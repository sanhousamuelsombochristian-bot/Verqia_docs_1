# VERQIA — Revue de cohérence V1

Périmètre : ERD V1 ↔ Data Contract V1 ↔ State Machines ↔ Event Model ↔ Rule Engine ↔ Collection Engine ↔ Cashflow Engine ↔ PostgreSQL/Django.
Résultat : Data Contract **V1.1** (corrections appliquées), depuis figé en V1.3.

Limites de cette revue :
- Les spécifications des Phases 1 à 5 et 7 ne sont pas dans ces fichiers. Je me suis appuyé sur la Phase 6 (Automation Engine), sur les règles rappelées dans la conversation et sur le Domain Model V1. Toute règle issue d'une phase que je n'ai pas relue est marquée « à confirmer ».
- Aucune migration ni requête SQL n'a été exécutée. Les points PostgreSQL/Django du §7 sont un raisonnement, à confirmer par un banc d'essai au démarrage du backend.

Légende : **[APPLIQUÉ]** corrigé dans le contrat V1.1 · **[À TRANCHER]** décision métier, rien n'est modifié.

---

## 1. ERD ↔ Data Contract

Contrôle mécanique (script) : 39 tables dans le contrat, 35 dessinées, 4 hors diagramme volontairement (`events`, `event_receipts`, `idempotency_keys`, `audit_logs`). Aucune table du diagramme n'est absente du contrat.

| # | Constat | Gravité | Statut |
|---|---|---|---|
| 1.1 | `collection_actions`, `promises` et `priority_items` référençaient `(org, invoice_id, customer_id)`, mais `invoices` n'avait pas la clé unique correspondante (elle incluait `currency`). Une FK ne peut viser que des colonnes couvertes par une clé unique : les migrations auraient échoué. | Bloquant | [APPLIQUÉ] UQ `(organization_id, id, customer_id)` |
| 1.2 | Les contraintes T1–T9 étaient citées mais définies uniquement dans la conversation. | Élevé | [APPLIQUÉ] §14 du contrat, T1–T12 |
| 1.3 | `automation_executions` et `automations.current_version_id` pouvaient pointer vers la version d'une **autre** automatisation. | Élevé | [APPLIQUÉ] UQ `(org, automation_id, id)` sur les versions, FK composites |
| 1.4 | `promises` : le XOR `invoice_id`/`customer_id` obligeait à une jointure pour compter les promesses rompues par client (Risk Engine) et laissait passer une facture d'un autre client. | Moyen | [APPLIQUÉ] `customer_id` toujours renseigné, FK composite |
| 1.5 | ERD : `risk_profiles` dessiné en `||--||` alors qu'un client peut ne pas avoir encore de profil. `collection_holds → automations`, `cashflow_lines → payments/customers` absents. | Faible | [APPLIQUÉ] ERD V1.1 |
| 1.6 | FK `*_by → users` non documentées dans l'ERD. | Faible | [APPLIQUÉ] section « Conventions non dessinées » |
| 1.7 | `customer_contacts` : UQ `(customer_id, channel, value)` bloquait la ressaisie d'un contact désactivé. | Faible | [APPLIQUÉ] UQ partiel `WHERE is_active` |

---

## 2. Data Contract ↔ State Machines

### 2.1 Facture — cycle de vie (`lifecycle_state`)

Transitions autorisées (à imposer dans le Domain, avec un trigger de garde optionnel en base) :

| De → Vers | Condition | Émet |
|---|---|---|
| `DRAFT → ISSUED` | lignes = total (T9), total > 0 | `INVOICE_ISSUED` |
| `DRAFT → CANCELLED` | — | `INVOICE_CANCELLED` |
| `ISSUED → DUE_SOON` | `due_date - due_soon_days <= today` | `INVOICE_DUE_SOON` |
| `ISSUED / DUE_SOON → DUE` | `due_date = today` | `INVOICE_DUE` |
| `ISSUED / DUE_SOON / DUE → OVERDUE` | `due_date < today` | `INVOICE_OVERDUE` |
| `ISSUED / DUE_SOON / DUE / OVERDUE → VOID` | `paid_minor = 0` | `INVOICE_VOIDED` |

