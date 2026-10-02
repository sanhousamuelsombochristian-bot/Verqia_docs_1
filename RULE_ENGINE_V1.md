# VERQIA — Rule Engine V1.1

Références : Data Contract V1.3 (figé), Invariants V1.2, State Machines V1.
Périmètre de cette passe : **faits, exceptions, langage de conditions, décision, exécutabilité, testabilité, observabilité**.
Hors périmètre (passes suivantes) : contenu de la stratégie de recouvrement et valeurs des niveaux (Collection Engine), workflows et déclencheurs (Automation Engine), modèles de score (Risk / Priority).

Statut : **V1.1 — VERROUILLÉ**, amendé par `COLLECTION_ENGINE_V1_2.md` ( RN1 à RN12 : 13ᵉ exception `RECONCILIATION_PENDING`, faits de rapprochement, revérification des grants à l'exécution, scénarios `RE-47` à `RE-52`). Base V1.1 : R1 à R8 validées ; les quatre corrections de la revue sont appliquées (§12). Les points laissés provisoires (faits de comportement R5, listes `refresh_events` R13) sont **fermés** par `RISK_PRIORITY_CASHFLOW_V1.md` (§1.4 et §5).

---

## 0. Position et principes

```
DATA → EVENTS → FACTS → RULES → (Risk · Priority · Forecast) → DECISION → AUTOMATION → ACTION
```

Le Rule Engine répond à : **« qu'est-ce qui est vrai, et que devrait-on décider ? »** Il ne fait rien. Il ne modifie aucune donnée.

| # | Principe |
|---|---|
| P1 | **Fonction pure** : `évaluer(faits, définition, as_of) → Décision`. Aucun effet de bord, aucune écriture. Les appelants (Collection Engine, Automation Engine) exécutent la décision. |
| P2 | **Horloge injectée** : le moteur ne lit jamais l'heure. `as_of` est un paramètre. Même entrée, même sortie. |
| P3 | **Une décision est explicable** : chaque issue porte sa trace (faits utilisés, exceptions évaluées, conditions évaluées, versions). |
| P4 | **Les protections ne se contournent pas** : les règles intégrées passent avant toute règle configurable, dans un ordre fixe. |
| P5 | **Les faits viennent de la source de vérité** : jamais d'une valeur recopiée dans un événement. Le payload d'un événement ne sert qu'à déclencher. |
| P6 | **Le tenant est une entrée**, pas un contexte implicite : chaque fait est chargé pour une organisation donnée. |
| P7 | **Dates dans le fuseau de l'organisation** (règle C10). |

---

## 1. Quatre couches de règles

| Couche | Nature | Où elle vit | Configurable ? |
|---|---|---|---|
| **L0 — Invariants financiers** | allocation ≤ disponible, tenant, immuabilités | Domain + PostgreSQL (T1–T15) | Non |
| **L1 — Garde-fous d'exécution (exceptions intégrées)** | hiérarchie PAID / VOID / litige / promesse / hold / etc. (§3) | code, ordre fixe | Non |
| **L2 — Règles configurables** | déclencheurs, conditions, niveaux, actions, délais | JSON versionné (`automation_versions.definition`) | Oui, par organisation |
| **L3 — Modèles** | score de risque, score de priorité | Risk / Priority Engines | Version de modèle |

**Non-contournement (P4, verrouillé par la Phase 6)** : L2 ne peut ni supprimer, ni réordonner, ni désactiver L1. Le champ `exceptions` d'une définition JSON peut seulement **ajouter** des exceptions (clauses `UNLESS` supplémentaires), jamais en retirer.

**Nature de L1** : ce ne sont pas des règles métier au sens de L2. Ce sont des **garde-fous d'exécution** (« cette action a-t-elle le droit de partir ? ») ; L2 répond à « faut-il agir ? ». Cette distinction fixe le contrat avec le Collection Engine et l'Automation Engine (§7 bis).

---

## 2. Modèle de faits

Un **fait** est une valeur dérivée, calculée à `as_of` pour un sujet (organisation, client, facture, promesse), à partir de la source de vérité.

### 2.1 Propriétés de chaque fait

| Propriété | Valeurs |
|---|---|
| **Type** | `int`, `money` (unité mineure, `bigint`), `bool`, `date`, `timestamp`, `enum` (ordonné ou non) |
| **Fraîcheur** | `LIVE` (calculé à l'évaluation depuis les tables sources) ou `PROJECTION` (lu dans `risk_profiles` / `priority_items`, avec son `computed_at`) |
| **Nullité** | un fait peut être **inconnu** (`UNKNOWN`) : données manquantes ou échantillon insuffisant. L'inconnu n'est pas zéro. |
| **Portée** | organisation, client, facture, promesse |

**Fournisseurs de faits** (Architecture technique, TD12) : `rules.contracts` **déclare** un fournisseur par famille de faits ; chaque module propriétaire l'**implémente** dans son infrastructure ; le `FactReader` les assemble. `rules` n'importe aucun autre module (les faits de `collection` : `hold_active`, `highest_level_reached`, `reminders_30d` sont fournis par `collection`).

**Cohérence de lecture** : tous les faits d'une évaluation sont chargés dans une seule transaction en lecture à instantané stable (`REPEATABLE READ`), pour qu'une décision ne mélange pas deux états de la base.

### 2.2 Catalogue

**Organisation et temps**
| Fait | Type | Définition | Source |
|---|---|---|---|
| `org.status` | enum | statut de l'organisation | `organizations.status` |
| `org.today` | date | date de `as_of` dans le fuseau de l'organisation | `organizations.timezone` |
| `org.in_comm_window` | bool | l'heure locale de `as_of` est dans `[comm_window_start, comm_window_end]` | `org_settings.comm_window_start`, `org_settings.comm_window_end` |
| `org.is_business_day(d)` | bool | `d` est un jour ouvré : jour de semaine dans `business_days`, hors jours fériés | `org_settings.business_days`, `org_holidays.day` |

**Client**
| Fait | Type | Définition | Source |
|---|---|---|---|
| `customer.status` | enum | statut du client | `customers.status` |
| `customer.exposure_minor` | money | Σ `outstanding_minor` des factures ouvertes | `invoices.outstanding_minor` |
| `customer.overdue_exposure_minor` | money | Σ `outstanding_minor` des factures ouvertes en retard | `invoices.outstanding_minor`, `invoices.due_date` |
| `customer.open_invoice_count` | int | nombre de factures ouvertes | `invoices.lifecycle_state`, `invoices.settlement_state` |
| `customer.overdue_invoice_count` | int | nombre de factures ouvertes en retard | `invoices.due_date` |
| `customer.max_days_overdue` | int | plus grand `invoice.days_overdue` du client | `invoices.due_date` |
| `customer.risk_level` | enum ordonné `LOW < MEDIUM < HIGH < CRITICAL` | niveau de risque courant ; `UNKNOWN` sans profil | `risk_profiles.level` *(PROJECTION)* |
| `customer.risk_score` | int 0–100 | score courant | `risk_profiles.score` *(PROJECTION)* |
| `customer.broken_promises_12m` | int | promesses `BROKEN` sur 12 mois glissants | `promises.status`, `promises.customer_id` |
| `customer.avg_days_to_pay_12m` | int | somme `S` de `settled_on − due_date` sur `n` factures soldées dans les 12 derniers mois ; valeur `⌊(2 × S + n) / (2 × n)⌋` (demi vers le haut, valeurs négatives permises) ; `UNKNOWN` si `n < 3` | `invoices.settled_on`, `invoices.due_date` |
| `customer.late_payment_rate_12m` | **entier en pour-mille** : `⌊1 000 × (factures soldées en retard) / n⌋` sur 12 mois ; `UNKNOWN` si `n < 3` | `invoices.settled_on`, `invoices.due_date` |
| `customer.settled_invoice_count_12m` | int | `n` : nombre de factures soldées (`settled_on`) sur les 12 derniers mois | `invoices.settled_on` |
| `customer.reversed_payments_12m` | int | paiements annulés sur les 12 derniers mois | `payment_reversals.reversed_at`, `payments.customer_id` |
| `customer.delay_trend_90d` | int | délai moyen (formule ci-dessus) des factures soldées sur les 90 derniers jours moins celui des 90 jours précédents ; `UNKNOWN` s'il y a moins de 2 factures dans l'une des fenêtres | `invoices.settled_on`, `invoices.due_date` |
| `customer.unallocated_payment_minor` | money | `Σ (amount_minor − allocated_minor)` des paiements `RECEIVED` ou `PARTIALLY_ALLOCATED` du client | `payments.amount_minor`, `payments.allocated_minor`, `payments.status` |
| `customer.usable_contact(channel)` | bool | il existe un **contact de référence** du canal avec une valeur non vide | `customer_contacts.channel`, `customer_contacts.is_active`, `customer_contacts.is_primary`, `customer_contacts.value` |
| `customer.consent(channel)` | enum (`GRANTED`, `DENIED`, `WITHDRAWN`, `UNKNOWN`) | consentement du **contact de référence** du canal ; `UNKNOWN` s'il n'existe pas | `customer_contacts.consent_status`, `customer_contacts.is_primary` |

*Les faits de comportement (`*_12m`) sont **figés** par `RISK_PRIORITY_CASHFLOW_V1.md` §5 (fin de R5).*

**Contact de référence (R11).** Pour un canal donné : le contact `is_primary` et `is_active` de ce canal. **Aucun repli** : si le contact principal n'a pas de consentement, on n'utilise pas un autre contact actif qui en aurait un ; s'il n'existe pas de contact principal actif, `usable_contact` vaut faux (`NO_CONTACT`, détail `NO_PRIMARY_CONTACT` dans la trace). Le Collection Engine ne réinterprète jamais cette définition. Le Domain fait du premier contact actif d'un canal son contact principal par défaut, pour que l'absence de principal reste exceptionnelle. Une valeur de consentement autre que `GRANTED` donne `NO_CONSENT` pour un message envoyé par le système.

**Facture**
| Fait | Type | Définition | Source |
|---|---|---|---|
| `invoice.lifecycle` | enum | état de cycle de vie | `invoices.lifecycle_state` |
| `invoice.settlement` | enum | état de règlement | `invoices.settlement_state` |
| `invoice.is_open` | bool | cycle de vie ∈ {`ISSUED`, `DUE_SOON`, `DUE`, `OVERDUE`} **et** règlement ≠ `PAID` | `invoices.lifecycle_state`, `invoices.settlement_state` |
| `invoice.days_to_due` | int | `due_date − org.today` (négatif si échue) | `invoices.due_date` |
| `invoice.is_overdue` | bool | `is_open` et `due_date < org.today` | `invoices.due_date` |
| `invoice.days_overdue` | int | `max(0, org.today − due_date)` si `is_overdue`, sinon 0 | `invoices.due_date` |
| `invoice.business_days_overdue` | int | nombre de jours ouvrés entre `due_date` (exclu) et `org.today` (inclus) | `invoices.due_date`, `org_holidays.day` |
| `invoice.age_days` | int | `org.today − issue_date` | `invoices.issue_date` |
| `invoice.total_minor` / `paid_minor` / `outstanding_minor` | money | montants | `invoices.total_minor`, `invoices.paid_minor`, `invoices.outstanding_minor` |
| `invoice.cycle` | int | cycle de recouvrement | `invoices.collection_cycle` |
| `invoice.has_open_dispute` | bool | un litige `OPEN` existe | `invoice_disputes.status` |
| `invoice.collectible_minor` | money | `outstanding` sans litige ouvert ; `0` si litige total ; sinon `max(outstanding − disputed, 0)` | `invoice_disputes.disputed_amount_minor`, `invoices.outstanding_minor` |
| `invoice.active_promise` | bool | une promesse `ACTIVE` s'applique : de la facture, **ou** à défaut du client (`invoice_id` NULL) | `promises.status`, `promises.invoice_id`, `promises.customer_id` |
| `invoice.promise_scope` | enum (`INVOICE`, `CUSTOMER`, `NONE`) | portée de la promesse applicable ; **la promesse de la facture prime** sur celle du client (R12) | `promises.invoice_id` |
| `invoice.promise_date` / `promise_amount_minor` | date / money | de la promesse applicable (§ `promise_scope`) | `promises.promised_date`, `promises.promised_amount_minor` |
| `invoice.hold_active(automation_id)` | bool | un hold en vigueur couvre la facture, son client ou l'organisation, pour cette automatisation ou toutes | `collection_holds.status`, `collection_holds.starts_at`, `collection_holds.ends_at`, `collection_holds.scope`, `collection_holds.automation_id` |
| `invoice.highest_level_reached` | int | plus grand `level` des actions dont le statut compte, dans le cycle courant ; `0` sinon (définition complète §2.4) | `collection_actions.level`, `collection_actions.status` |
| `invoice.reminders_30d` | int | nombre d'actions `REMINDER` `DONE` sur les 30 derniers jours (fenêtre glissante) | `collection_actions.type`, `collection_actions.executed_at` |
| `invoice.days_since_last_action` | int | jours (fuseau de l'organisation) depuis la dernière action `DONE` de la facture dans le cycle courant, tous types et toutes origines ; absent s'il n'y en a pas | `collection_actions.executed_at`, `collection_actions.status`, `collection_actions.invoice_id` |
| `invoice.priority_level` | enum ordonné `NONE < WATCH < ACTION < PRIORITY < CRITICAL` | priorité courante | `priority_items.level` *(PROJECTION)* |
| `invoice.priority_score` | numérique 0–100 | score de priorité | `priority_items.rank_score` *(PROJECTION)* |
| `invoice.is_imported_held` | bool | la facture appartient à un lot d'import qui n'est pas encore libéré | `invoices.import_batch_id`, `import_batches.status` |
| `invoice.reconciliation_pending` | bool `LIVE` | au moins un paiement satisfait Q1 à Q5 pour cette facture : non alloué, non annulé, même client et même devise, facture ouverte et émise au plus tard à la date de valeur, **fenêtre non écoulée** (date locale de l'organisation ≤ dernier jour de suspension ; `COLLECTION_ENGINE_V1_2.md` §1) | `payments.amount_minor`, `payments.allocated_minor`, `payments.status`, `payments.customer_id`, `payments.currency`, `payments.value_date`, `payments.created_at`, `invoices.issue_date`, `invoices.currency` |
| `invoice.reconciliation_pending_minor` | money `LIVE` | somme des montants non alloués des paiements qualifiants ; valeur brute, jamais stockée dans un snapshot déterminant (RP14) | `payments.amount_minor`, `payments.allocated_minor` |

*Le chargeur de faits calcule les deux faits et le bloc explicatif `reconciliation` du `decision_snapshot` (identifiants, montants, dates, `window_last_day`, `stale`) par la **même** fonction (`reconciliation_state`) : aucune troisième source.*

**Règle de dérivation** : les faits temporels (`is_overdue`, `days_overdue`, `days_to_due`) sont calculés **depuis les dates**, pas depuis `lifecycle_state`. Le cycle de vie est mis à jour par le Scheduler avec un léger retard possible ; le moteur ne doit pas dépendre de ce retard. `lifecycle_state` sert seulement à classer une facture comme ouverte ou non (`DRAFT`, `CANCELLED`, `VOID` exclus).

### 2.3 Contrat de projection et barrière de fraîcheur (R2, R13)

Un fait `PROJECTION` peut être en retard sur l'événement qui déclenche l'évaluation : `INVOICE_OVERDUE` est consommé à la fois par le Risk Engine et par l'Automation Engine, sans ordre garanti.

**Contrat de projection.** Chaque projection déclare :

| Élément | Sens |
|---|---|
| `producer` | le moteur qui l'écrit |
| `refresh_events` | la liste **exhaustive** des événements qui provoquent son recalcul |
| `computed_at` | horodatage du **dernier calcul**, mis à jour à **chaque** recalcul, y compris quand l'entrée n'a pas changé (dans ce cas : pas de nouveau snapshot, pas d'événement, mais `computed_at` avance) |

Sans cette dernière règle, la barrière attendrait pour toujours : un recalcul sans changement (`input_hash` identique) ne réécrirait rien, donc `computed_at` resterait inférieur à l'événement.

**Règle de barrière.** Si l'événement déclencheur figure dans `refresh_events` de la projection utilisée, l'évaluation exige `projection.computed_at >= trigger_event.occurred_at` (l'égalité est acceptable). Sinon l'issue est **`DEFER`** : nouvelles tentatives à +30 s, +2 min, +10 min, +30 min ; passé ce délai, l'évaluation continue avec la valeur disponible et la trace porte `stale=true` et l'âge de la projection.
Si l'événement déclencheur **ne figure pas** dans `refresh_events`, aucune barrière n'est appliquée : la projection est, par conception, non affectée par cet événement, et la trace enregistre son `computed_at`.
Les évaluations sans événement déclencheur (balayage, revalidation) exigent seulement l'existence de la projection.

**Listes définitives** (RP7, `RISK_PRIORITY_CASHFLOW_V1.md` §1.4 ; elles remplacent les listes provisoires dérivées de la matrice des consommateurs de `INVARIANTS_V1.md` §3.2) :

| Projection | Producteur | `refresh_events` |
|---|---|---|
| `risk_profiles` (`customer.risk_level`, `customer.risk_score`) | Risk Engine | `INVOICE_ISSUED`, `INVOICE_OVERDUE`, `INVOICE_PARTIALLY_PAID`, `INVOICE_PAID`, `INVOICE_SETTLEMENT_REVERTED`, `INVOICE_VOIDED`, `PAYMENT_ALLOCATED`, `PAYMENT_ALLOCATION_REVERSED`, `PAYMENT_REVERSED`, `PROMISE_BROKEN`, `PROMISE_FULFILLED`, `RISK_RECALCULATION_REQUESTED` |
| `priority_items` (`invoice.priority_level`, `invoice.priority_score`) | Priority Engine | `INVOICE_ISSUED`, `INVOICE_DUE_SOON`, `INVOICE_DUE`, `INVOICE_OVERDUE`, `INVOICE_PARTIALLY_PAID`, `INVOICE_PAID`, `INVOICE_SETTLEMENT_REVERTED`, `INVOICE_VOIDED`, `INVOICE_CANCELLED`, `INVOICE_DISPUTED`, `INVOICE_DISPUTE_RESOLVED`, `PAYMENT_CREATED`, `PAYMENT_ALLOCATED`, `PAYMENT_ALLOCATION_REVERSED`, `PAYMENT_REVERSED`, `PROMISE_CREATED`, `PROMISE_BROKEN`, `PROMISE_FULFILLED`, `PROMISE_CANCELLED`, `COLLECTION_HOLD_PLACED`, `COLLECTION_HOLD_RELEASED`, `COLLECTION_ACTION_EXECUTED`, `RISK_CHANGED`, `PRIORITY_RECALCULATION_REQUESTED` |

**Obligation inter-moteurs.** Toute projection utilisée par une règle doit avoir, pour **chaque** événement de sa liste, un mécanisme de recalcul déterministe qui met à jour `computed_at`. C'est un contrat entre le Rule Engine et les moteurs producteurs ; il sera vérifié par un test d'intégration global (passe Engine Contracts).

**Validation statique** : une définition qui exige un fait `PROJECTION` alors que son événement déclencheur n'est pas dans les `refresh_events` de cette projection reçoit un **avertissement** (`DEFINITION_PROJECTION_TRIGGER_MISMATCH`), non bloquant : la règle lira une valeur que cet événement n'a pas rafraîchie.

### 2.4 Définition complète de `invoice.highest_level_reached` (R9)

Fait `LIVE`. Portée : même facture, même `collection_cycle`, **tous types d'action et toutes origines** (automatique ou manuelle). Valeur : le plus grand `level` parmi les actions dont le statut compte ; `0` s'il n'y en a aucune.

| Statut de l'action | Compte ? | Raison |
|---|:-:|---|
| `PROPOSED` | non | pas encore décidée |
| `PENDING_APPROVAL` | non | en attente d'accord (N7) |
| `SCHEDULED` | **oui** | engagée |
| `EXECUTING` | **oui** | en cours |
| `DONE` | **oui** | effectuée |
| `FAILED` | non | n'a pas abouti : le niveau n'a pas été atteint auprès du client |
| `CANCELLED` | non | annulée par un acteur |
| `SUPPRESSED` | non | exception métier : jamais exécutée |

Le fait est recalculé à chaque évaluation : une action `SCHEDULED` puis `SUPPRESSED` ou `CANCELLED` cesse de compter.
Conséquence à connaître pour `FAILED` : sa `dedup_key` reste occupée (l'unicité ne libère que `CANCELLED` et `SUPPRESSED`). Le moteur ne recrée donc pas la même action ; l'alerte au responsable (machine `Collection Action`) traite l'échec. Il peut en revanche produire une action d'un niveau supérieur.

---

## 3. Garde-fous d'exécution (exceptions intégrées, L1)

Les exceptions intégrées sont des **garde-fous d'exécution** : elles répondent à « cette action a-t-elle le droit de partir maintenant ? », pas à « faut-il agir ? » (question de L2). Le Collection Engine et l'Automation Engine les appellent par la **même fonction** ; aucun ne les réimplémente.

**Étape 0 — Applicabilité.** Le sujet doit être une facture **émise**. Une facture `DRAFT` n'est pas « annulée » : elle n'est simplement pas encore recouvrable. Le moteur retourne `SKIP` (`skip_reason = NOT_ISSUED`) sans évaluer d'exception.

Ensuite, dans cet ordre, les 13 exceptions. La première qui échoue devient `primary_exception` et donne le code de l'issue ; **toutes** sont évaluées et consignées dans `exceptions_trace`, pour l'explicabilité.

| # | Code | Condition d'échec (l'exception s'applique) | Classe |
|---|---|---|---|
| 1 | `ORG_INACTIVE` | `org.status ≠ ACTIVE` | intégrité |
| 2 | `CUSTOMER_ARCHIVED` | `customer.status = ARCHIVED` | intégrité |
| 3 | `CUSTOMER_INACTIVE` | `customer.status = INACTIVE` | intégrité |
| 4 | `VOIDED` | facture `CANCELLED` ou `VOID` | intégrité |
| 5 | `PAID` | règlement = `PAID` | intégrité |
| 6 | `DISPUTED` | `invoice.collectible_minor = 0` | métier |
| 7 | `PROMISE_ACTIVE` | `invoice.active_promise` | métier |
| 8 | `HOLD_ACTIVE` | `invoice.hold_active(automation_id)` | métier |
| 9 | `IMPORT_HELD` | `invoice.is_imported_held` | automatique seulement |
| 10 | `FREQUENCY_LIMIT` | `invoice.reminders_30d ≥ max_reminders_per_30d` (actions de type `REMINDER`) | politique |
| 11 | `NO_CONTACT` | aucun contact utilisable pour le canal visé (§2.2) | livraison |
| 12 | `NO_CONSENT` | consentement du contact de référence ≠ `GRANTED`, pour un message envoyé par le système | livraison |
| 13 | `RECONCILIATION_PENDING` | `invoice.reconciliation_pending` (un paiement reçu, non encore affecté, pourrait régler cette facture ; fenêtre bornée en jours ouvrés) | **métier** |

*Le n° 13 est ajouté à la fin pour ne pas renuméroter les 12 existants ; l'ordre ne fixe que le code retenu quand plusieurs exceptions échouent (Collection V1.2, §3.1).*

*Correction par rapport à la première version : `CUSTOMER_INACTIVE` passe en classe intégrité (la matrice N3, validée, interdit toute nouvelle action de recouvrement pour un client `INACTIVE` : il faut le réactiver) ; `FREQUENCY_LIMIT` devient une exception de politique, contournable (limite anti-harcèlement décidée par l'organisation, pas contrainte légale).*

Exemple de sortie :
```json
{
  "outcome": "SUPPRESS",
  "primary_exception": "PAID",
  "suppression_code": "PAID",
  "exceptions_trace": [
    {"code": "ORG_INACTIVE", "result": "PASSED"},
    {"code": "CUSTOMER_ARCHIVED", "result": "PASSED"},
    {"code": "PAID", "result": "FAILED"},
    {"code": "DISPUTED", "result": "FAILED"}
  ]
}
```

### 3.1 Applicabilité et contournement (R3, R10)

| Code | S'applique à une action **manuelle** ? | Contournable ? | Rôle minimal pour contourner |
|---|:-:|:-:|---|
| `ORG_INACTIVE`, `CUSTOMER_ARCHIVED`, `CUSTOMER_INACTIVE`, `VOIDED`, `PAID` | oui | **non** | — |
| `DISPUTED` | oui | oui | `MANAGER` |
| `PROMISE_ACTIVE` | oui | oui | `COLLECTOR` |
| `HOLD_ACTIVE` | oui | oui, **sauf** hold de type `LEGAL` | `MANAGER` |
| `IMPORT_HELD` | non (ne concerne que l'automatique) | sans objet | — |
| `FREQUENCY_LIMIT` | oui | oui | `MANAGER` |
| `RECONCILIATION_PENDING` | oui, les quatre types d'action | oui, **manuel seulement** ; grant **revérifié à l'exécution** (§3.3) | `COLLECTOR` |
| `NO_CONTACT` | oui | **non** | — |
| `NO_CONSENT` | oui, pour un envoi par le système (pas pour une tâche d'appel humain) | **non** | — |

Pour une **action automatique**, aucune exception n'est contournable.
**Exemptions** : les notifications **internes** (alerte responsable, alerte administrateur, revue de rapprochement) et les demandes de recalcul ne contactent pas le client ; elles sont soumises à la seule exception 1 (`ORG_INACTIVE`).

### 3.2 Traduction en issue selon le contexte

| Code | Action de recouvrement | Exécution d'automatisation |
|---|---|---|
| `ORG_INACTIVE`, `CUSTOMER_INACTIVE`, `CUSTOMER_ARCHIVED` | `SUPPRESSED` | `PAUSED` (même code) |
| `VOIDED` | `SUPPRESSED` | `CANCELLED` (`SUBJECT_VOIDED`) |
| `PAID` | `SUPPRESSED` | `CANCELLED` (`SUBJECT_PAID`) |
| `DISPUTED`, `PROMISE_ACTIVE`, `HOLD_ACTIVE`, `IMPORT_HELD`, `RECONCILIATION_PENDING` | `SUPPRESSED` | `PAUSED` (même code) |
| `FREQUENCY_LIMIT`, `NO_CONTACT`, `NO_CONSENT` | `SUPPRESSED` | étape `SKIPPED` ; le flux continue |

Une exécution `PAUSED` reprend quand sa cause est levée ; une exécution dont une étape est `SKIPPED` poursuit ses étapes suivantes (une branche de repli éventuelle est définie dans la passe Automation Engine).

### 3.3 Override manuel : structure côté domaine (R10)

Le moteur n'accepte **jamais** un booléen `override` venu du frontend. Le frontend envoie une **demande** `{exception_code, reason_code, reason_text}`. La couche Application (use case `AuthorizeOverride`) décide :

1. l'action est d'origine **manuelle** ;
2. l'exception est contournable (§3.1) et, pour `HOLD_ACTIVE`, le hold n'est pas de type `LEGAL` ;
3. le rôle de l'acteur est au moins le rôle minimal de l'exception ;
4. le motif est renseigné ;
5. l'organisation est `ACTIVE`.

Elle produit alors une **`OverrideGrant`** typée, seule forme acceptée par le moteur :

| Champ | Contenu |
|---|---|
| `exception_code` | l'exception contournée |
| `actor_id`, `actor_role` | qui, avec quel rôle |
| `reason_code`, `reason_text` | pourquoi |
| `granted_at` | quand (horloge injectée) |

Effet dans la décision : l'exception est `OVERRIDDEN` dans `exceptions_trace`, `overrides[]` liste les grants, l'issue peut être `PROCEED`. Un grant qui ne correspond à aucune exception en échec est ignoré et consigné.
Persistance : `collection_actions.decision_snapshot.overrides[]` et une ligne `audit_logs` (action sensible, D3). Aucune nouvelle colonne.

**Le grant est une preuve, pas une autorité (V1.2, RN3).** `decision_snapshot` est immuable : `overrides[]` atteste ce qui a été décidé à la création, il n'autorise rien à lui seul. Pour **toute** exception contournable (`DISPUTED`, `PROMISE_ACTIVE`, `HOLD_ACTIVE` hors `LEGAL`, `FREQUENCY_LIMIT`, `RECONCILIATION_PENDING`) :

1. le grant est lié à **une action** et à **un code d'exception** ; il ne couvre ni une autre action, ni une exécution d'automatisation ;
2. **à l'exécution** (contexte D), avant `EXECUTING`, `ExecuteDueAction` ré-autorise le grant avec la situation **courante** : acteur toujours membre actif, rôle **courant** ≥ rôle minimal, organisation `ACTIVE`, motif présent, exception toujours contournable (un hold `LEGAL` apparu depuis ne l'est pas), action toujours `MANUAL` ;
3. échec : action `SUPPRESSED` avec le code de l'exception ; la cause (`ACTOR_INACTIVE`, `ROLE_INSUFFICIENT`, `ORG_INACTIVE`, `NOT_OVERRIDABLE`) est écrite dans l'audit ; ce n'est pas une erreur d'API ;
4. une automatisation ne **crée** jamais de grant (`AuthorizeOverride` exige un acteur humain) et n'en **consomme** jamais (les contextes `AUTOMATIC` ignorent tout grant reçu et le consignent) ; un worker qui exécute une action manuelle ne fait que rejouer la vérification 2 ;
5. audit à la création **et** à chaque vérification à l'exécution ; test d'architecture : `override_grants` n'est un paramètre que des cas d'usage manuels et de cette vérification.

Détail : `COLLECTION_ENGINE_V1_2.md` §3.3 (G1 à G9).
Erreurs d'autorisation (couche Application) : `OVERRIDE_NOT_ALLOWED` · `OVERRIDE_ROLE_INSUFFICIENT` · `OVERRIDE_REASON_REQUIRED` · `OVERRIDE_ORIGIN_NOT_MANUAL`.

---

## 4. Langage de conditions

Les conditions d'une définition d'automatisation sont **des données, jamais du code**. Aucun appel de fonction, aucune expression libre, aucune expression régulière.

### 4.1 Grammaire (schéma JSON v1)

```
condition := comparaison | { "all": [condition, …] } | { "any": [condition, …] } | { "not": condition }
comparaison := { "fact": <nom de fait>, "op": <opérateur>, "value": <valeur | paramètre> }
paramètre  := { "param": "org.critical_amount_minor" | "org.due_soon_days" | … }   // uniquement des colonnes d'org_settings
```

Opérateurs : `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `is_unknown`, `is_known`.
Sur un fait `enum` ordonné, `gt/gte/lt/lte` suivent l'ordre déclaré (`risk_level gte MEDIUM`).
Les montants s'expriment en unité mineure ; la devise est celle de l'organisation.

### 4.2 Logique à trois valeurs (R7)

Chaque comparaison vaut `TRUE`, `FALSE` ou `UNKNOWN` (fait inconnu).

| | `all` | `any` | `not` |
|---|---|---|---|
| Règle | `FALSE` si un terme est `FALSE` ; sinon `UNKNOWN` si un terme est `UNKNOWN` ; sinon `TRUE` | `TRUE` si un terme est `TRUE` ; sinon `UNKNOWN` si un terme est `UNKNOWN` ; sinon `FALSE` | `not UNKNOWN = UNKNOWN` |

**À la racine**, une condition `UNKNOWN` est traitée comme **non satisfaite** (aucune action), et la trace le signale (« donnée manquante : `customer.risk_level` »). Le moteur ne devine jamais une valeur pour agir.

### 4.3 Limites

Profondeur ≤ 5, nombre de nœuds ≤ 50, aucune valeur de type chaîne libre hors valeurs d'énumération, aucune référence à un fait absent du catalogue §2.2.

---

## 5. Validation statique d'une définition

À la création d'une version d'automatisation (`automation_versions`), avant insertion. Une version invalide n'est **jamais** enregistrée.

| Contrôle | Code d'erreur |
|---|---|
| Conformité au schéma JSON (`schema_version`) | `DEFINITION_SCHEMA_INVALID` |
| Fait inexistant dans le catalogue | `DEFINITION_UNKNOWN_FACT` |
| Opérateur ou valeur incompatible avec le type du fait | `DEFINITION_TYPE_MISMATCH` |
| Action hors liste blanche (contrat §8.2) | `DEFINITION_ACTION_NOT_ALLOWED` |
| Niveau hors de 1–5 ; délai hors bornes | `DEFINITION_VALUE_OUT_OF_RANGE` |
| Profondeur ou taille excédées | `DEFINITION_TOO_COMPLEX` |
| Tentative de retirer ou désactiver une exception intégrée | `DEFINITION_BUILTIN_EXCEPTION_OVERRIDE` |
| **Boucle** : une action émet (directement) l'événement qui sert de déclencheur (par exemple déclencheur `RISK_CHANGED` avec action `REQUEST_RISK_RECALCULATION`) | `DEFINITION_TRIGGER_LOOP` (R8) |
| Fait `PROJECTION` exigé alors que l'événement déclencheur n'est pas dans les `refresh_events` de la projection (avertissement, non bloquant) | `DEFINITION_PROJECTION_TRIGGER_MISMATCH` |
| Canal désactivé en V1 (`SMS`, `WHATSAPP`) référencé par une étape | `DEFINITION_CHANNEL_NOT_ENABLED` |
| Couple (niveau, type d'action) hors de la matrice du Collection Engine | `DEFINITION_LEVEL_TYPE_INCOMPATIBLE` |
| Plage de niveaux d'une étape vide, hors de 1–5 ou incompatible avec le type | `DEFINITION_STEP_LEVEL_RANGE_INVALID` |

Le contrôle de boucle statique complète, sans le remplacer, la limite d'exécution `causation_depth ≤ 20`.
La validation produit aussi la liste des faits requis (`required_facts`), pour ne charger que ceux-là (§9).

---

## 6. La décision

### 6.1 Issues

| Issue | Sens | Exemple |
|---|---|---|
| `PROCEED` | aucune exception ne s'applique et les conditions sont vraies | créer l'action |
| `SUPPRESS` | une exception intégrée s'applique | facture `PAID` : `suppression_code = PAID` |
| `SKIP` | les conditions ne sont pas satisfaites (fausses ou inconnues), ou le niveau est déjà atteint | rien à faire |
| `DEFER` | une condition d'exécution n'est pas encore remplie ; réessayer plus tard | projection en retard ; hors fenêtre de communication (`retry_at` = prochain créneau) |

Hors fenêtre de communication : `DEFER` et non une erreur (Invariants §7.1).

Raisons de `SKIP` : `CONDITIONS_NOT_MET`, `CONDITIONS_UNKNOWN`, `NOT_ISSUED` (facture `DRAFT`), `LEVEL_ALREADY_REACHED`, `NO_LEVEL_MATCHED`, `STEP_LEVEL_OUT_OF_RANGE` (niveau calculé hors de la plage de l'étape), `APPROVAL_PREVIOUSLY_REJECTED` (approbation refusée dans ce cycle).

### 6.2 Structure (conceptuelle)

| Champ | Contenu |
|---|---|
| `decision_id` | hash déterministe de (`organization_id`, sujet, `as_of`, `engine_version`, `automation_version_id`, versions de modèles, `input_hash`) |
| `subject` | type et identifiant (facture, client…) |
| `evaluated_at`, `as_of`, `org_timezone` | contexte temporel |
| `outcome` | `PROCEED / SUPPRESS / SKIP / DEFER` |
| `suppression_code`, `skip_reason`, `retry_at` | selon l'issue |
| `primary_exception` | code de la première exception en échec (celle qui détermine l'issue) ; absent si aucune |
| `exceptions_trace[]` | pour chacune des 13 exceptions : `PASSED`, `FAILED`, `OVERRIDDEN` ou `NOT_APPLICABLE`, et les faits utilisés ; **toutes** sont évaluées, une seule décide |
| `overrides[]` | les `OverrideGrant` prises en compte (§3.3) |
| `requires_approval`, `approval_reason` | décidés par les règles (`approval_min_risk_level`, étapes de la définition) ; le Collection Engine crée l'approbation |
| `conditions_trace` | l'arbre des conditions, chaque feuille avec fait, opérateur, valeur attendue, **valeur observée**, résultat `TRUE/FALSE/UNKNOWN` |
| `facts_snapshot` | uniquement les faits utilisés, avec leur valeur et, pour les `PROJECTION`, `computed_at` |
| `levels` | `risk_level`, `priority_level`, `collection_level` — **séparés** |
| `rule_refs` | `engine_version`, `automation_id`, `automation_version_id`, versions des modèles de risque et de priorité |
| `proposed_actions[]` | actions à créer si `PROCEED` (type, niveau, canal, paramètres) |
| `input_hash` | hash des faits et des versions ; deux évaluations de même hash produisent la même décision |

**Sans donnée personnelle** : la trace ne contient que des identifiants, des montants, des états et des dates (contrat §17).

### 6.3 Persistance

| Où | Quoi |
|---|---|
| `collection_actions.decision_snapshot` | la décision qui a produit l'action, y compris une action créée `SUPPRESSED` |
| `automation_execution_steps.revalidation_result` | la décision de **chaque** revalidation, à chaque étape |
| Compteurs et journaux structurés | les issues `SKIP` et `DEFER` au niveau du **déclencheur** (trop nombreuses pour être stockées : une organisation de 5 000 factures évalue tout chaque jour) |

Pour répondre à « pourquoi rien n'est parti pour cette facture ? », le moteur propose une **évaluation à la demande** (§7), qui recalcule la décision courante, sans écrire.

---

## 7. Contextes d'évaluation

| Contexte | Déclencheur | Entrée | Sortie exploitée par |
|---|---|---|---|
| **A. Déclenchement** | événement ou instant temporel | sujet, définition, `as_of` | Automation Engine : créer ou non une exécution |
| **B. Revalidation d'étape** | avant chaque étape d'une exécution | sujet, définition, `as_of` | Automation Engine : continuer, mettre en pause, annuler, sauter |
| **C. Création d'action** | proposition d'action | sujet, type, niveau, canal | Collection Engine : `PROPOSED` ou `SUPPRESSED` |
| **D. Revalidation avant exécution** | juste avant `SCHEDULED → EXECUTING` | l'action | Collection Engine : envoyer ou `SUPPRESSED` |
| **E. Simulation / explication** | requête utilisateur (« pourquoi ? », « que se passerait-il ? ») | sujet, `as_of` (défaut : maintenant) | interface ; **n'écrit rien** |

Les contextes A à D utilisent **exactement la même fonction** que E : il n'existe pas deux implémentations, donc pas de divergence possible entre ce que l'interface explique et ce que le moteur fait.

---

## 7 bis. Frontière Rule Engine / Collection Engine / Automation Engine

| Responsabilité | Rule Engine | Collection Engine | Automation Engine |
|---|:-:|:-:|:-:|
| Décider si une action a le droit de partir (garde-fous L1) | **oui** | appelle (contextes C, D) | appelle (contextes A, B) |
| Évaluer les conditions et déterminer le niveau | **oui** | — | — |
| Décider si une approbation est requise (règles + `approval_min_risk_level`) | **oui** (`requires_approval`, avec motif) | crée l'approbation | orchestre l'attente |
| Choisir le canal, le gabarit, la personne assignée | — | **oui** | fournit les paramètres de la définition |
| Créer, planifier, exécuter, réessayer, clore une action | — | **oui** | — |
| Persister la trace de décision | — | `decision_snapshot` | `revalidation_result` |
| Orchestrer étapes, délais, pauses, reprises | — | — | **oui** |
| Écrire risque, priorité, cashflow | jamais | jamais | jamais (demandes seulement) |

Le **canal** est fourni par l'appelant : le Collection Engine le choisit avant d'appeler les garde-fous, qui évaluent alors `NO_CONTACT` et `NO_CONSENT` pour ce canal. Le repli vers un autre canal est une décision du Collection Engine (passe suivante), pas du Rule Engine.

---

## 8. Détermination du niveau de recouvrement

Le mécanisme est fixé ici ; les valeurs (seuils, conditions par niveau) le seront dans la passe Collection Engine.

1. La définition fournit une **table ordonnée** `niveaux[]` : chaque entrée associe un niveau (1 à 5) à une condition. Évaluation **du plus haut au plus bas** ; la première condition vraie l'emporte (premier appariement).
2. **Niveau initial** : `niveau = 0` avant résolution (R15). Si aucune condition n'est vraie, il reste à 0.
3. **Plancher** (N7) : si `invoice.is_overdue`, `niveau = max(niveau, 3)` ; depuis 0, une facture en retard devient donc niveau 3. Si la facture n'est pas en retard et que `niveau = 0`, l'issue est `SKIP` (`skip_reason = NO_LEVEL_MATCHED`).
4. **Non-régression** : si `niveau < invoice.highest_level_reached` (§2.4), l'issue est `SKIP` (`skip_reason = LEVEL_ALREADY_REACHED`). Une action manuelle peut passer outre, avec un `OverrideGrant`.
5. Le niveau de recouvrement ne se déduit **jamais** directement du niveau de risque : les deux sont des faits distincts que les conditions de la table peuvent combiner.

---

## 9. Exécutable : structure du composant

| Composant | Rôle |
|---|---|
| **Fact providers** | un par famille de faits ; interface : `charger(sujets[], noms_de_faits[], as_of) → FaitSet` ; chargement **par lot** (fonctions de fenêtrage par client), jamais une requête par facture |
| **Built-in exceptions** | les 13 exceptions du §3, fonctions pures sur un `FaitSet` |
| **Condition evaluator** | évalue l'arbre à trois valeurs et produit `conditions_trace` |
| **Definition validator** | schéma, faits, types, boucles (§5) |
| **Level resolver** | table ordonnée + plancher + non-régression (§8) |
| **Decision builder** | assemble la `Décision` et calcule `input_hash` |
| **Engine facade** | point d'entrée unique `évaluer(...)` |

Emplacement dans l'architecture : couche **Domain** ; **aucune dépendance** à Django, à Redis ni à un fournisseur. Seuls les fact providers touchent la base, via l'infrastructure.

**Performance.**
- Évaluation par lot : 5 000 factures se chargent par client (une requête d'agrégats par famille de faits), pas par facture.
- Seuls les faits listés dans `required_facts` sont chargés.
- Les faits `PROJECTION` sont lus par jointure sur `risk_profiles` / `priority_items`, sans recalcul.
- Aucun cache de faits entre transactions en V1 (une valeur périmée serait une décision fausse) ; le lot d'évaluation partage un instantané.
- **Point à vérifier au banc d'essai** : le coût du fait `invoice.reminders_30d` et des faits de comportement (`*_12m`) sur des volumes réalistes ; index à ajuster.

---

## 10. Testable

### 10.1 Stratégie

| Type de test | Ce qu'il garantit |
|---|---|
| **Tests unitaires par exception** | chacune des 13 exceptions, échec et réussite |
| **Tests différentiels des faits** | chaque fact provider est comparé à une implémentation naïve en Python sur des données aléatoires |
| **Tests d'or (golden)** | un tableau de scénarios avec la `Décision` attendue, complète (§10.2) |
| **Tests de propriétés** | déterminisme (mêmes entrées, même décision) ; ajouter une exception ne transforme jamais `SUPPRESS` en `PROCEED` ; permuter des termes d'un `all` ou d'un `any` ne change pas le résultat ; `UNKNOWN` n'est jamais traité comme `TRUE` |
| **Tests de fuseau et de temps** | 23:59 et 00:01 locaux ; fuseaux avec heure d'été ; jours fériés ; passage de fenêtre de communication |
| **Tests du validateur** | jeu de définitions invalides (une par code d'erreur du §5) ; fuzzing du schéma |
| **Rejeu de décisions** | à partir d'un `facts_snapshot` et des versions enregistrés, la décision se **reproduit à l'identique** ; garde-fou de non-régression à chaque changement de `engine_version` |
| **Isolation tenant** | une évaluation pour l'organisation A ne lit jamais une ligne de B |
| **Concurrence** | deux évaluations simultanées du même sujet avec les mêmes entrées produisent le même `decision_id` ; la création d'action reste unique (`dedup_key`) |

### 10.2 Matrice minimale de scénarios (tests d'or)

| # | Scénario | Issue attendue |
|---|---|---|
| 1 | facture ouverte en retard de 12 jours, risque `HIGH`, aucune exception | `PROCEED`, niveau ≥ 3 |
| 2 | facture `PAID` | `SUPPRESS` `PAID` |
| 3 | facture `PAID` **et** litige ouvert | `SUPPRESS` `PAID` (l'ordre prime) ; trace : `DISPUTED` aussi consigné |
| 4 | facture `VOID` d'un client `ARCHIVED` | `SUPPRESS` `CUSTOMER_ARCHIVED` (ordre 2 avant 4) |
| 5 | litige partiel, `collectible_minor > 0` | `PROCEED`, action sur le montant recouvrable |
| 6 | litige partiel couvrant tout le solde | `SUPPRESS` `DISPUTED` |
| 7 | litige total | `SUPPRESS` `DISPUTED` |
| 8 | promesse `ACTIVE`, action automatique | `SUPPRESS` `PROMISE_ACTIVE` |
| 9 | promesse `ACTIVE`, action **manuelle** motivée | `PROCEED` avec `override` enregistré |
| 10 | hold `LEGAL`, action manuelle | `SUPPRESS` `HOLD_ACTIVE` (non contournable) |
| 11 | hold visant une autre automatisation | `PROCEED` |
| 12 | hold expiré (`ends_at < as_of`) mais statut encore `ACTIVE` | `PROCEED` (règle de lecture du contrat) |
| 13 | `reminders_30d = max_reminders_per_30d`, action `REMINDER` | `SUPPRESS` `FREQUENCY_LIMIT` |
| 14 | client sans contact du canal | `SUPPRESS` `NO_CONTACT` |
| 15 | contact présent, consentement `UNKNOWN`, message automatique | `SUPPRESS` `NO_CONSENT` |
| 16 | même cas, tâche d'appel humain | `PROCEED` |
| 17 | condition `risk_level gte MEDIUM`, client sans profil | `SKIP`, trace « donnée manquante » |
| 18 | projection de risque plus ancienne que l'événement | `DEFER` |
| 19 | facture `OVERDUE`, règle produisant le niveau 2 | niveau relevé à 3 (plancher) |
| 20 | niveau calculé 3, niveau 4 déjà `SCHEDULED` | `SKIP` `LEVEL_ALREADY_REACHED` |
| 21 | niveau 4 déjà `PENDING_APPROVAL` uniquement, niveau calculé 3 | `PROCEED` (cet état ne compte pas) |
| 22 | hors fenêtre de communication | `DEFER` avec `retry_at` |
| 23 | lot d'import non libéré | `SUPPRESS` `IMPORT_HELD` |
| 24 | organisation `SUSPENDED` | `SUPPRESS` `ORG_INACTIVE` (aussi pour une notification interne) |
| 25 | notification interne, facture `PAID` | `PROCEED` (exemptée hors exception 1) |
| 26 | facture `DRAFT` | `SKIP` `NOT_ISSUED`, aucune exception évaluée |
| 27 | facture `CANCELLED` | `SUPPRESS` `VOIDED` |
| 28 | facture `VOID` | `SUPPRESS` `VOIDED` |
| 29 | lot d'import non libéré **et** facture `PAID` | `SUPPRESS` `PAID` (ordre 5 avant 9) ; `IMPORT_HELD` aussi consigné `FAILED` |
| 30 | client `INACTIVE`, action manuelle avec demande d'override | refus `OVERRIDE_NOT_ALLOWED` (non contournable) |
| 31 | promesse `ACTIVE`, action manuelle, rôle `COLLECTOR` | `PROCEED`, `PROMISE_ACTIVE` `OVERRIDDEN` |
| 32 | litige total, action manuelle, rôle `COLLECTOR` | refus `OVERRIDE_ROLE_INSUFFICIENT` |
| 33 | booléen `override=true` fourni sans `OverrideGrant` | ignoré ; issue inchangée |
| 34 | promesse de facture **et** promesse client `ACTIVE` | `promise_scope = INVOICE` ; date et montant de la promesse de facture |
| 35 | plusieurs contacts email actifs ; le principal sans consentement, un autre avec | `SUPPRESS` `NO_CONSENT` (aucun repli) |
| 36 | canal sans contact principal actif | `SUPPRESS` `NO_CONTACT` |
| 37 | cycle avec une action `FAILED` niveau 4 et une `SUPPRESSED` niveau 5 ; niveau calculé 3 | `highest_level_reached = 0` ; `PROCEED` |
| 38 | aucune condition de la table de niveaux vraie, facture non échue | `SKIP` `NO_LEVEL_MATCHED` |
| 39 | aucune condition vraie, facture en retard | niveau 3 (plancher depuis 0) |
| 40 | recalcul de risque à entrée inchangée | `computed_at` avancé, aucun nouveau snapshot ; la barrière est satisfaite |
| 41 | `computed_at` égal à `occurred_at` de l'événement | barrière satisfaite |
| 42 | événement déclencheur absent des `refresh_events` de la projection | aucune barrière ; trace avec `computed_at` |
| 43 | `TRUE and UNKNOWN` · `FALSE and UNKNOWN` · `TRUE or UNKNOWN` · `FALSE or UNKNOWN` · `not UNKNOWN` | `UNKNOWN` · `FALSE` · `TRUE` · `UNKNOWN` · `UNKNOWN` |
| 44 | deux évaluations concurrentes du même sujet | même `decision_id` ; une seule action créée |
| 45 | sujet de l'organisation A évalué avec le contexte de B | `SUBJECT_NOT_FOUND` ; aucune ligne de A lue |
| 46 | `FREQUENCY_LIMIT` atteint, action manuelle, `OverrideGrant` `MANAGER` | `PROCEED`, `FREQUENCY_LIMIT` `OVERRIDDEN` |
| 47 | paiement de 100 000 non alloué, enregistré lundi, facture candidate, mardi, action **automatique** ; un `OverrideGrant` fourni | `SUPPRESS` `RECONCILIATION_PENDING` ; grant ignoré et consigné |
| 48 | même situation, action **manuelle** sans grant | `SUPPRESS` `RECONCILIATION_PENDING` |
| 49 | même situation, action manuelle, `OverrideGrant` `COLLECTOR` avec motif | `PROCEED`, `RECONCILIATION_PENDING` `OVERRIDDEN` |
| 50 | même paiement, évaluation le vendredi (jour local suivant le dernier jour de la fenêtre, jeudi) | `PROCEED` ; `reconciliation_stale = true` dans le bloc `reconciliation` |
| 51 | paiement non alloué **et** hold actif | `SUPPRESS` `HOLD_ACTIVE` (ordre 8 avant 13) ; `RECONCILIATION_PENDING` aussi consigné `FAILED` |
| 52 | action manuelle `SCHEDULED` avec grant `COLLECTOR` ; à l'exécution, l'acteur a été rétrogradé (ou désactivé) | `SUPPRESS` `RECONCILIATION_PENDING` ; cause `ROLE_INSUFFICIENT` (ou `ACTOR_INACTIVE`) dans l'audit ; aucun envoi |

---

## 11. Observable

| Signal | Contenu |
|---|---|
| **Compteurs** | `rule_evaluations_total{contexte, issue, suppression_code}` ; `rule_defer_total{cause}` ; `rule_unknown_fact_total{fait}` |
| **Histogrammes** | durée d'une évaluation ; durée de chargement des faits par famille ; taille des lots |
| **Qualité de données** | taux d'`UNKNOWN` par fait (un fait souvent inconnu signale un problème de données ou de calcul de projection) ; âge des projections au moment de l'évaluation |
| **Journaux structurés** | un par évaluation persistée : `organization_id`, `correlation_id`, `decision_id`, `outcome`, `engine_version`, durée ; **jamais** de donnée personnelle |
| **Traces distribuées** | un span par évaluation, rattaché à la chaîne événement → exécution → action |
| **Alertes** | pic de `SUPPRESS` d'un même code (par exemple `NO_CONSENT` soudain élevé) ; taux de `DEFER` croissant (projections en retard) ; échec de rejeu de décisions ; profondeur de causalité proche de la limite |
| **Tableau de bord d'explication** | répartition des `suppression_code` par organisation : « pourquoi n'envoie-t-on rien ? » |

Étiquettes de métriques : pas d'`organization_id` en étiquette (cardinalité) ; il figure dans les journaux et les traces.

---

## 12. Décisions

### R1–R8 : **VALIDÉES**

| # | Décision |
|---|---|
| R1 | Exceptions intégrées à ordre fixe ; le champ `exceptions` d'une définition ne fait qu'ajouter |
| R2 | Barrière de fraîcheur des projections (précisée par R13) |
| R3 | Exceptions d'intégrité non contournables ; exceptions métier contournables par une action manuelle motivée, sauf hold `LEGAL` (précisée par R10) |
| R4 | Faits temporels calculés depuis les dates |
| R5 | Fenêtre de comportement de 12 mois, échantillon minimal de 3 factures ; **figé** par la passe Risk / Priority / Cashflow (§5) |
| R6 | `SKIP` / `DEFER` au niveau déclencheur non persistés ; explication à la demande |
| R7 | Logique à trois valeurs ; `UNKNOWN` à la racine = non satisfait |
| R8 | Détection statique des boucles de déclenchement |

### Corrections issues de la revue : **APPLIQUÉES**

| # | Correction |
|---|---|
| R14 | `DRAFT` n'est pas `VOIDED` : étape 0 d'applicabilité, `SKIP` `NOT_ISSUED` ; `VOIDED` = `CANCELLED` ou `VOID` |
| R9 | `highest_level_reached` défini pour les 8 statuts (§2.4) |
| R10 | Override : `OverrideGrant` typée produite par le domaine, jamais un booléen (§3.3) |
| R13 | Contrat de projection : `refresh_events`, `computed_at` mis à jour à chaque recalcul, barrière limitée aux événements listés (§2.3) |
| R15 | Niveau initial `0` avant résolution ; sans condition vraie hors retard : `SKIP` `NO_LEVEL_MATCHED` (§8) |
| R16 | `decision_id` = hash de (`organization_id`, sujet, `as_of`, `engine_version`, `automation_version_id`, versions de modèles, `input_hash`) ; `primary_exception` distinct de `exceptions_trace` |
| R11 | Consentement : contact de référence = contact principal actif du canal, **sans repli** vers un autre contact (§2.2) |
| R12 | Promesse applicable : celle de la facture prime sur celle du client (§2.2) |

### À confirmer (choix de valeurs faits dans cette révision)

| # | Choix | Alternative |
|---|---|---|
| R9 | `FAILED` **ne compte pas** dans `highest_level_reached` | le compter empêcherait tout niveau inférieur après un échec |
| R10 | Rôles minimaux : `DISPUTED` et `HOLD_ACTIVE` → `MANAGER` ; `PROMISE_ACTIVE` → `COLLECTOR` ; `FREQUENCY_LIMIT` → `MANAGER` | à ajuster selon ta politique de rôles |
| R10 | `CUSTOMER_INACTIVE` non contournable (cohérence avec la matrice N3, que j'avais mal classée) ; `FREQUENCY_LIMIT` contournable (politique, pas obligation légale) | rendre `FREQUENCY_LIMIT` non contournable |
| R13 | Listes `refresh_events` **définitives** (RP7) ; délais de réessai de la barrière : 30 s / 2 min / 10 min / 30 min | fermé |

**Amendement Collection V1.2** (`COLLECTION_ENGINE_V1_2.md`, RN1 à RN12) : exception n° 13 ; faits `invoice.reconciliation_pending` et `_minor` ; grant revérifié à l'exécution pour toutes les exceptions contournables ; scénarios 47 à 52.

**Conséquences sur le contrat V1.3** (appliquées) : `IMPORT_HELD` ajouté aux codes de suppression ; `decision_snapshot` porte `primary_exception` et `overrides[]` ; `computed_at` des projections mis à jour à chaque recalcul.

## 13. Ce que reçoivent les passes suivantes

- **Collection Engine** : la table ordonnée de niveaux (mécanisme du §8, à remplir), l'applicabilité des exceptions par type d'action (§3.1), les issues d'évaluation (§6.1).
- **Automation Engine** : le langage de conditions (§4), la validation statique (§5), la traduction exception → pause/annulation/saut (§3.2), les contextes A et B (§7).
- **Risk / Priority** : les faits `PROJECTION` et la barrière de fraîcheur (§2.3), la définition provisoire des faits de comportement.
