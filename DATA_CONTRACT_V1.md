# VERQIA — Data Contract V1.3

Statut : **V1.3 — FIGÉ** (amendements consignés en §20, jusqu'à Collection V1.2). Décisions verrouillées : D1 (litige), D2 (pas de `UPDATE_PRIORITY`), D3 (audit), D5 (pas de `MANAGER_ALERT` comme action), D6 (archivage), D9 (principe des deux chemins de création), N6, N7, N11, N13, N14 (import par lots). Voir §14, §15 et §20.
Restent à **spécifier** (et non à décider) : les détails opérationnels de l'import, les valeurs de la stratégie de recouvrement par défaut, les préconditions détaillées d'activation d'une automatisation. Ils n'ajoutent aucune colonne.
Références : Domain Model V1, ERD V1 (`ERD_V1.md`), Revue de cohérence (`REVIEW_COHERENCE_V1.md`), Invariants (`INVARIANTS_V1.md`).

---

## 0. Décisions de typage

| Sujet | Décision |
|---|---|
| Montants | `bigint` en unité mineure. Suffixe de colonne `_minor`. Jamais `float`/`numeric` pour de l'argent. |
| Devise | `char(3)` ISO 4217, majuscules (`CHECK (currency ~ '^[A-Z]{3}$')`). |
| UUID | UUIDv7 **généré côté application** (fonction utilitaire unique `new_id()`). Colonne `uuid`, sans défaut en base. |
| Dates / horodatages | `date` pour les dates métier (échéance, émission). `timestamptz` (UTC) pour tout instant. |
| Énumérations | `text` + `CHECK (col IN (...))`. Pas d'enum PostgreSQL natif. |
| JSON | `jsonb`, avec `CHECK (jsonb_typeof(col) = 'object')` (ou `'array'`) quand la forme est connue. |
| Texte insensible à la casse | `citext` pour `users.email`. |
| Suppression | `ON DELETE RESTRICT` sur **toutes** les FK. Aucun `CASCADE`. |
| FK composites | **Verrouillé.** Django : `ForeignKey(db_constraint=False)` pour la navigation ORM ; contraintes composites `(organization_id, x_id)` posées en SQL (`RunSQL`), sans doublon avec une FK simple. |
| Colonnes générées | **Verrouillé.** `GeneratedField(db_persist=True)` : `outstanding_minor`, `weighted_minor`, `automation_versions.trigger_type`. |
| Acteur | `*_by` : `uuid NULL` → `users.id` (NULL = action système). Quand l'origine compte, ajouter `actor_type IN ('USER','SYSTEM','AUTOMATION')`. |

### Colonnes standard (déclarées une fois, non répétées ensuite)

| Sigle | Colonnes incluses |
|---|---|
| **STD** | `id uuid PK` · `organization_id uuid NN` · `created_at timestamptz NN default now()` · `updated_at timestamptz NN default now()` |
| **STD+V** | STD + `version integer NN default 1` (verrou optimiste, `CHECK version >= 1`) |
| **APP** (append-only) | `id uuid PK` · `organization_id uuid NN` · `created_at timestamptz NN default now()` — **pas** de `updated_at` |

Implicites sur toute table STD/STD+V/APP :
- `UNIQUE (organization_id, id)` (cible des FK composites).
- FK vers l'organisation : `organization_id → organizations(id)`.
- Toute FK métier est **composite** : `(organization_id, x_id) → parent(organization_id, id)`.
- Toute FK a un index couvrant, préfixé par `organization_id`.
- `updated_at` maintenu par trigger `set_updated_at()`.

Légende des colonnes de tableaux : **NN** = NOT NULL · **—** = pas de défaut.

Légende « Nature » : **SOURCE** = source de vérité · **CACHE** = colonne dérivée reconstructible · **PROJ** = projection/calcul reconstructible · **LOG** = historique immuable.

---

## 1. Identity & tenancy

### 1.1 `organizations` — STD+V (l'`id` EST le tenant, pas de `organization_id`)
Propriétaire : `organizations` · Nature : SOURCE · Événements : `ORGANIZATION_CREATED`, `ORGANIZATION_UPDATED`, `ORGANIZATION_SUSPENDED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| name | text | NN | — | longueur 1–200 |
| slug | text | NN | — | UNIQUE ; `^[a-z0-9-]{3,63}$` |
| default_currency | char(3) | NN | — | devise unique de l'org en V1 |
| timezone | text | NN | 'UTC' | IANA, validé en application |
| country | char(2) | NN | — | ISO 3166-1 alpha-2 |
| status | text | NN | 'PROVISIONING' | `PROVISIONING, ACTIVE, SUSPENDED, CLOSED` ; T14 : `PROVISIONING → ACTIVE`, `PROVISIONING → CLOSED`, `ACTIVE ⇄ SUSPENDED`, `ACTIVE/SUSPENDED → CLOSED` |

Index : UQ `slug`.

### 1.2 `users` — table globale (pas de `organization_id`)
Propriétaire : `identity` · Nature : SOURCE · Événements : `USER_CREATED`, `USER_STATUS_CHANGED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| id | uuid | NN | — | PK |
| email | citext | NN | — | UNIQUE |
| password_hash | text | NULL | — | NULL si SSO |
| full_name | text | NN | — | |
| locale | text | NN | 'fr' | |
| status | text | NN | 'ACTIVE' | `ACTIVE, INVITED, DISABLED` |
| last_login_at | timestamptz | NULL | — | |
| anonymized_at | timestamptz | NULL | — | PII : voir §17 ; NN ⇒ `status='DISABLED'` |
| created_at, updated_at | timestamptz | NN | now() | |

### 1.3 `memberships` — STD+V
Propriétaire : `identity` · Nature : SOURCE · Événements : `MEMBER_ADDED`, `MEMBER_ROLE_CHANGED`, `MEMBER_REMOVED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| user_id | uuid | NN | — | FK `users(id)` (non composite : table globale) |
| role | text | NN | — | `OWNER, ADMIN, MANAGER, COLLECTOR, VIEWER` |
| status | text | NN | 'ACTIVE' | `ACTIVE, SUSPENDED, REMOVED` |
| approval_limit_minor | bigint | NULL | — | `>= 0` ; NULL = pas de droit d'approbation |

Contraintes : UQ `(organization_id, user_id)`. Index : `(user_id)`.
Règle applicative : au moins un `OWNER` actif par organisation.

### 1.4 `org_settings` — STD+V (1 ligne par org)
Propriétaire : `organizations` · Nature : SOURCE · Événements : `ORG_SETTINGS_CHANGED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| critical_amount_minor | bigint | NN | 0 | `>= 0` ; seuil « montant critique » |
| due_soon_days | smallint | NN | 7 | `BETWEEN 0 AND 90` |
| promise_grace_days | smallint | NN | 2 | `BETWEEN 0 AND 30` |
| comm_window_start | time | NN | '08:00' | heure locale de l'org |
| comm_window_end | time | NN | '18:00' | `> comm_window_start` |
| business_days | smallint[] | NN | '{1,2,3,4,5}' | valeurs 1–7 (ISO) |
| max_reminders_per_30d | smallint | NN | 4 | `>= 0` par facture |
| approval_min_risk_level | text | NULL | 'CRITICAL' | `LOW, MEDIUM, HIGH, CRITICAL` ou NULL |
| extra | jsonb | NN | '{}' | objet ; réglages secondaires. Clés documentées : `max_customer_messages_per_day` (2), `send_rate_per_hour` (200), `approval_expiry_hours` (72), `task_sla_days` (3), `enroll_max_per_day` (100), `reconciliation_hold_business_days` (3 ; entier de 1 à 10 : fenêtre de suspension par un paiement non alloué, en jours ouvrés du calendrier de l'organisation, Collection V1.2 RN5) |

Contraintes : UQ `organization_id`.

### 1.5 `org_holidays` — STD
Propriétaire : `organizations` · Nature : SOURCE

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| day | date | NN | — | |
| label | text | NN | — | |

Contraintes : UQ `(organization_id, day)`.

---

## 2. Customers

### 2.1 `customers` — STD+V
Propriétaire : `customers` · Nature : SOURCE · Événements : `CUSTOMER_CREATED`, `CUSTOMER_UPDATED`, `CUSTOMER_DEACTIVATED`, `CUSTOMER_ARCHIVED`, `CUSTOMER_REACTIVATED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| code | text | NN | — | UQ par org ; 1–50 |
| legal_name | text | NN | — | |
| tax_id | text | NULL | — | |
| external_ref | text | NULL | — | id dans un système externe |
| status | text | NN | 'ACTIVE' | `ACTIVE, INACTIVE, ARCHIVED` |
| archived_at | timestamptz | NULL | — | `(status='ARCHIVED') = (archived_at IS NOT NULL)` |
| anonymized_at | timestamptz | NULL | — | PII : voir §17 (personne physique / entrepreneur individuel) ; NN ⇒ `status='ARCHIVED'` |
| import_batch_id | uuid | NULL | — | FK composite `import_batches` ; NN si créé par import |
| created_by | uuid | NULL | — | FK `users` |

Contraintes : UQ `(organization_id, code)` · UQ partiel `(organization_id, external_ref) WHERE external_ref IS NOT NULL`.
Index : `(organization_id, status)` · GIN trigram `legal_name`.
Garde d'archivage (D6) : `ACTIVE/INACTIVE → ARCHIVED` est refusé s'il existe une facture en `DRAFT`, `ISSUED`, `DUE_SOON`, `DUE` ou `OVERDUE` dont le règlement n'est pas `PAID`. Si un reversal rouvre ensuite une facture, elle reste non recouvrable automatiquement (`CUSTOMER_ARCHIVED`), une notification `CUSTOMER_ARCHIVED_BALANCE_REOPENED` est envoyée aux `ADMIN`, et le client n'est **jamais** réactivé automatiquement.
**Aucun** solde, encours ou retard stocké ici.

### 2.2 `customer_contacts` — STD
Propriétaire : `customers` · Nature : SOURCE · Événements : `CUSTOMER_CONTACT_ADDED`, `CUSTOMER_CONTACT_UPDATED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| customer_id | uuid | NN | — | FK composite |
| name | text | NN | — | |
| channel | text | NN | — | `EMAIL, PHONE, WHATSAPP, SMS` |
| value | text | NN | — | format validé selon `channel` en application |
| is_primary | boolean | NN | false | |
| is_active | boolean | NN | true | remplace la suppression |
| consent_status | text | NN | 'UNKNOWN' | `UNKNOWN, GRANTED, DENIED, WITHDRAWN` |
| consent_updated_at | timestamptz | NULL | — | NN si `consent_status <> 'UNKNOWN'` |
| preferred_language | char(2) | NN | 'fr' | |
| anonymized_at | timestamptz | NULL | — | PII : voir §17 ; NN ⇒ `is_active=false AND consent_status='WITHDRAWN'` |

Contraintes : UQ partiel `(customer_id, channel) WHERE is_primary AND is_active` · UQ partiel `(customer_id, channel, value) WHERE is_active` (un contact désactivé ne bloque pas une ressaisie).
Index : `(organization_id, customer_id)`.

---

## 3. Invoices

### 3.1 `invoices` — STD+V
Propriétaire : `invoices` · Nature : SOURCE (`paid_minor`, `settlement_state`, `settled_on` = CACHE de `payment_allocations`)
Événements : `INVOICE_CREATED`, `INVOICE_ISSUED`, `INVOICE_DUE_SOON`, `INVOICE_DUE`, `INVOICE_OVERDUE`, `INVOICE_PARTIALLY_PAID`, `INVOICE_PAID`, `INVOICE_SETTLEMENT_REVERTED`, `INVOICE_CANCELLED`, `INVOICE_VOIDED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| customer_id | uuid | NN | — | FK composite `(organization_id, customer_id)` |
| number | text | NN | — | UQ par org |
| currency | char(3) | NN | — | = `organizations.default_currency` en V1 (contrôle applicatif) |
| issue_date | date | NN | — | |
| due_date | date | NN | — | `>= issue_date` |
| total_minor | bigint | NN | — | `>= 0` |
| paid_minor | bigint | NN | 0 | CACHE ; `0 <= paid_minor <= total_minor` |
| outstanding_minor | bigint | NN | généré | `GENERATED ALWAYS AS (total_minor - paid_minor) STORED` |
| lifecycle_state | text | NN | 'DRAFT' | `DRAFT, ISSUED, DUE_SOON, DUE, OVERDUE, CANCELLED, VOID` |
| settlement_state | text | NN | 'UNPAID' | CACHE ; `UNPAID, PARTIALLY_PAID, PAID` |
| state_changed_at | timestamptz | NN | now() | dernier changement de `lifecycle_state` |
| collection_cycle | smallint | NN | 0 | `>= 0` ; incrémenté par le Domain (a) à l'entrée en `OVERDUE`, (b) à l'annulation d'un règlement quand le cycle de vie est déjà `OVERDUE` ; jamais décrémenté. Structure `dedup_key` et la non-régression des niveaux |
| issued_at | timestamptz | NULL | — | NN ⇔ état ∉ (`DRAFT`, `CANCELLED`) |
| settled_on | date | NULL | — | CACHE ; NN ⇔ `settlement_state='PAID'` ; = `value_date` du paiement qui a soldé la facture (date réelle de règlement, pas la date de saisie de l'allocation) |
| cancelled_at | timestamptz | NULL | — | NN si `CANCELLED`/`VOID` (date d'annulation, pour les deux) |
| cancel_reason | text | NULL | — | NN si `CANCELLED`/`VOID` |
| external_ref | text | NULL | — | |
| origin | text | NN | 'NATIVE' | `NATIVE, IMPORTED` |
| import_batch_id | uuid | NULL | — | FK composite `import_batches` ; `(origin='IMPORTED') = (import_batch_id IS NOT NULL)` |
| notes | text | NULL | — | |
| created_by | uuid | NULL | — | |

Contraintes :
- UQ `(organization_id, number)`.
- UQ `(organization_id, id, customer_id, currency)` — cible des FK d'allocation.
- UQ `(organization_id, id, customer_id)` — cible des FK « même client » (`collection_actions`, `promises`, `priority_items`).
- CK règlement, trois branches exclusives :
  - `settlement_state='UNPAID' ⇔ paid_minor = 0`
  - `settlement_state='PAID' ⇔ paid_minor = total_minor AND total_minor > 0`
  - `settlement_state='PARTIALLY_PAID' ⇔ paid_minor > 0 AND paid_minor < total_minor`
- CK `lifecycle_state IN ('DRAFT','CANCELLED') ⇒ paid_minor = 0`.
- CK `lifecycle_state IN ('CANCELLED','VOID') ⇒ paid_minor = 0` : une facture ne peut être annulée que si toutes ses allocations ont été reversées (pas d'avoirs en V1).
- CK `lifecycle_state IN ('ISSUED','DUE_SOON','DUE','OVERDUE') ⇒ total_minor > 0`.
- CK `(settlement_state='PAID') = (settled_on IS NOT NULL)`.
- Contrainte différée T4 (cache = somme des allocations).
- Trigger T13 : après émission, `number`, `customer_id`, `currency`, `issue_date`, `due_date` et `total_minor` sont immuables (voir §14).

Rattrapage à l'émission (S3) : `DRAFT → ISSUED` applique, dans la même transaction, les transitions temporelles déjà applicables à la date courante de l'organisation (une facture émise en retard n'attend pas le Scheduler). Chaque transition effectivement réalisée écrit sa ligne d'historique et émet son événement.

Règle de gel : le Scheduler ne fait plus avancer `lifecycle_state` d'une facture `PAID`. Une facture soldée en retard reste `OVERDUE + PAID`. Si le règlement est annulé (`INVOICE_SETTLEMENT_REVERTED`), `lifecycle_state` est recalculé immédiatement depuis `due_date`.

Index : `(organization_id, lifecycle_state, due_date)` · `(organization_id, customer_id) INCLUDE (outstanding_minor, due_date) WHERE settlement_state <> 'PAID' AND lifecycle_state IN ('ISSUED','DUE_SOON','DUE','OVERDUE')` (exposition client) · `(organization_id, due_date) WHERE settlement_state <> 'PAID' AND lifecycle_state IN ('ISSUED','DUE_SOON','DUE')` (transitions du Scheduler).

### 3.2 `invoice_items` — STD
Propriétaire : `invoices` · Nature : SOURCE · Événements : (portés par `INVOICE_*`)

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| invoice_id | uuid | NN | — | FK composite |
| position | integer | NN | — | `>= 1` |
| description | text | NN | — | |
| quantity | numeric(18,4) | NN | — | `> 0` |
| unit_price_minor | bigint | NN | — | `>= 0` |
| line_total_minor | bigint | NN | — | `= round(quantity * unit_price_minor)` |

Contraintes : UQ `(invoice_id, position)` · trigger T7 (immuable hors `DRAFT`) · T9 (`SUM = total_minor` à l'émission).

### 3.3 `invoice_state_history` — APP (+ `occurred_at`)
Propriétaire : `invoices` · Nature : LOG

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| invoice_id | uuid | NN | — | FK composite |
| dimension | text | NN | — | `LIFECYCLE, SETTLEMENT` |
| from_state | text | NULL | — | NULL à la création |
| to_state | text | NN | — | |
| reason | text | NULL | — | |
| actor_id | uuid | NULL | — | |
| actor_type | text | NN | — | `USER, SYSTEM, AUTOMATION` |
| event_id | uuid | NULL | — | référence logique (pas de FK) |
| occurred_at | timestamptz | NN | now() | |

Index : `(invoice_id, occurred_at)`. Append-only (T8).

### 3.4 `invoice_disputes` — STD+V
Propriétaire : `invoices` · Nature : SOURCE · Événements : `INVOICE_DISPUTED`, `INVOICE_DISPUTE_RESOLVED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| invoice_id | uuid | NN | — | FK composite |
| status | text | NN | 'OPEN' | `OPEN, RESOLVED_VALID, RESOLVED_REJECTED` |
| reason | text | NN | — | |
| disputed_amount_minor | bigint | NULL | — | NULL = litige total ; `> 0` ; `<= invoice.total_minor` (trigger) |
| opened_by | uuid | NN | — | |
| opened_at | timestamptz | NN | now() | |
| resolved_by | uuid | NULL | — | |
| resolved_at | timestamptz | NULL | — | NN ⇔ `status <> 'OPEN'` |
| resolution_note | text | NULL | — | |

Contraintes : UQ partiel `(invoice_id) WHERE status='OPEN'`.
Montant recouvrable (D1, verrouillé) : `collectible_minor = outstanding_minor` sans litige ouvert ; `0` si un litige ouvert a `disputed_amount_minor IS NULL` (litige total) ; sinon `max(outstanding_minor - disputed_amount_minor, 0)`. Le recouvrement standard est suspendu si et seulement si `collectible_minor = 0`. Un litige partiel n'interrompt donc pas le recouvrement de la part non contestée. Côté cashflow, la part contestée (`min(disputed_amount_minor, outstanding_minor)`) est en `AT_RISK`.

---

## 4. Payments

### 4.1 `payments` — STD+V
Propriétaire : `payments` · Nature : SOURCE (`allocated_minor`, `status` = CACHE)
Événements : `PAYMENT_CREATED`, `PAYMENT_ALLOCATED`, `PAYMENT_ALLOCATION_REVERSED`, `PAYMENT_REVERSED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| customer_id | uuid | NN | — | FK composite |
| currency | char(3) | NN | — | |
| reference | text | NN | — | référence bancaire |
| method | text | NN | — | `BANK_TRANSFER, CHEQUE, CASH, MOBILE_MONEY, CARD, OTHER` |
| amount_minor | bigint | NN | — | `> 0` ; **immuable** (trigger) |
| allocated_minor | bigint | NN | 0 | CACHE ; `0 <= allocated_minor <= amount_minor` |
| received_at | timestamptz | NN | — | |
| value_date | date | NN | — | |
| status | text | NN | 'RECEIVED' | CACHE ; `RECEIVED, PARTIALLY_ALLOCATED, ALLOCATED, REVERSED` |
| idempotency_key | text | NN | — | |
| import_batch_id | uuid | NULL | — | FK composite `import_batches` ; NN si créé par import |
| notes | text | NULL | — | |
| created_by | uuid | NULL | — | |

Contraintes : UQ `(organization_id, reference, method)` (un paiement en espèces reçoit une référence interne générée) · UQ `(organization_id, idempotency_key)` · UQ `(organization_id, id, customer_id, currency)` · T5.
CK statut ↔ allocation :
- `status='RECEIVED' ⇔ allocated_minor = 0` (hors `REVERSED`)
- `status='PARTIALLY_ALLOCATED' ⇔ 0 < allocated_minor < amount_minor`
- `status='ALLOCATED' ⇔ allocated_minor = amount_minor`
- `status='REVERSED' ⇒ allocated_minor = 0` (toutes les allocations ont été reversées)

Un paiement `REVERSED` n'accepte plus aucune allocation (T10).
Index : `(organization_id, customer_id, received_at)` · `(organization_id, received_at) WHERE status IN ('RECEIVED','PARTIALLY_ALLOCATED')`.
Disponible à affecter = `amount_minor - allocated_minor` (jamais stocké).

### 4.2 `payment_reversals` — APP
Propriétaire : `payments` · Nature : LOG · Événements : `PAYMENT_REVERSED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| payment_id | uuid | NN | — | FK composite ; **UNIQUE** |
| reason_code | text | NN | — | `BOUNCED, CHARGEBACK, ERROR, DUPLICATE, OTHER` |
| reason | text | NN | — | |
| reversed_by | uuid | NULL | — | |
| reversed_at | timestamptz | NN | now() | |

### 4.3 `payment_allocations` — APP (+ `allocated_at`)
Propriétaire : `payments` · Nature : **SOURCE de vérité du solde** · Événements : `PAYMENT_ALLOCATED`, `PAYMENT_ALLOCATION_REVERSED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| payment_id | uuid | NN | — | |
| invoice_id | uuid | NN | — | |
| customer_id | uuid | NN | — | dénormalisé (règle « même client ») |
| currency | char(3) | NN | — | dénormalisé (règle « même devise ») |
| amount_minor | bigint | NN | — | `<> 0` ; `> 0` = allocation, `< 0` = reversal |
| reverses_allocation_id | uuid | NULL | — | NN ⇔ `amount_minor < 0` |
| source | text | NN | 'MANUAL' | `MANUAL, AUTO_MATCH, REVERSAL` |
| reason | text | NULL | — | NN si reversal |
| allocated_by | uuid | NULL | — | |
| allocated_at | timestamptz | NN | now() | |

Contraintes :
- FK `(organization_id, payment_id, customer_id, currency) → payments(organization_id, id, customer_id, currency)`.
- FK `(organization_id, invoice_id, customer_id, currency) → invoices(organization_id, id, customer_id, currency)`.
- UQ `(id, payment_id, invoice_id)` ; FK `(reverses_allocation_id, payment_id, invoice_id) → payment_allocations(id, payment_id, invoice_id)`.
- CK `(reverses_allocation_id IS NULL) = (amount_minor > 0)`.
- CK `(amount_minor < 0) ⇒ (reason IS NOT NULL AND source = 'REVERSAL')`.
- T1, T2, T3, T6, T8.

Index : `(organization_id, invoice_id)` · `(organization_id, payment_id)` · `(organization_id, customer_id, allocated_at)` (vérification des promesses de niveau client, comportement de paiement) · `(reverses_allocation_id) WHERE reverses_allocation_id IS NOT NULL`.
Les dates de règlement (promesse tenue, délai de paiement, cashflow réalisé) se lisent sur `payments.value_date` via `payment_id`, jamais sur `allocated_at` (date de saisie).

---

## 5. Promises

### 5.1 `promises` — STD+V
Propriétaire : `promises` · Nature : SOURCE · Événements : `PROMISE_CREATED`, `PROMISE_FULFILLED`, `PROMISE_BROKEN`, `PROMISE_CANCELLED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| customer_id | uuid | NN | — | toujours renseigné (permet le décompte par client sans jointure) |
| invoice_id | uuid | NULL | — | NULL = promesse de niveau client ; FK composite `(organization_id, invoice_id, customer_id) → invoices(organization_id, id, customer_id)` (la facture appartient bien à ce client) ; `MATCH SIMPLE` : aucune vérification si NULL |
| promised_amount_minor | bigint | NN | — | `> 0` |
| currency | char(3) | NN | — | |
| promised_date | date | NN | — | |
| grace_days | smallint | NN | 0 | copie du réglage au moment de la création |
| channel | text | NN | — | `PHONE, EMAIL, MEETING, WHATSAPP, OTHER` |
| status | text | NN | 'ACTIVE' | `ACTIVE, FULFILLED, BROKEN, CANCELLED` |
| note | text | NULL | — | |
| recorded_by | uuid | NN | — | |
| resolved_at | timestamptz | NULL | — | NN ⇔ `status <> 'ACTIVE'` |
| resolved_amount_minor | bigint | NULL | — | montant constaté à la résolution ; NN si `FULFILLED` ou `BROKEN` ; `>= 0` |

Contraintes : FK composite ci-dessus, ajoutée en plus de `(organization_id, customer_id) → customers` · UQ partiel `(invoice_id) WHERE status='ACTIVE' AND invoice_id IS NOT NULL` · UQ partiel `(customer_id) WHERE status='ACTIVE' AND invoice_id IS NULL` (une promesse client active à la fois).
Index : `(organization_id, status, promised_date)` · `(organization_id, customer_id, status)` (promesses rompues par client, pour le Risk Engine).
Une promesse est « applicable » à une facture si `invoice_id = facture` OU (`invoice_id IS NULL` ET `customer_id = client de la facture`).
Montant constaté d'une promesse = Σ (allocations − reversals) de la portée (facture ou client), sur les paiements non `REVERSED` dont `payments.value_date >=` date de création de la promesse (fuseau de l'organisation). `FULFILLED` quand il atteint `promised_amount_minor` ou quand la facture est `PAID`.

### 5.2 `promise_history` — APP (+ `occurred_at`)
Nature : LOG

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| promise_id | uuid | NN | — | FK composite |
| from_status | text | NULL | — | |
| to_status | text | NN | — | |
| reason | text | NULL | — | |
| actor_id | uuid | NULL | — | |
| actor_type | text | NN | — | `USER, SYSTEM, AUTOMATION` |
| event_id | uuid | NULL | — | référence logique |
| occurred_at | timestamptz | NN | now() | |

Index : `(promise_id, occurred_at)`.

---

## 6. Collections

### 6.1 `collection_actions` — STD+V
Propriétaire : `collection` · Nature : SOURCE
Événements : `COLLECTION_ACTION_PROPOSED`, `_SCHEDULED`, `_EXECUTED`, `_FAILED`, `_CANCELLED`, `_SUPPRESSED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| invoice_id | uuid | NN | — | |
| customer_id | uuid | NN | — | FK composite `(organization_id, invoice_id, customer_id) → invoices(organization_id, id, customer_id)` : même client que la facture |
| type | text | NN | — | `REMINDER, CALL_TASK, FOLLOW_UP, ESCALATION` (D5 : l'alerte responsable est une **notification**, pas une action) |
| level | smallint | NN | 1 | `BETWEEN 1 AND 5` — **verrouillé V1**, sens en §19 ; indépendant du niveau de risque |
| status | text | NN | 'PROPOSED' | `PROPOSED, SCHEDULED, PENDING_APPROVAL, EXECUTING, DONE, FAILED, CANCELLED, SUPPRESSED` |
| origin | text | NN | — | `AUTOMATION, MANUAL` |
| automation_execution_id | uuid | NULL | — | FK composite ; NN si `origin='AUTOMATION'` |
| channel | text | NULL | — | `EMAIL, SMS, WHATSAPP, PHONE, IN_APP` |
| template_id | uuid | NULL | — | FK `message_templates` |
| scheduled_for | timestamptz | NULL | — | NN si `SCHEDULED` |
| executed_at | timestamptz | NULL | — | NN si `DONE` |
| assigned_to | uuid | NULL | — | |
| assigned_role | text | NULL | — | pool de rôle (C5) : `COLLECTOR, MANAGER, ADMIN, OWNER` ; un pool comprend les utilisateurs actifs de rôle **au moins égal** ; une tâche de pool est réclamée par un membre (`assigned_to` renseigné) |
| max_attempts | smallint | NN | 3 | `BETWEEN 1 AND 10` |
| decision_snapshot | jsonb | NN | — | faits + règle + motifs au moment de la décision ; contient **séparément** `risk_level`, `priority_level`, `collection_rules_ref` (version de la définition d'automatisation) et `level`, ainsi que `primary_exception`, `exceptions_trace[]` et `overrides[]` (`OverrideGrant`) ; identifiants et montants uniquement, aucune donnée personnelle |
| dedup_key | text | NN | — | |
| outcome | text | NULL | — | liste fermée (C7) : `SENT, BOUNCED` (envoi) ; `CONTACTED, NO_ANSWER, PROMISE_OBTAINED, DISPUTE_RAISED, REFUSED, WRONG_CONTACT, OTHER` (tâche humaine) ; `USER_CANCELLED, APPROVAL_REJECTED, APPROVAL_EXPIRED` (annulation) |
| outcome_note | text | NULL | — | |
| suppression_code | text | NULL | — | NN ⇔ `SUPPRESSED` ; `PAID, VOIDED, DISPUTED, PROMISE_ACTIVE, HOLD_ACTIVE, IMPORT_HELD, RECONCILIATION_PENDING, FREQUENCY_LIMIT, NO_CONTACT, NO_CONSENT, CUSTOMER_INACTIVE, CUSTOMER_ARCHIVED, ORG_INACTIVE` (motif structuré, exploitable par le moteur et l'explicabilité) |
| suppression_note | text | NULL | — | détail libre |
| created_by | uuid | NULL | — | |

Contraintes : **UQ partiel `(organization_id, dedup_key) WHERE status NOT IN ('CANCELLED','SUPPRESSED')`** — une action annulée ou supprimée ne bloque pas la création d'une action équivalente ; une action `DONE` ou `FAILED` continue de bloquer un doublon dans le même cycle · CK `origin='AUTOMATION' ⇒ automation_execution_id IS NOT NULL`.
CK (C5, C7) : `type = 'REMINDER' ⇒ assigned_to IS NULL AND assigned_role IS NULL` ; `type IN ('CALL_TASK','FOLLOW_UP','ESCALATION') ⇒ assigned_to IS NOT NULL OR assigned_role IS NOT NULL` ; `status = 'DONE' ⇒ outcome IS NOT NULL` ; `status = 'CANCELLED' ⇒ outcome IN ('USER_CANCELLED','APPROVAL_REJECTED','APPROVAL_EXPIRED')` ; `outcome` dans la liste fermée ci-dessus.
Index : `(organization_id, status, scheduled_for)` · `(organization_id, assigned_to, status)` · `(organization_id, assigned_role, status) WHERE assigned_role IS NOT NULL` · `(organization_id, invoice_id, status)`.
Formule normative de `dedup_key` (C4) : `{invoice_id}:{type}:L{level}:C{cycle}:R{occurrence}`, où `cycle` = `invoices.collection_cycle` et `occurrence` est **produit par l'Automation Engine** à partir du `trigger_key` de l'exécution (et de l'indice de répétition d'une étape) ; il vaut `0.0` par défaut. Le Collection Engine ne choisit jamais `occurrence` et n'en accepte aucun d'un appelant. Une action manuelle utilise `manual:{idempotency_key}`. Un nouveau retard, y compris après annulation d'un règlement sur une facture restée `OVERDUE`, ouvre un nouveau cycle ; un événement rejoué ne crée rien.
Non-régression : pour un `(invoice_id, cycle)`, un nouveau `level` inférieur au maximum des niveaux des actions `SCHEDULED`, `EXECUTING` ou `DONE` est refusé (sauf action manuelle motivée). Contrôle applicatif.

### 6.2 `collection_action_attempts` — APP
Nature : LOG

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| action_id | uuid | NN | — | FK composite |
| attempt_no | smallint | NN | — | `>= 1` ; `<= action.max_attempts` (trigger) |
| started_at | timestamptz | NN | — | |
| finished_at | timestamptz | NN | — | `>= started_at` |
| outcome | text | NN | — | `SUCCEEDED, FAILED` |
| provider | text | NULL | — | |
| provider_ref | text | NULL | — | |
| error_code | text | NULL | — | NN si `FAILED` |
| error_message | text | NULL | — | |
| next_retry_at | timestamptz | NULL | — | |

Contraintes : UQ `(action_id, attempt_no)`.

### 6.3 `collection_holds` — STD+V
Propriétaire : `collection` · Nature : SOURCE · Événements : `COLLECTION_HOLD_PLACED`, `COLLECTION_HOLD_RELEASED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| scope | text | NN | — | `INVOICE, CUSTOMER, ORGANIZATION` |
| invoice_id | uuid | NULL | — | FK composite ; NN ⇔ `INVOICE` |
| customer_id | uuid | NULL | — | FK composite ; NN ⇔ `CUSTOMER` |
| automation_id | uuid | NULL | — | FK composite ; NULL = toutes les automatisations. Permet « suspendre *cette* relance pour ce client » |
| kind | text | NN | — | `MANUAL_SUSPENSION, LEGAL, NEGOTIATION` |
| reason | text | NN | — | |
| starts_at | timestamptz | NN | now() | |
| ends_at | timestamptz | NULL | — | `> starts_at` ; NULL = indéfini |
| status | text | NN | 'ACTIVE' | `ACTIVE, RELEASED, EXPIRED` |
| placed_by | uuid | NN | — | |
| released_by | uuid | NULL | — | |
| released_at | timestamptz | NULL | — | NN ⇔ `RELEASED` |
| release_reason | text | NULL | — | |

Contraintes :
- CK cohérence portée/cible : `INVOICE ⇒ invoice_id NN AND customer_id NULL` ; `CUSTOMER ⇒ customer_id NN AND invoice_id NULL` ; `ORGANIZATION ⇒ invoice_id NULL AND customer_id NULL`.
- `EXCLUDE USING gist` sur `(coalesce(invoice_id, customer_id, organization_id) WITH =, coalesce(automation_id, organization_id) WITH =, kind WITH =, tstzrange(starts_at, ends_at) WITH &&) WHERE status='ACTIVE'`. Le `coalesce(..., organization_id)` est indispensable : sans lui, deux holds de portée `ORGANIZATION` ne seraient jamais comparés (NULL ≠ NULL). Nécessite l'extension `btree_gist`.

Index : deux index partiels `WHERE status='ACTIVE'` : `(organization_id, invoice_id)` et `(organization_id, customer_id)`.
Règle de lecture : un hold est en vigueur ⇔ `status='ACTIVE' AND starts_at <= now() AND (ends_at IS NULL OR ends_at > now())`. Le passage à `EXPIRED` par le Scheduler ne conditionne jamais la lecture.

---

## 7. Risk & Priority (projections)

### 7.1 `risk_profiles` — STD
Propriétaire : `risk` · Nature : **PROJ** (reconstructible) · Événements : `RISK_CHANGED` (uniquement si le niveau change)

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| customer_id | uuid | NN | — | FK composite ; **UNIQUE** |
| score | smallint | NN | — | `BETWEEN 0 AND 100` |
| level | text | NN | — | `LOW, MEDIUM, HIGH, CRITICAL` |
| model_version | text | NN | — | |
| factors | jsonb | NN | — | objet `{"factors": [{factor, normalized_input, points, max}], "meta": {confidence}}` ; **dérivé exclusivement des entrées normalisées** (RP14) : aucune valeur brute ni taille d'échantillon |
| input_hash | text | NN | — | SHA-256 du JSON canonique `{model, org, subject, inputs}` ; `inputs` = entrées **normalisées** (points par facteur, `confidence`, `previous_level` publié) ; égal ⇒ sortie égale (`RISK_PRIORITY_CASHFLOW_V1.md` §1.2) |
| computed_at | timestamptz | NN | — | horodatage du **dernier calcul**, mis à jour à chaque recalcul, même à entrée inchangée (barrière de fraîcheur du Rule Engine) |
| trigger_event_id | uuid | NULL | — | référence logique ; comme `computed_at`, métadonnée de **provenance**, hors contenu déterminant |

### 7.2 `risk_snapshots` — APP
Nature : LOG · mêmes colonnes métier que 7.1 (sans UNIQUE sur `customer_id`).
Contraintes : UQ `(customer_id, model_version, input_hash)`. Index : `(customer_id, computed_at DESC)`.

### 7.3 `priority_items` — STD
Propriétaire : `priority` · Nature : **PROJ** · Événements : `PRIORITY_CHANGED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| invoice_id | uuid | NN | — | FK composite ; **UNIQUE** |
| customer_id | uuid | NN | — | dénormalisé pour filtrer (FK composite avec la facture) |
| level | text | NN | — | `NONE, WATCH, ACTION, PRIORITY, CRITICAL` |
| rank_score | numeric(6,2) | NN | — | `BETWEEN 0 AND 100` (borne de **stockage** ; domaine de `prio-1.0` : 0 à 95) |
| reasons | jsonb | NN | — | objet `{factors: [{factor, normalized_input, points}], caps: [], signals: []}` ; dérivé exclusivement des entrées normalisées (RP14) ; `signals` peut contenir `RECONCILIATION_PENDING` (RP23), sans effet sur le score |
| model_version | text | NN | — | |
| input_hash | text | NN | — | SHA-256 du JSON canonique ; `inputs` = points par facteur, `previous_level` **publié**, indicateurs de plafond, `reconciliation_pending` |
| computed_at | timestamptz | NN | — | horodatage du **dernier calcul**, mis à jour à chaque recalcul, même à entrée inchangée |

Index : `(organization_id, level, rank_score DESC) WHERE level <> 'NONE'` · `(organization_id, customer_id)`.

### 7.4 `priority_snapshots` — APP
Nature : LOG · mêmes colonnes métier que 7.3 + `trigger_event_id uuid NULL`.
Contraintes : UQ `(invoice_id, model_version, input_hash)`. Index : `(invoice_id, computed_at DESC)`.

---

## 8. Automation

### 8.1 `automations` — STD+V
Propriétaire : `automation` · Nature : SOURCE
Événements : `AUTOMATION_CREATED`, `AUTOMATION_VERSION_CREATED`, `AUTOMATION_ACTIVATED`, `AUTOMATION_PAUSED`, `AUTOMATION_DISABLED`, `AUTOMATION_ARCHIVED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| name | text | NN | — | UQ par org parmi les non archivées |
| description | text | NULL | — | |
| status | text | NN | 'DRAFT' | `DRAFT, ACTIVE, PAUSED, DISABLED, ARCHIVED` |
| current_version_id | uuid | NULL | — | FK composite `(organization_id, id, current_version_id) → automation_versions(organization_id, automation_id, id)` **DEFERRABLE INITIALLY DEFERRED** : la version courante appartient bien à cette automatisation ; NN si `ACTIVE` |
| active_since | timestamptz | NULL | — | **`status = 'ACTIVE' ⇔ active_since IS NOT NULL`** ; fixé à chaque passage à `ACTIVE` (avec inscription : `as_of` de l'aperçu) et à chaque changement de version courante ; effacé quand l'automatisation quitte `ACTIVE` ; référence de la non-rétroactivité (Automation Engine §4) |
| created_by | uuid | NULL | — | |
| approved_by | uuid | NULL | — | |
| approved_at | timestamptz | NULL | — | |
| archived_at | timestamptz | NULL | — | NN ⇔ `ARCHIVED` |

Dispatch d'un événement : jointure `automations.current_version_id → automation_versions.trigger_type` filtrée sur `status='ACTIVE'` (pas de cache `trigger_type` sur `automations` : il pouvait diverger de la version courante).
Index : `(organization_id, status)`.

### 8.2 `automation_versions` — APP
Nature : LOG (immuable)

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| automation_id | uuid | NN | — | FK composite |
| version_no | integer | NN | — | `>= 1` ; séquentiel |
| definition | jsonb | NN | — | objet : trigger, conditions, exceptions, actions, délais |
| schema_version | text | NN | — | |
| definition_hash | text | NN | — | SHA-256 de la définition normalisée |
| trigger_type | text | NN | généré | `GENERATED ALWAYS AS (definition #>> '{trigger,type}') STORED` ; le chemin `trigger.type` est figé par `schema_version` |
| change_note | text | NULL | — | |
| created_by | uuid | NULL | — | |

Contraintes : UQ `(automation_id, version_no)` · UQ `(organization_id, automation_id, id)` (cible des FK : une exécution ou une version courante ne peut pas pointer vers la version d'une autre automatisation) · CK `jsonb_typeof(definition)='object'`.
Index : `(organization_id, trigger_type)`.
Validation du schéma JSON et de la liste blanche d'actions : **Domain**, avant insertion.

**Liste blanche des actions d'automatisation (V1, verrouillée D2/D5)** :

| Action | Effet | Support |
|---|---|---|
| `CREATE_COLLECTION_ACTION`, `CREATE_REMINDER`, `CREATE_TASK`, `ASSIGN_TASK`, `ESCALATE` | crée une action de recouvrement (types `REMINDER`, `CALL_TASK`, `FOLLOW_UP`, `ESCALATION`) | `collection_actions` |
| `CREATE_NOTIFICATION`, `CREATE_MANAGER_ALERT` | crée une notification (l'alerte responsable est une notification de type `MANAGER_ALERT`) | `notifications` |
| `REQUEST_APPROVAL`, `REQUEST_REVIEW` | crée une approbation (`kind`) | `approvals` |
| `REQUEST_RISK_RECALCULATION`, `REQUEST_PRIORITY_RECALCULATION`, `REQUEST_CASHFLOW_RECALCULATION` | émet un événement `REQUEST` | `events` |
| `WAIT`, `DELAY`, `BRANCH`, `STOP`, `PAUSE` | contrôle du flux | `automation_executions`, `automation_execution_steps` |

`UPDATE_PRIORITY` **n'existe pas** : seule la projection `priority_items`, écrite par le Priority Engine, porte une priorité.
`PAUSE` de la Phase 6 désigne un **contrôle d'exécution** (pause par un utilisateur ou le système), pas une étape de définition.


### 8.3 `automation_executions` — STD+V
Propriétaire : `automation` · Nature : SOURCE
Événements : `AUTOMATION_EXECUTION_STARTED`, `_COMPLETED`, `_FAILED`, `_CANCELLED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| automation_id | uuid | NN | — | FK composite |
| automation_version_id | uuid | NN | — | version **exécutée** ; FK composite `(organization_id, automation_id, automation_version_id) → automation_versions(organization_id, automation_id, id)` |
| trigger_key | text | NN | — | identité du déclenchement (Automation Engine §3) : `event:{event_id}` · `time:{ancre}{±N}d:{sujet}#{n}` · `enroll:{automation_version_id}:{sujet}` · `import-release:{batch_id}:{sujet}` · `retry:{execution_id}` ; l'indice `n` alimente l'`occurrence` du Collection Engine |
| trigger_event_id | uuid | NULL | — | référence logique ; NULL pour un déclencheur purement temporel |
| subject_type | text | NN | — | `INVOICE, CUSTOMER, PAYMENT, PROMISE` |
| subject_id | uuid | NN | — | |
| status | text | NN | 'PENDING' | `PENDING, RUNNING, WAITING, COMPLETED, FAILED, CANCELLED, PAUSED` |
| current_step | integer | NN | 0 | `>= 0` |
| resume_at | timestamptz | NULL | — | NN si `WAITING` |
| retry_count | smallint | NN | 0 | `>= 0` |
| correlation_id | uuid | NN | — | |
| failure_reason | text | NULL | — | NN si `FAILED` |
| status_reason | text | NULL | — | NN si `PAUSED`/`CANCELLED` ; CK `IN ('USER','AUTOMATION_PAUSED','AUTOMATION_DISABLED','DISPUTED','PROMISE_ACTIVE','HOLD_ACTIVE','CUSTOMER_INACTIVE','CUSTOMER_ARCHIVED','ORG_INACTIVE','IMPORT_HELD','RECONCILIATION_PENDING','SUBJECT_PAID','SUBJECT_VOIDED')` (mêmes exceptions métier que `collection_actions.suppression_code`) |
| status_changed_by | uuid | NULL | — | |
| started_at | timestamptz | NULL | — | |
| completed_at | timestamptz | NULL | — | NN si terminal |

Contraintes : **UQ `(automation_id, trigger_key, subject_id)`** — l'idempotence ne dépend pas de `events`, qui est partitionnée et n'admet pas d'unicité globale sur autre chose que `(id, occurred_at)`.
Contrainte de concurrence (AU6) : **UQ partiel `(automation_id, subject_id) WHERE status IN ('PENDING','RUNNING','WAITING','PAUSED')`** — au plus une exécution non terminale par automatisation et sujet ; les états terminaux (`COMPLETED`, `FAILED`, `CANCELLED`) coexistent historiquement.
Création étalée (libération d'un lot, inscription) : les exécutions sont créées en `WAITING` avec `resume_at` = créneau de démarrage.
Index : `(status, resume_at) WHERE status IN ('PENDING','WAITING')` · `(organization_id, subject_type, subject_id)`.
Index d'exploitation (optimisation, pas une garantie métier) : `(organization_id, trigger_key text_pattern_ops) WHERE trigger_key LIKE 'import-release:%'` pour le suivi et la pause d'un lot d'import.

### 8.4 `automation_execution_steps` — APP
Nature : LOG (historique explicable)

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| execution_id | uuid | NN | — | FK composite |
| step_index | integer | NN | — | `>= 0` |
| attempt_no | smallint | NN | 1 | `>= 1` |
| step_type | text | NN | — | `CONDITION, ACTION, WAIT, BRANCH, APPROVAL, STOP` |
| status | text | NN | — | `COMPLETED, SKIPPED, FAILED, SUSPENDED, STOPPED` |
| revalidation_result | jsonb | NN | — | exceptions et conditions évaluées |
| output | jsonb | NULL | — | |
| error | text | NULL | — | NN si `FAILED` |
| executed_at | timestamptz | NN | now() | |

Contraintes : UQ `(execution_id, step_index, attempt_no)`. *(Écart vs ERD V1 : `attempt_no` ajouté pour permettre les retries.)*

### 8.5 `approvals` — STD+V
Propriétaire : `approvals` · Nature : SOURCE · Événements : `APPROVAL_REQUESTED`, `APPROVAL_GRANTED`, `APPROVAL_REJECTED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| execution_id | uuid | NULL | — | FK composite |
| collection_action_id | uuid | NULL | — | FK composite ; XOR avec `execution_id` |
| requested_by | uuid | NULL | — | NULL = système |
| kind | text | NN | 'APPROVAL' | `APPROVAL, REVIEW` (couvre `REQUEST_APPROVAL` et `REQUEST_REVIEW`) |
| requested_from_user | uuid | NULL | — | |
| requested_role | text | NULL | — | CK : exactement l'un des deux est renseigné |
| reason | text | NN | — | pourquoi une approbation est requise |
| context | jsonb | NN | — | ce qui sera exécuté |
| status | text | NN | 'PENDING' | `PENDING, APPROVED, REJECTED, EXPIRED` |
| decided_by | uuid | NULL | — | NN si ≠ `PENDING` (sauf `EXPIRED`) |
| decided_at | timestamptz | NULL | — | idem |
| decision_comment | text | NULL | — | |
| expires_at | timestamptz | NN | — | |

Index : `(organization_id, status, expires_at) WHERE status='PENDING'` · `(requested_from_user, status)`.

---

## 9. Cashflow

### 9.1 `cashflow_runs` — STD
Propriétaire : `cashflow` · Nature : PROJ · Événements : `CASHFLOW_UPDATED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| as_of | date | NN | — | |
| horizon_days | integer | NN | — | `> 0` (7, 30, 60, 90, 180, 365) |
| scenario | text | NN | 'BASE' | `BASE, PESSIMISTIC, OPTIMISTIC` — **verrouillé V1** (pas de `STRESS` ni `CONSERVATIVE`) |
| currency | char(3) | NN | — | |
| model_version | text | NN | — | |
| assumptions | jsonb | NN | — | objet |
| input_hash | text | NN | — | SHA-256 du JSON canonique de `assumptions` et des entrées **brutes** triées du run (factures, non-alloué par client, promesses, paiements de la fenêtre) ; **RP14 ne s'applique pas** : un run est un objet complet et daté |
| status | text | NN | 'RUNNING' | `RUNNING, COMPLETED, FAILED` |
| is_current | boolean | NN | false | dernier calcul valide du couple (horizon, scénario) |
| computed_at | timestamptz | NULL | — | NN si `COMPLETED` |
| trigger_event_id | uuid | NULL | — | référence logique |
| created_by | uuid | NULL | — | |

Contraintes : UQ `(organization_id, as_of, horizon_days, scenario, model_version, input_hash)` · UQ partiel `(organization_id, horizon_days, scenario) WHERE is_current` · CK `horizon_days IN (7,30,60,90,180,365)` · CK `is_current ⇒ status='COMPLETED'` · UQ partiel `(organization_id, horizon_days, scenario) WHERE status='RUNNING'` (au plus un calcul en cours par couple ; une seconde demande avec le même `input_hash` reçoit ce run, avec un `input_hash` différent elle reçoit `CASHFLOW_RUN_CONFLICT`).
Bascule de `is_current` : dans une même transaction, d'abord `UPDATE … SET is_current=false` sur l'ancien run, puis `true` sur le nouveau (un index unique partiel ne peut pas être différé).
Promotion (RP17) : un seul run `is_current` par triplet (index unique ci-dessus) ; la promotion se fait sous verrou consultatif sur le triplet, en une transaction, et est **monotone** : un run ne devient courant que si son `(as_of, computed_at)` est plus récent que celui du run courant ; un run retardataire reste `COMPLETED` non courant.

### 9.2 `cashflow_lines` — APP
Nature : PROJ

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| run_id | uuid | NN | — | FK composite |
| period_start | date | NN | — | |
| period_end | date | NN | — | `> period_start` |
| category | text | NN | — | `REALIZED, EXPECTED, PROBABLE, AT_RISK` |
| amount_minor | bigint | NN | — | `>= 0` ; montant nominal (devise = `cashflow_runs.currency`, non dupliquée) |
| probability | numeric(5,4) | NN | 1 | `BETWEEN 0 AND 1` ; `= 1` pour `REALIZED` |
| weighted_minor | bigint | NN | généré | `GENERATED ALWAYS AS ((round(amount_minor * probability))::bigint) STORED` : montant pondéré, sommable ; équivaut à `⌊(montant × p + 5 000) / 10 000⌋` avec `p` en points de base (arrondi demi vers le haut, montants positifs) |
| source_payment_id | uuid | NULL | — | FK composite ; NN pour `REALIZED` |
| source_invoice_id | uuid | NULL | — | FK composite ; NN pour `EXPECTED`, `PROBABLE`, `AT_RISK` (sauf ligne agrégée) |
| source_customer_id | uuid | NULL | — | FK composite |
| explanation | jsonb | NULL | — | |

Contraintes : CK `category='REALIZED' ⇒ source_payment_id IS NOT NULL AND probability = 1`.
Index : `(run_id, period_start)` · `(organization_id, source_invoice_id)` · `(organization_id, source_payment_id)`.
Dates et montants `REALIZED` : `payments.value_date` et `payments.amount_minor`, hors paiements `REVERSED`.

---

## 10. Notifications

### 10.1 `notifications` — STD+V
Propriétaire : `notifications` · Nature : SOURCE · Événements : `NOTIFICATION_CREATED`, `NOTIFICATION_SENT`, `NOTIFICATION_FAILED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| recipient_user_id | uuid | NULL | — | FK `users` |
| recipient_contact_id | uuid | NULL | — | FK composite ; XOR avec `recipient_user_id` |
| type | text | NN | — | |
| channel | text | NN | — | `IN_APP, EMAIL, SMS, WHATSAPP` |
| template_id | uuid | NULL | — | |
| payload | jsonb | NN | — | |
| source_action_id | uuid | NULL | — | FK composite `collection_actions` |
| status | text | NN | 'PENDING' | `PENDING, SENT, FAILED, CANCELLED` |
| dedup_key | text | NN | — | |
| scheduled_for | timestamptz | NULL | — | |
| sent_at | timestamptz | NULL | — | NN si `SENT` |
| read_at | timestamptz | NULL | — | |
| anonymized_at | timestamptz | NULL | — | PII : voir §17 (le `payload` est nettoyé, la ligne reste) |

Contraintes : UQ partiel `(organization_id, dedup_key) WHERE status <> 'CANCELLED'`.
Index : `(organization_id, status, scheduled_for)` · `(recipient_user_id, read_at)`.
Types initiaux de `type` : `MANAGER_ALERT` (D5), `CUSTOMER_ARCHIVED_BALANCE_REOPENED` (D6), `APPROVAL_REQUESTED`, `REMINDER`, `RECONCILIATION_REVIEW` (revue d'un paiement non alloué, pool `COLLECTOR`), `RECONCILIATION_OVERDUE` (fin de fenêtre, pool `MANAGER`) ; clés de déduplication `reconciliation:{payment_id}:review:{user_id}` et `reconciliation:{payment_id}:overdue:{user_id}`. Catalogue complet à figer avec le Collection Engine.

### 10.2 `notification_deliveries` — APP
Nature : LOG

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| notification_id | uuid | NN | — | FK composite |
| attempt_no | smallint | NN | — | `>= 1` |
| provider | text | NN | — | |
| provider_message_id | text | NULL | — | |
| outcome | text | NN | — | `ACCEPTED, DELIVERED, FAILED, BOUNCED` |
| error | text | NULL | — | |
| attempted_at | timestamptz | NN | now() | |
| delivered_at | timestamptz | NULL | — | |

Contraintes : UQ `(notification_id, attempt_no)`.

### 10.3 `message_templates` — STD
Nature : SOURCE

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| code | text | NN | — | |
| channel | text | NN | — | |
| language | char(2) | NN | 'fr' | |
| version | integer | NN | 1 | |
| subject | text | NULL | — | |
| body | text | NN | — | |
| variables | jsonb | NN | '[]' | tableau des variables autorisées |
| status | text | NN | 'DRAFT' | `DRAFT, ACTIVE, ARCHIVED` |
| created_by | uuid | NULL | — | |

Contraintes : UQ `(organization_id, code, channel, language, version)`.
*(Colonne `version` propre au versionnement de contenu, distincte du verrou optimiste : ici STD, sans `version` de verrou.)*

---

## 11. Billing

### 11.1 `plans` — table globale
| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| id | uuid | NN | — | PK |
| code | text | NN | — | UNIQUE |
| name | text | NN | — | |
| limits | jsonb | NN | — | quotas et fonctionnalités |
| price_minor | bigint | NN | — | `>= 0` |
| currency | char(3) | NN | — | |
| billing_interval | text | NN | — | `MONTH, YEAR` |
| status | text | NN | 'ACTIVE' | `ACTIVE, RETIRED` |
| created_at, updated_at | timestamptz | NN | now() | |

### 11.2 `subscriptions` — STD+V
Événements : `SUBSCRIPTION_CHANGED`

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| plan_id | uuid | NN | — | FK `plans(id)` |
| status | text | NN | — | `TRIALING, ACTIVE, PAST_DUE, CANCELLED, EXPIRED` |
| current_period_start | timestamptz | NN | — | |
| current_period_end | timestamptz | NN | — | `> current_period_start` |
| trial_ends_at | timestamptz | NULL | — | |
| cancel_at_period_end | boolean | NN | false | |
| provider | text | NULL | — | |
| provider_ref | text | NULL | — | |

Contraintes : UQ partiel `(organization_id) WHERE status IN ('ACTIVE','TRIALING','PAST_DUE')`.

---

## 12. Transversal

### 12.1 `events` — outbox, **partitionnée par mois sur `occurred_at`**
Nature : LOG (contenu métier immuable ; seules les colonnes de publication sont mutables)

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| id | uuid | NN | — | PK composite `(id, occurred_at)` |
| occurred_at | timestamptz | NN | now() | clé de partition |
| organization_id | uuid | NN | — | pas de FK (partition) |
| type | text | NN | — | ex. `INVOICE_OVERDUE` |
| category | text | NN | — | `MUTATION, TRANSITION, REQUEST, RESULT` (voir `INVARIANTS_V1.md` §10) |
| import_batch_id | uuid | NULL | — | référence logique ; renseigné pour les événements émis pendant la normalisation d'un lot d'import |
| aggregate_type | text | NN | — | |
| aggregate_id | uuid | NN | — | |
| payload | jsonb | NN | — | objet |
| schema_version | smallint | NN | 1 | |
| correlation_id | uuid | NN | — | |
| causation_id | uuid | NULL | — | id de l'événement parent |
| causation_depth | smallint | NN | 0 | profondeur dans la chaîne de causalité ; `CHECK (causation_depth <= 20)` ; au-delà, le worker rejette et alerte (anti-boucle Risk ↔ Priority ↔ Automation) |
| aggregate_version | integer | NULL | — | `version` de la racine **après** modification dans la transaction d'émission (s'incrémente aussi sur les colonnes de cache) ; NULL pour `REQUEST` et pour les projections sans `version` ; permet à un handler de détecter un événement obsolète |
| actor_id | uuid | NULL | — | |
| actor_type | text | NN | — | `USER, SYSTEM, AUTOMATION` |
| published_at | timestamptz | NULL | — | mutable ; posé quand **chaque handler abonné a pris en charge** l'événement (reçu terminal, `RETRYING` ou `DEAD`) : il ne dépend jamais de la **réussite** d'un handler |
| available_at | timestamptz | NN | now() | mutable ; **disponibilité du message d'outbox** : bail de réclamation du relais, fenêtre de regroupement d'un `REQUEST`. Ne sert **jamais** de calendrier de reprise d'un handler (voir `event_receipts.available_at`) |
| publish_attempts | smallint | NN | 0 | mutable |
| last_error | text | NULL | — | mutable |

Index : partiel `(available_at, id) WHERE published_at IS NULL` · `(organization_id, aggregate_type, aggregate_id, occurred_at)` · `(organization_id, type, occurred_at)`.
Le trigger d'immutabilité n'autorise que la modification de `published_at`, `publish_attempts`, `last_error`, `available_at`.
Catégories : `TRANSITION` correspond à un changement d'état ; `MUTATION` à une création ou une mutation append-only (ex. `PAYMENT_ALLOCATED`, agrégat `PAYMENT`) ; `REQUEST` à une demande adressée à un seul moteur (regroupable) ; `RESULT` au résultat d'une projection.
Principe : un événement est une **notification** ; les handlers relisent l'état courant en base et ne se fient pas au seul `payload`.
Unicité : PostgreSQL n'admet pas d'index unique sur une table partitionnée qui n'inclut pas la clé de partition. Aucune déduplication globale par `dedup_key` n'est donc possible ici ; l'idempotence repose sur `event_receipts`, `automation_executions.trigger_key`, `collection_actions.dedup_key` et `notifications.dedup_key`. Les événements temporels du Scheduler ne sont émis qu'à l'occasion d'une transition d'état gardée (`UPDATE … WHERE lifecycle_state = <ancien>`), donc au plus une fois.

### 12.2 `event_receipts`
| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| event_id | uuid | NN | — | référence logique |
| handler_name | text | NN | — | |
| organization_id | uuid | NN | — | |
| outcome | text | NN | 'PROCESSED' | `PROCESSED, SKIPPED, RETRYING, DEAD` — `RETRYING` (nouvelle tentative planifiée) et `DEAD` (handler en échec après ses tentatives) sont des états **techniques**, jamais des états métier ; l'événement reste rejouable |
| processed_at | timestamptz | NN | now() | |
| attempts | smallint | NN | 1 | nombre de tentatives de traitement ; `>= 1` |
| last_error | text | NULL | — | dernière erreur ; NN si `RETRYING` ou `DEAD` ; sans donnée personnelle |
| available_at | timestamptz | NULL | — | **prochaine tentative de CE handler** ; NN si et seulement si `RETRYING` ; `CHECK (outcome = 'RETRYING') = (available_at IS NOT NULL)`. Ne se confond jamais avec `events.available_at` |

PK `(event_id, handler_name)`. Un reçu `PROCESSED` ou `SKIPPED` fait répondre `REPLAY` à toute nouvelle livraison ; un reçu `RETRYING` est repris par la boucle de reprise du relais (index partiel `(available_at) WHERE outcome = 'RETRYING'`) ; un reçu `DEAD` n'est retraité que par la commande explicite `ReplayDeadEvent`, qui le met à jour. Purge planifiée

### 12.3 `idempotency_keys` — STD
| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| key | text | NN | — | |
| endpoint | text | NN | — | méthode + route |
| request_hash | text | NN | — | |
| status | text | NN | 'IN_PROGRESS' | `IN_PROGRESS, COMPLETED` |
| response_status | smallint | NULL | — | |
| response_body | jsonb | NULL | — | |
| expires_at | timestamptz | NN | — | |

Contraintes : UQ `(organization_id, key, endpoint)`. Index : `(expires_at)`. Purge planifiée.

### 12.4 `audit_logs` — **partitionnée par mois sur `occurred_at`**, append-only
| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| id | uuid | NN | — | PK composite `(id, occurred_at)` |
| occurred_at | timestamptz | NN | now() | |
| organization_id | uuid | NN | — | |
| actor_id | uuid | NULL | — | |
| actor_type | text | NN | — | `USER, SYSTEM, AUTOMATION` |
| action | text | NN | — | |
| entity_type | text | NN | — | |
| entity_id | uuid | NN | — | |
| before | jsonb | NULL | — | |
| after | jsonb | NULL | — | |
| reason | text | NULL | — | |
| ip | inet | NULL | — | |
| user_agent | text | NULL | — | |
| correlation_id | uuid | NULL | — | |
| anonymized_at | timestamptz | NULL | — | PII : voir §17 (seuls `before`, `after`, `reason` peuvent être nettoyés) |

Index : `(organization_id, entity_type, entity_id, occurred_at)` · `(organization_id, actor_id, occurred_at)`.
Politique d'audit (D3, verrouillée) : sont écrits dans `audit_logs`, dans la transaction, les commandes d'un utilisateur ou d'une automatisation, les changements de configuration et de droits, les holds, les approbations et les actions sensibles (anonymisation, réactivation d'un client archivé, engagement d'un lot d'import). Les transitions purement temporelles du Scheduler (`DUE_SOON`, `DUE`, `OVERDUE`) restent dans `*_history` et `events`, sans doublon d'audit.

### 12.5 `import_batches` — STD+V
Propriétaire : `imports` (nouveau module) · Nature : SOURCE · Événements : `IMPORT_BATCH_UPLOADED`, `_READY`, `_APPROVED`, `_COMMITTED`, `_NORMALIZED`, `_RELEASED`, `_FAILED`, `_CANCELLED`

Un lot d'import historique. Il matérialise la séquence verrouillée (N14) : import → validation → lot prêt → validation par un administrateur → engagement → normalisation → événements des moteurs → éligibilité des automatisations → exécution contrôlée.

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| kind | text | NN | 'HISTORICAL' | `HISTORICAL` (seul type en V1) |
| source_type | text | NN | — | `CSV, XLSX` en V1 |
| file_name | text | NULL | — | |
| file_hash | text | NN | — | SHA-256 du fichier |
| status | text | NN | 'UPLOADED' | `UPLOADED, VALIDATING, VALIDATION_FAILED, READY, APPROVED, COMMITTED, NORMALIZING, NORMALIZED, FAILED, RELEASING, RELEASE_PAUSED, RELEASED, CANCELLED` |
| rows_total | integer | NN | 0 | `>= 0` |
| rows_valid | integer | NN | 0 | `>= 0` |
| rows_invalid | integer | NN | 0 | `>= 0` ; `rows_valid + rows_invalid <= rows_total` |
| validation_summary | jsonb | NULL | — | objet ; comptes et motifs agrégés, sans donnée personnelle |
| release_mode | text | NN | 'PACED' | `HOLD` (aucune automatisation jusqu'à libération manuelle), `PACED` (libération étalée) |
| release_max_per_day | integer | NULL | — | `> 0` ; plafond quotidien d'exécutions libérées ; NN si `PACED` |
| uploaded_by | uuid | NN | — | |
| approved_by | uuid | NULL | — | NN à partir de `APPROVED` |
| approved_at | timestamptz | NULL | — | idem |
| committed_at | timestamptz | NULL | — | NN à partir de `COMMITTED` |
| normalized_at | timestamptz | NULL | — | NN à partir de `NORMALIZED` |
| released_at | timestamptz | NULL | — | NN si `RELEASED` |
| failure_reason | text | NULL | — | NN si `FAILED` ou `VALIDATION_FAILED` |
| cancelled_at | timestamptz | NULL | — | NN si `CANCELLED` |
| cancel_reason | text | NULL | — | NN si `CANCELLED` |

Contraintes : UQ partiel `(organization_id, file_hash) WHERE status NOT IN ('CANCELLED','VALIDATION_FAILED','FAILED')` (un même fichier n'est pas importé deux fois) · CK `status IN ('APPROVED','COMMITTED','NORMALIZING','NORMALIZED','RELEASING','RELEASE_PAUSED','RELEASED') ⇒ approved_by IS NOT NULL AND approved_at IS NOT NULL`.
Index : `(organization_id, status)`.
Règle : un lot `COMMITTED` ou au-delà n'est **jamais annulé ni supprimé**. Une correction se fait par les mécanismes normaux (reversal, `VOID`, nouvelle saisie).

### 12.6 `import_rows` — STD
Propriétaire : `imports` · Nature : staging technique

| Colonne | Type | Null | Défaut | Contrainte / note |
|---|---|---|---|---|
| batch_id | uuid | NN | — | FK composite |
| row_no | integer | NN | — | `>= 1` |
| entity_type | text | NN | — | `CUSTOMER, INVOICE, PAYMENT, ALLOCATION` |
| raw | jsonb | NN | — | ligne source telle que lue ; **contient des données personnelles** (voir §17) |
| validation_status | text | NN | 'PENDING' | `PENDING, VALID, INVALID` |
| errors | jsonb | NULL | — | tableau de `{code, field}` ; NN si `INVALID` |
| target_id | uuid | NULL | — | identifiant de l'entité créée à la normalisation |

Contraintes : UQ `(batch_id, row_no)` · trigger : `raw`, `validation_status` et `errors` immuables dès que le lot est `COMMITTED`.
Index : `(batch_id, validation_status)`.

Marquage des données importées : `customers.import_batch_id`, `invoices.import_batch_id` (avec `invoices.origin`) et `payments.import_batch_id`.
Les événements émis pendant la normalisation portent `events.import_batch_id`. Le répartiteur d'automatisations ne crée **aucune exécution** pour un événement dont le lot n'est pas au moins `RELEASING`. La libération construit les exécutions avec `trigger_key = import-release:{batch_id}:{subject_id}`, dans l'ordre de priorité, `release_max_per_day` limite le **démarrage** des exécutions, jamais leur création : toutes sont créées à la libération (statut `WAITING`, `resume_at` = créneau de démarrage), dans l'ordre de priorité ; `RELEASED` signifie que toutes sont créées et planifiées. Les moteurs Risk, Priority et Cashflow, eux, sont recalculés pendant la normalisation, par demandes regroupées (une par client, pas une par facture).

---

## 13. Matrice Propriétaire → Nature → Producteur d'événements

| Module | Tables SOURCE | Tables CACHE / PROJ | Tables LOG |
|---|---|---|---|
| identity / organizations | organizations, users, memberships, org_settings, org_holidays | — | — |
| customers | customers, customer_contacts | — | — |
| invoices | invoices, invoice_items, invoice_disputes | `invoices.paid_minor`, `settlement_state`, `settled_on` | invoice_state_history |
| payments | payments | `payments.allocated_minor`, `status` | payment_allocations (**SoT du solde**), payment_reversals |
| promises | promises | — | promise_history |
| collection | collection_actions, collection_holds | — | collection_action_attempts |
| risk | — | risk_profiles | risk_snapshots |
| priority | — | priority_items | priority_snapshots |
| approvals | approvals | — | — |
| automation | automations, automation_executions | — (`automation_versions.trigger_type` est une colonne générée) | automation_versions, automation_execution_steps |
| cashflow | — | cashflow_runs, cashflow_lines | — |
| notifications | notifications, message_templates | — | notification_deliveries |
| billing | plans, subscriptions | — | — |
| imports | import_batches, import_rows (staging) | — | — |
| core | idempotency_keys | — | events, event_receipts, audit_logs |

## 14. Contraintes différées et triggers (référence normative T1–T15)

Toutes sont des `CONSTRAINT TRIGGER … DEFERRABLE INITIALLY DEFERRED` (sauf T7 et T8, immédiats), posés par migrations SQL.

| # | Invariant | Table déclenchante |
|---|---|---|
| T1 | `SUM(amount_minor)` des allocations d'un paiement ∈ `[0, payment.amount_minor]` | payment_allocations |
| T2 | `SUM(amount_minor)` des allocations d'une facture ∈ `[0, invoice.total_minor]` | payment_allocations |
| T3 | Pour chaque allocation d'origine, `SUM(reversals liés) >= -original.amount_minor` | payment_allocations |
| T4 | `invoices.paid_minor = SUM(allocations)` ; `settlement_state` et `settled_on` cohérents | invoices, payment_allocations |
| T5 | `payments.allocated_minor = SUM(allocations)` ; `status` cohérent avec `payment_reversals` | payments, payment_allocations |
| T6 | Aucune allocation nette positive sur une facture `DRAFT`, `CANCELLED` ou `VOID` | payment_allocations |
| T7 | Lignes de facture immuables hors `DRAFT` (immédiat) | invoice_items |
| T8 | Append-only : `UPDATE`/`DELETE` interdits sur les tables LOG (immédiat). `TRUNCATE` révoqué au rôle applicatif. | tables LOG |
| T9 | `SUM(invoice_items.line_total_minor) = invoices.total_minor` à la transition `DRAFT → ISSUED` | invoices |
| T10 | Aucune allocation positive sur un paiement `REVERSED` | payment_allocations |
| T11 | `disputed_amount_minor <= invoices.total_minor` | invoice_disputes |
| T12 | `collection_action_attempts.attempt_no <= collection_actions.max_attempts` | collection_action_attempts |
| T14 | **Garde de transition** (immédiat, `BEFORE UPDATE` de la colonne d'état) : rejette tout couple `(ancien, nouveau)` absent de la table de transitions de la machine. Machines concernées : `organizations.status`, `customers.status`, `invoices.lifecycle_state`, `invoice_disputes.status`, `payments.status`, `promises.status`, `collection_actions.status`, `collection_holds.status`, `approvals.status`, `automations.status`, `automation_executions.status`, `import_batches.status`. Les couples sont **générés depuis la table de transitions du Domain** (source unique) ; un test vérifie l'égalité. Les `INSERT` (création, import) ne sont pas concernés. | tables listées |
| T15 | `invoices.lifecycle_state → 'VOID'` refusé tant qu'un litige `OPEN` existe sur la facture (immédiat, `BEFORE UPDATE`). | invoices |
| T13 | Si `OLD.lifecycle_state <> 'DRAFT'`, alors `number`, `customer_id`, `currency`, `issue_date`, `due_date`, `total_minor` sont inchangés (immédiat, `BEFORE UPDATE`). Une transition `DRAFT → ISSUED` reste libre de renseigner `issued_at`. Les créations par import sont des `INSERT` et ne sont pas concernées. | invoices |

Verrouillage applicatif associé : paiement d'abord, puis factures triées par `id`.

## 15. Écarts par rapport à l'ERD V1 (historique cumulé)

Ajouts de la V1 : `invoices.settled_at`, `payments.allocated_minor`, `automation_execution_steps.attempt_no`, `cashflow_runs.is_current`, `priority_items.customer_id`, `customers.external_ref` (UQ partiel), `message_templates.version`.

Corrections de la V1.1 (revue de cohérence, détail dans `REVIEW_COHERENCE_V1.md`) :

1. `invoices` : UQ `(organization_id, id, customer_id)` ajoutée (les FK « même client » n'avaient pas de cible valide).
2. `invoices.settled_at` remplacé par `settled_on date` (valeur du `value_date` du paiement).
3. `invoices` : CK à trois branches sur le règlement ; règle « annulée ⇒ non payée » ; règle de gel du cycle de vie d'une facture `PAID` ; index d'exposition et de Scheduler corrigés.
4. `payments` : CK statut ↔ `allocated_minor` ; T10.
5. `promises` : `customer_id` toujours renseigné ; `invoice_id` nullable ; FK composite facture ↔ client ; XOR supprimé.
6. `collection_actions` : `suppression_code` structuré ; formule de `dedup_key` ; FK composite « même client ».
7. `collection_holds` : `automation_id` ajouté ; `EXCLUDE` corrigé (`coalesce(..., organization_id)`) ; règle de lecture d'un hold en vigueur.
8. `approvals.kind` ajouté (`APPROVAL`, `REVIEW`).
9. `automations.trigger_type` supprimé ; `automation_versions.trigger_type` généré ; FK composites version ↔ automatisation.
10. `automation_executions.trigger_key` ajouté ; UQ portée sur `(automation_id, trigger_key, subject_id)`.
11. `cashflow_lines` : `source_payment_id`, `weighted_minor` (généré) ajoutés ; `currency` supprimé ; CK `REALIZED`. `cashflow_runs` : CK `is_current`, horizons.
12. `events` : `causation_depth`, `aggregate_version` ajoutés ; règle d'unicité documentée.
13. `customer_contacts` : UQ `(customer_id, channel, value)` limitée aux contacts actifs.
14. Définitions T1–T12 intégrées au contrat (elles n'existaient que dans la conversation).

## 16. Points restant à spécifier avant Django

Aucune décision de conception n'est ouverte sur le contrat. Restent à **spécifier** (ils n'ajoutent aucune colonne) :
- Import : formats de fichier et validations par entité, taille maximale d'un lot et atomicité de la normalisation (défaut V1 : tout ou rien dans une transaction), politique d'étalement de la libération, rétention du staging `import_rows` (proposition : purge technique 30 jours après `RELEASED`, `raw` contenant des données personnelles).
- Recouvrement : valeurs par défaut du gabarit d'automatisation (seuils des niveaux 1 à 5, canaux).
- Automatisation : liste détaillée des préconditions d'activation (N13).
- Frontière des niveaux avant échéance : les niveaux 3 à 5 avant `OVERDUE` sont-ils autorisés ? (proposition : non, sauf action manuelle motivée.)

## 17. Données personnelles et anonymisation (verrouillé V1)

**Règle.** L'anonymisation ne modifie jamais la vérité financière ni l'intégrité de l'historique.

| Donnée | Traitement |
|---|---|
| Montants, devises, dates métier, états | conservés |
| Identifiants techniques, événements, historiques d'état, allocations | conservés |
| Identité d'un acteur (`users.id`, `*_by`) | l'identifiant est conservé ; `email`/`full_name` anonymisables à la clôture du compte |
| Nom, téléphone, e-mail d'un contact (`customer_contacts`) | anonymisables |
| Raison sociale / n° fiscal d'un client personne physique | anonymisables (`customers.anonymized_at`) |
| Textes libres (`notes`, `reason`, `outcome_note`, `decision_comment`, `resolution_note`) | anonymisables |
| `notifications.payload` | nettoyé |
| `import_rows.raw` | staging contenant des données personnelles : nettoyé ou purgé après libération du lot (§16) |
| `audit_logs.before / after / reason` | minimisation à l'écriture + anonymisation ciblée |

**Minimisation à l'écriture (prioritaire).** Les `payload` d'événements et les `decision_snapshot` ne contiennent que des identifiants, des montants, des états et des dates. Jamais de nom, téléphone ni e-mail. Cette règle est portée par le catalogue d'événements dans le Domain (liste blanche de champs par type d'événement).

**Mécanisme d'anonymisation.**
- Rôle PostgreSQL dédié `verqia_privacy`, distinct du rôle applicatif. Il reçoit un `UPDATE` **au niveau des colonnes** listées ci-dessus et rien d'autre : aucune colonne `*_minor`, date métier ou état n'est modifiable par lui. C'est ce qui rend la règle « vérité financière intacte » vérifiable en base.
- Les triggers append-only (T8) laissent passer le rôle `verqia_privacy` uniquement sur `before`, `after`, `reason`, `anonymized_at`.
- Chaque exécution écrit une ligne `audit_logs` (`action='PII_ANONYMIZED'`, entité, colonnes touchées, base légale ou référence de la demande). Cette ligne ne contient aucune donnée personnelle.
- Valeurs de remplacement : texte `[ANONYMIZED]`, `null` pour les champs facultatifs. `users.email` devient `anonymized+{id}@invalid`, ce qui préserve l'unicité.
- L'anonymisation s'applique aussi aux **archives froides** (§18) : une archive ne doit pas devenir un contournement.
- Un contact anonymisé est `is_active=false`, `consent_status='WITHDRAWN'` ; les recouvrements n'ont plus de destinataire (`NO_CONSENT`).

## 18. Rétention (verrouillé V1)

| Donnée | Conservation opérationnelle | Après |
|---|---|---|
| `risk_snapshots`, `priority_snapshots` | 13 mois | agrégation puis archivage |
| `cashflow_runs`, `cashflow_lines` (runs non courants) | 13 mois | archive ; le **dernier run de chaque mois** pour les horizons 30 et 90 jours est conservé sans limite (comparaison prévu / réalisé) |
| `automation_execution_steps` | 13 mois | archivage |
| `events`, `audit_logs` | 24 mois | archive froide |
| `payment_allocations`, `payment_reversals`, `*_history`, `automation_versions`, factures, paiements, promesses, actions | **aucune limite** | jamais purgés (vérité financière et traçabilité) |

Principes :
- **Archive ≠ suppression.** La V1 ne contient aucun mécanisme de suppression automatique de données métier.
- `events` et `audit_logs` : l'archivage se fait par `DETACH PARTITION` puis export vers le stockage froid. Le `DROP` d'une partition détachée n'a lieu qu'après vérification de l'export, par procédure manuelle et auditée.
- Snapshots et étapes d'exécution (tables non partitionnées en V1) : la politique est **définie** mais son application automatique est **différée**. La V1 fournit la surveillance de volumétrie et un index sur `computed_at`/`executed_at` pour l'archivage futur. Avant toute purge, une table de synthèse mensuelle devra exister (évolution du risque sur plus de 13 mois) ; elle n'est pas créée en V1.
- L'explicabilité d'une action ne dépend pas des snapshots purgés : `collection_actions.decision_snapshot` fige les faits au moment de la décision.
- Purges techniques (hors métier, proposition à confirmer) : `idempotency_keys` après `expires_at`, `event_receipts` après 90 jours.

## 19. Niveaux de recouvrement (verrouillé V1, règles détaillées à valider)

| Niveau | Nom | Contenu type |
|---|---|---|
| 1 | Prévention | avant l'échéance : rappel préventif, information, préparation du paiement |
| 2 | Relance standard | échéance proche ou atteinte : rappel, notification, tâche de suivi |
| 3 | Recouvrement renforcé | retard constaté : relance plus insistante, appel, suivi rapproché |
| 4 | Escalade | retard important ou risque élevé : responsable, manager, traitement prioritaire |
| 5 | Management / critique | exposition importante + risque élevé : intervention managériale |

Le niveau de recouvrement n'est **pas** le niveau de risque. Chaîne : faits → score de risque → niveau de risque ; faits → score de priorité → niveau de priorité ; faits + règles de recouvrement → niveau de recouvrement. Les trois sont enregistrés séparément dans `decision_snapshot`.
Les seuils et bornes entre niveaux (notamment 1/2) vivent dans les définitions d'automatisation versionnées.

## 20. Historique des écarts

Voir §15 (V1 et V1.1). V1.2 : `anonymized_at` sur `users`, `customers`, `customer_contacts`, `notifications`, `audit_logs` ; §17 à §19 ; note FK composites et colonnes générées en §0.

V1.3 (revue d'invariants V1.1) :
1. `invoices.collection_cycle` ajouté. Corrige un défaut de la formule de `dedup_key` : un compte de transitions vers `OVERDUE` ne s'incrémentait pas pour une facture gelée en `OVERDUE` puis rouverte.
2. Trigger T13 : immuabilité de `number`, `customer_id`, `currency`, `issue_date`, `due_date`, `total_minor` après émission.
3. `events.category` ajouté ; règle d'`aggregate_version` précisée.
4. `promises.resolved_amount_minor` ajouté (montant constaté à la résolution).
5. Codes de suppression : `NO_CONTACT`, `NO_CONSENT` séparés ; `CUSTOMER_INACTIVE`, `CUSTOMER_ARCHIVED` ajoutés.
6. `cashflow_runs` : UQ partiel sur `status='RUNNING'`.
7. Non-régression des niveaux de recouvrement formalisée.

V1.3 FIGÉ (décisions D1, D2, D3, D5, D6, D9, N6, N7, N11, N13, N14) :
8. Tables `import_batches` et `import_rows` (39 → 41 tables) ; colonnes `import_batch_id` sur `customers`, `invoices`, `payments` et `events` ; `invoices.origin`.
9. `collection_actions.type` : `MANAGER_ALERT` retiré (D5).
10. Formule du montant recouvrable et règle de suspension (D1) sur `invoice_disputes`.
11. Liste blanche des actions d'automatisation sans `UPDATE_PRIORITY` (D2).
12. Politique d'audit (D3) et garde d'archivage (D6).
13. `collection_actions.dedup_key` et `notifications.dedup_key` : unicité partielle (hors `CANCELLED` et `SUPPRESSED` pour les actions ; hors `CANCELLED` pour les notifications). Corrige un blocage : une action supprimée interdisait définitivement sa remplaçante.
14. `automation_executions.status_reason` : liste fermée de codes.
15. S3 : rattrapage des transitions temporelles à l'émission d'une facture.
16. T14 : garde de transition générée depuis la table de transitions du Domain, sur 12 machines.
17. T15 : `VOID` refusé tant qu'un litige est `OPEN`.
18. `suppression_code` : `IMPORT_HELD` ajouté ; `decision_snapshot` porte `primary_exception`, `exceptions_trace[]`, `overrides[]` ; `computed_at` des projections mis à jour à chaque recalcul (Rule Engine V1.1).
19. Collection Engine V1.1 : `collection_actions.assigned_role` et CK associés ; `outcome` en liste fermée ; formule de `dedup_key` avec `R{occurrence}` (C4, C5, C7).
20. Automation Engine V1.1 : `automations.active_since` (+ CK) ; UQ partiel d'exécution active unique ; index d'exploitation `trigger_key` d'import ; grammaire du `trigger_key` ; note `PAUSE` ; clés documentées de `org_settings.extra` ; sémantique de `release_max_per_day` (AU5, AU6, AU8, AU10, AU12).
21. Engine Contracts V1.1 : `event_receipts.outcome` = `PROCESSED, SKIPPED, DEAD` (renomme `OK`), colonnes `attempts` et `last_error` (EC2, P1, P2).
22. Risk / Priority / Cashflow V1.1 : `factors` et `reasons` normalisés ; définition de `input_hash` (normalisé pour Risk et Priority, brut pour Cashflow) ; note sur `weighted_minor` ; promotion monotone d'un run ; rétention des runs de trésorerie (RP6, RP12, RP14, RP17, RP20).
23. Collection V1.2 (RN1 à RN12) : `RECONCILIATION_PENDING` ajouté à `collection_actions.suppression_code` et à `automation_executions.status_reason` (CK) ; types de notification `RECONCILIATION_REVIEW` et `RECONCILIATION_OVERDUE` ; clé `org_settings.extra.reconciliation_hold_business_days`. Aucune nouvelle colonne ni table : `decision_snapshot` reste immuable, le grant est audité à la création et à chaque vérification à l'exécution.
24. Architecture technique (TD1 à TD59) : `events.available_at` (bail et regroupement) ; `event_receipts.outcome` reçoit `RETRYING` et la colonne `available_at` (prochaine tentative d'un handler, distincte de celle des événements) ; `published_at` = prise en charge par tous les handlers ; `approvals` : propriétaire `approvals` (module dédié) ; `organizations.status` reçoit `PROVISIONING` (défaut) ; module `collection` (singulier). Aucune nouvelle table.
25. AM-01 (passe Collection Domain V1, DV4-4) : `INVARIANTS_V1.md §7.1` corrigé — `collection_actions.dedup_key` restait formulé sans `R{occurrence}`, en retard sur la correction C4 déjà appliquée ici (entrée #19) et dans `COLLECTION_ENGINE_V1.md §4/§19`. Aucune nouvelle colonne ni contrainte : correction de rédaction, la formule réelle (`text` opaque, §6.2) n'a jamais changé.
26. AM-02 (passe Collection Domain V1, DV4-7) : `COLLECTION_ENGINE_V1.md §12` corrigé — la table des réactions ne listait que `ORGANIZATION_SUSPENDED` pour `SUPPRESSED(ORG_INACTIVE)`, alors que `ORGANIZATION_CLOSED` reçoit **déjà** le même traitement d'après une décision antérieure et validée (`STATE_MACHINES_V1.md` §1 ligne 277 et note S10 : « `ORGANIZATION_CLOSED` traité comme `ORGANIZATION_SUSPENDED` par `collection` et `automation` », VALIDÉ Architecture technique TD59, appliqué). `specs.py` (`SuppressOnOrgSuspended`) implémentait déjà les deux événements correctement. Pas une nouvelle règle : mise en cohérence rédactionnelle d'un document resté en retard sur une décision déjà actée ailleurs.