Les sauts (`ISSUED → OVERDUE`) sont nécessaires : une facture importée ou émise après son échéance n'est jamais `DUE_SOON`. `CANCELLED` = annulée avant émission ; `VOID` = annulée après émission. Sans avoirs en V1, `VOID` exige zéro paiement net.

| # | Constat | Statut |
|---|---|---|
| 2.1.1 | Une facture `PAID` continuait à recevoir des transitions du Scheduler, ce qui la faisait devenir `OVERDUE` après règlement. | [APPLIQUÉ] règle de gel ; index Scheduler filtré sur `settlement_state <> 'PAID'` |
| 2.1.2 | Annulation d'une facture avec paiements : rien ne l'interdisait. | [APPLIQUÉ] CK `CANCELLED/VOID ⇒ paid_minor = 0` |
| 2.1.3 | `issued_at` « NN si ≠ DRAFT » contredisait `DRAFT → CANCELLED`. | [APPLIQUÉ] NN ⇔ état ∉ (`DRAFT`, `CANCELLED`) |
| 2.1.4 | `PARTIALLY_PAID` n'avait pas de contrainte propre (seuls `UNPAID` et `PAID` en avaient). | [APPLIQUÉ] CK à trois branches |
| 2.1.5 | Facture émise avec un total de 0 : `UNPAID` avec solde nul, état incohérent. | [APPLIQUÉ] CK total > 0 hors brouillon/annulée |
| 2.1.6 | Annulation d'un règlement sur une facture `PAID` gelée : `lifecycle_state` périmé (elle peut être en retard sans le savoir). | [APPLIQUÉ] recalcul immédiat depuis `due_date` |

### 2.2 Règlement (`settlement_state`)
`UNPAID ⇄ PARTIALLY_PAID ⇄ PAID`, uniquement via allocations et reversals (jamais par écriture directe). Toute transition est tracée dans `invoice_state_history` (`dimension='SETTLEMENT'`).

### 2.3 Paiement
| # | Constat | Statut |
|---|---|---|
| 2.3.1 | `payments.status` n'avait aucune contrainte le liant à `allocated_minor`. | [APPLIQUÉ] CK 4 branches |
| 2.3.2 | Un paiement `REVERSED` pouvait recevoir de nouvelles allocations. | [APPLIQUÉ] T10 |

### 2.4 Promesse
`ACTIVE → FULFILLED | BROKEN | CANCELLED` (terminal). `promise_history` couvre la traçabilité. Une promesse liée à une facture qui devient `PAID`, `VOID` ou `CANCELLED` doit être résolue automatiquement (handler, §3).

### 2.5 Action de recouvrement
| De → Vers | Condition |
|---|---|
| `PROPOSED → SCHEDULED` | revalidation OK |
| `PROPOSED → PENDING_APPROVAL` | approbation requise |
| `PENDING_APPROVAL → SCHEDULED` | approuvée |
| `PENDING_APPROVAL → CANCELLED` | rejetée ou expirée |
| `SCHEDULED → EXECUTING → DONE` | succès |
| `EXECUTING → SCHEDULED` | échec, tentatives restantes (`next_retry_at`) |
| `EXECUTING → FAILED` | tentatives épuisées (`max_attempts`) |
| `PROPOSED / SCHEDULED → SUPPRESSED` | revalidation échoue (exception métier) |
| tout état non terminal `→ CANCELLED` | annulation explicite |

`SUPPRESSED` = le système a constaté qu'une exception métier s'applique ; `CANCELLED` = décision d'un acteur. [APPLIQUÉ] `suppression_code` structuré (`PAID`, `VOIDED`, `DISPUTED`, `PROMISE_ACTIVE`, `HOLD_ACTIVE`, `FREQUENCY_LIMIT`, `NO_CONSENT`, `ORG_INACTIVE`) au lieu d'un texte libre, pour que l'explicabilité soit exploitable.

### 2.6 Automatisation et exécution
- Automatisation : `DRAFT → ACTIVE ⇄ PAUSED`, `ACTIVE/PAUSED → DISABLED → ARCHIVED`, `DRAFT → ARCHIVED`.
- Exécution : `PENDING → RUNNING → WAITING → RUNNING …`, terminaux `COMPLETED / FAILED / CANCELLED`, `PAUSED` réversible.
- Règle : si l'automatisation n'est plus `ACTIVE` au réveil d'une exécution `WAITING`, l'exécution passe en `PAUSED` (`status_reason='AUTOMATION_PAUSED'`). À la reprise, elle repart en `PENDING` et **revalide** avant chaque étape.

---

## 3. Data Contract ↔ Event Model

### 3.1 Rôle de chaque mécanisme (à ne pas confondre)
| Mécanisme | Rôle | Écrit par |
|---|---|---|
| `*_history` | chronologie d'état d'une entité | l'agrégat, dans la transaction |
| `events` | notification réactive entre modules | l'agrégat, dans la transaction (outbox) |
| `audit_logs` | qui a fait quoi, avant/après, pourquoi | le use case, dans la transaction |

### 3.2 Événements consommés (matrice à figer)
| Événement | Consommateurs |
|---|---|
| `INVOICE_ISSUED` | risk, priority, cashflow |
| `INVOICE_DUE_SOON`, `INVOICE_DUE` | automation, priority, cashflow |
| `INVOICE_OVERDUE` | automation, risk, priority, cashflow |
| `INVOICE_PARTIALLY_PAID`, `INVOICE_PAID` | risk, priority, cashflow, promises (vérification), collections (suppression des actions en attente), automation (arrêt des exécutions) |
| `INVOICE_SETTLEMENT_REVERTED` | invoices (recalcul du cycle de vie), risk, priority, cashflow, collections |
| `INVOICE_DISPUTED` / `INVOICE_DISPUTE_RESOLVED` | collections, automation, priority, cashflow |
| `INVOICE_VOIDED`, `INVOICE_CANCELLED` | promises (annulation), collections (annulation), priority (retrait), automation (annulation), cashflow |
| `PAYMENT_CREATED` | payments (rapprochement automatique, si activé) |
| `PAYMENT_ALLOCATED`, `PAYMENT_ALLOCATION_REVERSED` | risk, promises, cashflow |
| `PAYMENT_REVERSED` | risk, priority, promises, collections, cashflow |
| `PROMISE_CREATED` | collections, automation, priority, cashflow |
| `PROMISE_BROKEN` | risk, priority, automation, collections, cashflow |
| `PROMISE_FULFILLED` | risk, collections, cashflow |
| `COLLECTION_HOLD_PLACED` / `_RELEASED` | collections, automation, priority |
| `COLLECTION_ACTION_EXECUTED` | notifications |
| `RISK_CHANGED` | priority, automation, cashflow |
| `PRIORITY_CHANGED` | automation, notifications |
| `CASHFLOW_UPDATED` | automation |
| `CUSTOMER_ARCHIVED` | collections, automation |

Chaque consommateur = un `handler_name` stable, consigné dans `event_receipts`.

### 3.3 Constats
| # | Constat | Statut |
|---|---|---|
| 3.3.1 | **Déclencheurs temporels** (« 10 jours après l'échéance ») : `automation_executions.trigger_event_id NN` supposait un événement pour chaque déclencheur, or il n'y en a pas pour un simple décalage. | [APPLIQUÉ] `trigger_key` (NN) ; UQ `(automation_id, trigger_key, subject_id)` ; `trigger_event_id` devient nullable |
| 3.3.2 | Idempotence des événements du Scheduler : une déduplication par clé sur `events` est **impossible** (table partitionnée, l'unicité doit inclure `occurred_at`). | [APPLIQUÉ] règle documentée ; émission uniquement sur transition gardée (`UPDATE … WHERE état = ancien`) |
| 3.3.3 | Boucle possible : `RISK_CHANGED → priority → PRIORITY_CHANGED → automation → action → …`. | [APPLIQUÉ] `causation_depth` (≤ 20) ; `RISK_CHANGED` émis seulement sur changement de **niveau** |
| 3.3.4 | Événements potentiellement livrés dans le désordre ou obsolètes. | [APPLIQUÉ] `aggregate_version` ; principe « un événement est une notification, les handlers relisent l'état » |
| 3.3.5 | `dedup_key` des actions de recouvrement non spécifiée. | [APPLIQUÉ] formule `{invoice_id}:{type}:L{level}:C{cycle}` |
| 3.3.6 | Politique d'audit : trois écritures pour un même fait. | [À TRANCHER] proposition ci-dessous |

**Proposition D3 (audit).** `audit_logs` : toute **commande** utilisateur ou automatisation, tout changement de configuration, de droits, de hold et d'approbation, écrits dans la transaction. Les transitions purement temporelles du Scheduler (`DUE_SOON`, `DUE`, `OVERDUE`) vont dans `invoice_state_history` et `events` seulement, pour ne pas noyer l'audit.

---

## 4. Data Contract ↔ Rule Engine

### 4.1 Faits requis et leur source
| Fait | Source de vérité | Note |
|---|---|---|
| jours de retard | `due_date` + horloge + fuseau org | jamais stocké |
| solde | `invoices.outstanding_minor` (généré) | dérivé de `paid_minor`, vérifié par T4 |
| exposition client | somme des soldes des factures ouvertes | index couvrant ajouté |
| délai réel de paiement | `settled_on - due_date` | [APPLIQUÉ] `settled_on` = `payments.value_date`, pas la date de saisie de l'allocation |
| fréquence de retard | factures avec `settled_on > due_date` | idem |
| promesses rompues par client | `promises` (`customer_id`, `status='BROKEN'`) | [APPLIQUÉ] index `(org, customer_id, status)` |
| montant recouvrable | `outstanding_minor - disputed_amount_minor` (litige ouvert) | voir D1 |
| exceptions (ordre de priorité) | intégrité/org → `CANCELLED/VOID` → `PAID` → litige ouvert → promesse active → hold | toutes lisibles en base |

### 4.2 Constats
| # | Constat | Statut |
|---|---|---|
| 4.2.1 | Le délai de paiement était calculé sur la date de saisie de l'allocation, donc faussé quand un comptable affecte un paiement en retard. | [APPLIQUÉ] `settled_on` |
| 4.2.2 | Un hold expiré mais non encore marqué `EXPIRED` par le Scheduler aurait continué à bloquer. | [APPLIQUÉ] règle de lecture basée sur `starts_at/ends_at` |
| 4.2.3 | `EXCLUDE` des holds : `coalesce(invoice_id, customer_id)` est NULL pour la portée organisation, donc jamais comparé. | [APPLIQUÉ] `coalesce(…, organization_id)` |
| 4.2.4 | « Suspendre pour ce client **cette** relance » (Phase 6 §28) n'était pas représentable : un hold s'appliquait à toutes les automatisations. | [APPLIQUÉ] `collection_holds.automation_id` |
| 4.2.5 | Le cache `automations.trigger_type` pouvait diverger de la version courante. | [APPLIQUÉ] colonne générée sur `automation_versions` |

### 4.3 Décisions à trancher
- **D1 — Litige partiel.** La décision n°4 dit « recouvrer la part non contestée », mais l'invariant de la Phase 6 dit « facture `DISPUTED` suspend le recouvrement standard ». Ils se contredisent pour un litige partiel. **Recommandation** : litige total (`disputed_amount_minor IS NULL`) ⇒ suspension ; litige partiel ⇒ le recouvrement continue sur `outstanding − disputed_amount` et suspend seulement si ce montant est ≤ 0. Côté cashflow, la part contestée va en `AT_RISK`.
- **D2 — `UPDATE_PRIORITY`.** Cette action de la Phase 6 contredit le fait que `priority_items` est une projection recalculable. **Recommandation** : la remplacer par `REQUEST_PRIORITY_RECALCULATION` ; pas de surcharge manuelle de priorité en V1.

---

## 5. Data Contract ↔ Collection Engine

### 5.1 Correspondance avec la liste blanche d'actions (Phase 6)
| Action | Support dans le contrat |
|---|---|
| `CREATE_TASK`, `ASSIGN_TASK` | `collection_actions` (`CALL_TASK`, `FOLLOW_UP`) + `assigned_to` |
| `CREATE_COLLECTION_ACTION`, `CREATE_REMINDER` | `collection_actions` (`REMINDER`, …) |
| `CREATE_NOTIFICATION`, `CREATE_MANAGER_ALERT` | `notifications` |
| `ESCALATE` | `collection_actions` type `ESCALATION` + notification |
| `REQUEST_APPROVAL`, `REQUEST_REVIEW` | `approvals` [APPLIQUÉ] `kind IN ('APPROVAL','REVIEW')` |
| `REQUEST_RISK_RECALCULATION`, `REQUEST_CASHFLOW_RECALCULATION` | commande vers worker ; événements de demande |
| `WAIT`, `DELAY`, `BRANCH`, `STOP`, `PAUSE` | états et étapes d'`automation_executions` |
| `UPDATE_PRIORITY` | voir D2 |

### 5.2 Constats
| # | Constat | Statut |
|---|---|---|
| 5.2.1 | Doublon de concept : `MANAGER_ALERT` existe à la fois comme type d'action et comme notification. | [À TRANCHER] D5 : une alerte responsable est une notification ; on retire `MANAGER_ALERT` des types d'action |
| 5.2.2 | Niveaux 1–5 non définis. | [À TRANCHER] D4 |
| 5.2.3 | Où vit la stratégie de recouvrement (seuils, niveaux, canaux) ? Aucune table ne la porte. | [À TRANCHER] D4 |
| 5.2.4 | Limite de fréquence (`max_reminders_per_30d`) : requête sur `collection_actions` sans index adapté. | [APPLIQUÉ] index `(org, invoice_id, status)` |
| 5.2.5 | Le consentement (`NO_CONSENT`) et l'organisation inactive (`ORG_INACTIVE`) n'avaient pas de motif de suppression. | [APPLIQUÉ] codes de suppression |

**Proposition D4 (niveaux).**
| Niveau | Sens | Exemple de déclenchement |
|---|---|---|
| 1 | Rappel courtois | avant/à l'échéance |
| 2 | Relance standard | retard modéré |
| 3 | Relance ferme, contact humain | retard significatif ou risque HIGH |
| 4 | Mise en demeure | retard grave, avec approbation |
| 5 | Escalade direction / contentieux | critique, avec approbation |

La stratégie (seuils, canaux, gabarits par niveau) vit dans les **définitions d'automatisation** versionnées, avec une automatisation modèle créée à l'ouverture de chaque organisation. `decision_snapshot` référence la version de cette définition. Aucune table `collection_policies` supplémentaire en V1.

---

## 6. Data Contract ↔ Cashflow Engine

| Catégorie | Source | Champs |
|---|---|---|
| `REALIZED` | paiements non `REVERSED` | `payments.value_date`, `amount_minor` |
| `EXPECTED` | factures ouvertes non contestées | `due_date`, `outstanding_minor` ; décalage selon le comportement historique |
| `PROBABLE` | factures en retard avec promesse ou comportement favorable | `promises.promised_date`, `promised_amount_minor`, probabilité |
| `AT_RISK` | litige, risque critique | part contestée, `risk_profiles.level` |

| # | Constat | Statut |
|---|---|---|
| 6.1 | Une ligne `REALIZED` n'avait aucune référence vers le paiement d'origine. | [APPLIQUÉ] `source_payment_id` + CK |
| 6.2 | `probability` seule ne permettait pas de sommer des montants pondérés. | [APPLIQUÉ] `weighted_minor` (colonne générée) |
| 6.3 | `cashflow_lines.currency` dupliquait `cashflow_runs.currency` sans FK. | [APPLIQUÉ] colonne supprimée |
| 6.4 | Un run `FAILED` pouvait être marqué `is_current`. Horizons libres. | [APPLIQUÉ] CK `is_current ⇒ COMPLETED`, horizons `IN (7,30,60,90,180,365)` |
| 6.5 | La bascule de `is_current` échouerait sur l'index unique partiel si l'ordre des `UPDATE` est mauvais (un index unique partiel ne peut pas être différé). | [APPLIQUÉ] ordre imposé dans le contrat |

---

## 7. Vérification PostgreSQL / Django

Hypothèses de base : PostgreSQL 16 ou plus, Django 5.2 LTS. Les fonctionnalités marquées (*) sont à confirmer par un banc d'essai au démarrage du backend, car je ne les ai pas exécutées ici.

| Sujet | Verdict | Détail |
|---|---|---|
| UUIDv7 | OK | Généré côté application (`uuid.uuid7()` en Python 3.14 (*), sinon une bibliothèque). PostgreSQL 18 offre `uuidv7()` (*) si on veut un défaut en base pour les scripts d'administration. `UUIDField(default=new_id)`. |
| `bigint` | OK | `BigIntegerField`. |
| `jsonb` | OK | `JSONField`. Les `CHECK jsonb_typeof` passent par `CheckConstraint`. |
| `timestamptz` | OK | `USE_TZ = True`. |
| `citext`, trigram, `btree_gist` | OK | Extensions à créer en première migration (`CITextExtension`, `TrigramExtension`, `BtreeGistExtension`). Le rôle de migration doit pouvoir les créer. |
| Colonnes générées | OK | `GeneratedField(db_persist=True)` pour `outstanding_minor`, `weighted_minor`, `automation_versions.trigger_type`. Après `save()`, relire la valeur : Django ne la renvoie pas toujours sans `refresh_from_db()` (*). |
| FK composites | **À traiter** | Django ne crée pas de FK composite. Approche : `ForeignKey(db_constraint=False)` pour la navigation ORM, plus les contraintes composites posées en SQL (`RunSQL`). Toute migration qui touche ces tables doit passer en revue le SQL correspondant. |
| FK différées | OK | Django crée les FK PostgreSQL en `DEFERRABLE INITIALLY DEFERRED` par défaut, ce qui convient à `automations.current_version_id`. |
| Contraintes différées T1–T6, T9–T12 | **À traiter** | `CREATE CONSTRAINT TRIGGER … DEFERRABLE INITIALLY DEFERRED` via `RunSQL`, versionnés dans un dossier `sql/`. Les tests doivent tourner sur PostgreSQL, jamais SQLite. |
| Triggers d'immutabilité | **À traiter** | `BEFORE UPDATE OR DELETE` ne se déclenche pas sur `TRUNCATE` : révoquer `TRUNCATE` au rôle applicatif. Les `TransactionTestCase` (flush par `TRUNCATE`) exigent un rôle de test dédié. |
| `EXCLUDE` (holds) | OK | `ExclusionConstraint` de `django.contrib.postgres`, avec `btree_gist`. |
| Partitions (`events`, `audit_logs`) | **À traiter** | Tables créées par `RunSQL`, clé primaire `(id, occurred_at)` (`CompositePrimaryKey`, Django 5.2 (*)). Un job planifié crée les partitions à l'avance, plus une partition `DEFAULT` de secours et une alerte si elle reçoit des lignes. |
| Row-Level Security | **À traiter** | `SET LOCAL app.organization_id` en début de transaction (middleware et workers). Le rôle applicatif ne doit **pas** être propriétaire des tables (sinon il contourne RLS) ou utiliser `FORCE ROW LEVEL SECURITY`. Rôle de migration ≠ rôle d'exécution. Compatible avec un pooler en mode transaction. |
| Verrou optimiste `version` | À implémenter | Django n'en fournit pas : `UPDATE … WHERE id=… AND version=…` dans les repositories. |
| `updated_at` | OK | Trigger `set_updated_at()`, car `auto_now` ne joue pas sur `update()` ni `bulk_update()`. |
| Enums texte + CHECK | OK | `TextChoices` + `CheckConstraint`. |

---

## 8. Décisions

Ce tableau est **remplacé** : toutes les décisions D1 à D9 et N1 à N14 sont désormais fermées. L'état à jour figure dans `INVARIANTS_V1.md` §11 et dans l'en-tête du Data Contract V1.3 (figé). Ce document reste la trace de la revue de cohérence initiale.
