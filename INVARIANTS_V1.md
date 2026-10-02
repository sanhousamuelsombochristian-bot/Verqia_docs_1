# VERQIA — Revue d'invariants V1.2

Objet : transformer le Data Contract V1.3 en règles de moteur métier, objet par objet.
Pour chaque objet : **1 créer · 2 modifier · 3 immuable · 4 transitions · 5 erreurs · 6 événements**.

Statut des règles :
- **[CONTRAT]** déjà porté par le Data Contract V1.3 (contrainte, index ou trigger).
- **[VERROUILLÉ]** / **[VALIDÉ Nx]** décision validée (les décisions nouvelles sont numérotées N1… en §11).
- **[PROPOSÉ]** nouvelle règle que je recommande ; elle n'est pas dans le contrat tant que tu ne l'as pas validée.
- **[OUVERT]** dépend d'une décision D1–D9 non tranchée.

Toutes les erreurs sont des **erreurs de domaine à code stable** (`CODE_EN_MAJUSCULES`), traduites en HTTP par la couche API : 404 pour un objet hors tenant (jamais 403, pour ne pas révéler son existence), 409 pour conflit d'état ou de version, 422 pour une règle métier violée, 400 pour un format invalide.

---

## Règles communes à tous les objets

| # | Règle |
|---|---|
| C1 | Toute écriture métier appartient à **un use case** ; la vue API ne contient aucune règle. |
| C2 | Toute écriture porte `organization_id`, vérifié à trois niveaux : filtre applicatif, FK composite, RLS. |
| C3 | **Toute transition d'état est atomique et conditionnée par l'état attendu** : `UPDATE … WHERE état = ancien` dans la même requête. Zéro ligne modifiée ⇒ `INVALID_TRANSITION` ou `CONCURRENT_MODIFICATION`. Ne s'applique pas aux modifications ordinaires (ex. `legal_name`), qui relèvent de C4. |
| C4 | Toute modification d'un agrégat à verrou optimiste incrémente `version` ; un conflit renvoie `CONCURRENT_MODIFICATION` (409), à rejouer par le client. |
| C5 | Toute mutation métier significative et toute transition d'état produisent au minimum un événement outbox **dans la même transaction**. Une transition d'état a obligatoirement son événement. Un événement peut représenter une création, une mutation append-only, une demande de traitement, un résultat de projection ou une transition d'état : il n'implique donc pas une transition d'état (catégories en §10). |
| C6 | Une commande rejouée avec la même `idempotency_key` et le même contenu renvoie la première réponse ; avec un contenu différent : `IDEMPOTENCY_KEY_REUSED`. |
| C7 | Une organisation non `ACTIVE` n'exécute aucune automatisation et n'envoie aucune communication (`ORG_NOT_ACTIVE`). |
| C8 | Toute correction d'une donnée financière immuable se fait par **annulation + nouvelle saisie**, jamais par modification. |
| C9 | Payloads d'événements : identifiants, montants, états, dates. Aucune donnée personnelle (contrat §17). |
| C10 | Toute « date courante » (échéances, `value_date`, `promised_date`, fenêtres de communication, jours ouvrés) s'évalue dans le **fuseau horaire de l'organisation**, jamais celui du serveur. |
| C11 | Trois issues distinctes d'une erreur : **REPLAY** idempotent (l'objet existant est renvoyé), **SKIPPED** (no-op légitime : événement obsolète, action supprimée par une exception métier) et **erreur de domaine**. `ACTION_DUPLICATE`, `CASHFLOW_RUN_EXISTS` et `STALE_INPUT` sont des REPLAY ou SKIPPED, plus des erreurs. |
| C12 | Exceptions déclarées à « un agrégat par transaction » : **liste fermée et nominative, sans formule ouverte** : `AllocatePayment`, `ReverseAllocation`, `ReversePayment` (EC-05 : Payment + Invoice) et `NormalizeImportBatch` (matérialisation d'un lot d'import dans `customers`, `invoices` et `payments`, tout ou rien, EC1). `CreateOrganization` n'en fait plus partie : c'est un **plan de provisioning**, une transaction par étape (§1). Toute autre opération inter-agrégats passe par événement ou par **composition orchestrée** : chaque module écrit dans **sa** transaction, à la demande de l'appelant, avec idempotence propre (Architecture technique, TD58). |
| C13 | **Audit [VERROUILLÉ D3]** : sont écrits dans `audit_logs`, dans la transaction, les commandes d'un utilisateur ou d'une automatisation, les changements de configuration et de droits, les holds, les approbations et les actions sensibles. Les transitions purement temporelles du Scheduler restent dans `*_history` et `events`, sans doublon d'audit. |

---

## 1. Organization

| | Règle |
|---|---|
| **1 Créer** | Nom, `slug` unique, devise, fuseau IANA, pays. **Plan de provisioning** (Architecture technique, TD59) : l'organisation et ses `org_settings` sont écrits à l'état `PROVISIONING` ; puis chaque **étape** du port `ProvisioningStep` s'exécute **dans sa propre transaction**, avec son propriétaire et son idempotence `(organisation, étape)` : membre `OWNER` (`identity`), abonnement d'essai (`billing`), jeu d'automatisations modèles (`automation`, créées en `DRAFT` ; l'activation est explicite, par un `OWNER` **[VERROUILLÉ N13]**). Quand toutes les étapes sont faites, l'organisation passe `ACTIVE` et `ORGANIZATION_CREATED` est émis. Tant qu'elle est `PROVISIONING`, aucune commande métier n'y est acceptée. |
| **2 Modifier** | `name`, `timezone`, `org_settings`, `status`. `default_currency` **uniquement tant qu'aucune facture ni aucun paiement n'existe**. [PROPOSÉ] |
| **3 Immuable** | `id`, `slug` (en V1), `created_at` ; `default_currency` dès la première donnée financière. |
| **4 Transitions** | `PROVISIONING → ACTIVE` (système, toutes les étapes faites) ; `PROVISIONING → CLOSED` (abandon) ; `ACTIVE ⇄ SUSPENDED` ; `ACTIVE/SUSPENDED → CLOSED` (terminal, aucune donnée supprimée). `SUSPENDED` : plus d'automatisation ni de communication sortante, lecture et gestion de l'abonnement seulement. `CLOSED` : lecture et export seulement. |
| **5 Erreurs** | `ORG_SLUG_TAKEN` · `ORG_CURRENCY_LOCKED` · `ORG_NOT_ACTIVE` · `LAST_OWNER_REQUIRED` (retrait ou rétrogradation du dernier `OWNER`) · `ORG_TIMEZONE_INVALID` |
| **6 Événements** | `ORGANIZATION_CREATED`, `ORGANIZATION_UPDATED`, `ORGANIZATION_SUSPENDED`, `ORGANIZATION_REACTIVATED`, `ORGANIZATION_CLOSED`, `ORG_SETTINGS_CHANGED` |

Changer le fuseau horaire n'agit que sur les calculs futurs (fenêtres de communication, jours ouvrés) ; il ne réécrit aucun historique. [VALIDÉ]

**Activation d'une automatisation [VERROUILLÉ N13].** `DRAFT → ACTIVE` exige des préconditions (liste détaillée à spécifier dans la passe Automation Engine) : activation par un `OWNER` ou un `ADMIN`, version courante valide au schéma, gabarits de message actifs pour les canaux utilisés, au moins un canal utilisable. Sinon `AUTOMATION_PRECONDITIONS_NOT_MET`. Tant qu'une automatisation n'est pas `ACTIVE`, elle ne produit **aucune** exécution ni aucune relance.

---

## 2. Customer

| | Règle |
|---|---|
| **1 Créer** | `code` unique par organisation (généré s'il est omis), `legal_name`. Statut `ACTIVE`. Contacts facultatifs. Un seul contact principal par canal. [CONTRAT] |
| **2 Modifier** | `legal_name`, `tax_id`, `external_ref`, `status`, contacts (ajout, désactivation, consentement). |
| **3 Immuable** | `id`, `code` (référencé par des systèmes externes), `created_at`. Un contact n'est jamais supprimé : `is_active=false`. |
| **4 Transitions** | `ACTIVE ⇄ INACTIVE` ; `ACTIVE/INACTIVE → ARCHIVED` ; `ARCHIVED → ACTIVE` réservé à `ADMIN`, avec motif. Effet de chaque état : matrice ci-dessous **[VALIDÉ N3]**. |
| **5 Erreurs** | `CUSTOMER_CODE_TAKEN` · `CUSTOMER_INACTIVE` / `CUSTOMER_ARCHIVED` · `CUSTOMER_HAS_OPEN_INVOICES` (archivage) **[VERROUILLÉ D6]** · `CONTACT_PRIMARY_CONFLICT` · `CONTACT_INVALID_VALUE` |
| **6 Événements** | `CUSTOMER_CREATED`, `CUSTOMER_UPDATED`, `CUSTOMER_DEACTIVATED`, `CUSTOMER_ARCHIVED`, `CUSTOMER_REACTIVATED`, `CUSTOMER_CONTACT_ADDED`, `CUSTOMER_CONTACT_UPDATED` |

**Matrice des états du client [VALIDÉ N3].** Un client archivé interdit les nouvelles opérations commerciales, mais ne bloque pas les opérations nécessaires pour corriger ou clôturer l'historique financier.

| Opération | ACTIVE | INACTIVE | ARCHIVED |
|---|:-:|:-:|:-:|
| Lire, exporter | ✅ | ✅ | ✅ |
| Modifier l'identité | ✅ | ✅ | ❌ |
| Créer une facture | ✅ | ❌ | ❌ |
| Créer une promesse | ✅ | ❌ | ❌ |
| Créer une action de recouvrement | ✅ | ❌ | ❌ |
| Exécuter une action déjà planifiée | ✅ | ❌ (`SUPPRESSED`, `CUSTOMER_INACTIVE`) | ❌ (`SUPPRESSED`, `CUSTOMER_ARCHIVED`) |
| Enregistrer un paiement | ✅ | ✅ | ❌ (réactivation requise) |
| Allouer un paiement existant | ✅ | ✅ | ✅ |
| Reverser une allocation ou un paiement | ✅ | ✅ | ✅ |
| Annuler (`CANCELLED`/`VOID`) une facture existante | ✅ | ✅ | ✅ |

Réactiver un client `ARCHIVED` : rôle `ADMIN`, avec motif. Le refus d'enregistrer un paiement d'un client archivé n'est pas un blocage définitif : un encaissement réel force une décision humaine (réactivation), il n'est pas perdu.

Le Scheduler **revalide** le statut du client avant chaque exécution : une action `SCHEDULED` d'un client devenu `INACTIVE` ou `ARCHIVED` passe en `SUPPRESSED`.

**Archivage [VERROUILLÉ D6].** L'archivage est **refusé** tant qu'il existe une facture `DRAFT`, `ISSUED`, `DUE_SOON`, `DUE` ou `OVERDUE` dont le règlement n'est pas `PAID` (`CUSTOMER_HAS_OPEN_INVOICES`). Ce garde vaut au moment de l'archivage. Un reversal ultérieur (opération autorisée) peut rouvrir une facture : elle reste **non recouvrable automatiquement** (`CUSTOMER_ARCHIVED`), une notification `CUSTOMER_ARCHIVED_BALANCE_REOPENED` est envoyée aux `ADMIN`, et le client n'est **jamais** réactivé automatiquement. Une correction financière ne doit pas produire silencieusement une réactivation commerciale.

Invariant structurel [CONTRAT] : aucun solde, encours ni retard n'est stocké sur le client.
`CUSTOMER_UPDATED` ne transporte que la liste des champs modifiés, pas leurs valeurs (C9).

---

## 3. Invoice (avec ses lignes et ses litiges)

| | Règle |
|---|---|
| **1 Créer** | En `DRAFT`. Client `ACTIVE`, devise = devise de l'organisation, `number` unique, `due_date >= issue_date`. `total_minor >= 0` en brouillon **[VERROUILLÉ]**. Le total est **calculé** depuis les lignes, jamais saisi. |
| **2 Modifier** | En `DRAFT` : tout (client, dates, lignes). Après émission : uniquement `notes` et `external_ref`. Le cycle de vie et le règlement ne bougent que par les mécanismes du §4. |
| **3 Immuable après émission** | `number`, `customer_id`, `currency`, `issue_date`, `total_minor`, lignes [CONTRAT T7] ; `due_date` aussi **[VALIDÉ N1]** : une échéance renégociée passe par une **promesse**, pas par une réécriture de la date (sinon les retards passés deviennent invérifiables). Porté par le trigger T13 (contrat §14). Les créations par import (INSERT) ne sont pas concernées. |
| **4 Transitions** | Voir tableau ci-dessous. |
| **5 Erreurs** | `INVOICE_EMPTY` · `INVOICE_TOTAL_MUST_BE_POSITIVE` (émission) **[VERROUILLÉ]** · `INVOICE_NUMBER_TAKEN` · `INVOICE_FIELD_LOCKED` · `INVOICE_HAS_PAYMENTS` (annulation) · `INVOICE_HAS_OPEN_DISPUTE` (`VOID` refusé tant qu'un litige est `OPEN`, S5, T15 ; **B3-c**) · `INVOICE_DATES_INVALID` · `CUSTOMER_INACTIVE` / `CUSTOMER_ARCHIVED` · `INVALID_TRANSITION` · `CONCURRENT_MODIFICATION` |
| **6 Événements** | Voir tableau ci-dessous. |

### 3.1 Cycle de vie

| Transition | Garde | Événement |
|---|---|---|
| `DRAFT → ISSUED` | ≥ 1 ligne, total > 0, T9, client et organisation `ACTIVE` | `INVOICE_ISSUED` |
| `DRAFT → CANCELLED` | — | `INVOICE_CANCELLED` |
| `ISSUED → DUE_SOON` | `due_date - due_soon_days <= aujourd'hui` et règlement ≠ `PAID` | `INVOICE_DUE_SOON` |
| `ISSUED / DUE_SOON → DUE` | `due_date = aujourd'hui` et règlement ≠ `PAID` | `INVOICE_DUE` |
| `ISSUED / DUE_SOON / DUE → OVERDUE` | `due_date < aujourd'hui` et règlement ≠ `PAID` | `INVOICE_OVERDUE` |
| `ISSUED / DUE_SOON / DUE / OVERDUE → VOID` | `paid_minor = 0` et aucun litige `OPEN` (S5, T15) | `INVOICE_VOIDED` |

Les sauts de cycle de vie sont légaux (`ISSUED → OVERDUE` pour une facture émise en retard ou importée). Une facture `PAID` est **gelée** ; si son règlement est annulé, son cycle de vie est recalculé immédiatement. **Deux chemins de création distincts [VERROUILLÉ D9]** : `CreateInvoice` produit toujours un `DRAFT` ; `ImportHistoricalInvoice` est un use case séparé qui reconstruit l'état historique (facture directement `OVERDUE` ou `PAID`, avec son historique d'états), `origin='IMPORTED'`. Aucun autre chemin ne crée une facture hors `DRAFT`. Séquence et règles de l'import : §9 bis.

### 3.1 bis Cycle de recouvrement (`invoices.collection_cycle`) [N12]

Compteur stocké, initialisé à 0, incrémenté par le Domain dans la transaction qui :
- fait entrer la facture en `OVERDUE` (transition), **ou**
- annule un règlement (`PAID → …`) alors que le cycle de vie est **déjà** `OVERDUE` (le cycle de vie n'a pas bougé, mais le retard recommence pour le recouvrement).

Il structure `dedup_key` et la non-régression des niveaux (§7.1). Il n'est jamais décrémenté. Les actions de niveaux 1–2 (avant échéance) appartiennent au cycle 0.

### 3.2 Règlement (uniquement par allocation ou reversal)

| Transition | Événement |
|---|---|
| `UNPAID → PARTIALLY_PAID` | `INVOICE_PARTIALLY_PAID` |
| `UNPAID / PARTIALLY_PAID → PAID` | `INVOICE_PAID` |
| `PARTIALLY_PAID → PARTIALLY_PAID` (montant modifié) | aucun événement de facture (`PAYMENT_ALLOCATED` suffit) |
| `PAID → PARTIALLY_PAID / UNPAID`, `PARTIALLY_PAID → UNPAID` | `INVOICE_SETTLEMENT_REVERTED` |

### 3.3 Litige (`invoice_disputes`) — dimension orthogonale **[VERROUILLÉ]**
| | Règle |
|---|---|
| Créer | Facture en cycle de vie `ISSUED…OVERDUE` et règlement ≠ `PAID`. Un seul litige `OPEN` par facture [CONTRAT]. `disputed_amount_minor` facultatif, `<= total` [CONTRAT T11]. Motif obligatoire. |
| Modifier | Montant contesté et motif tant que `OPEN` (avec audit). |
| Transitions | `OPEN → RESOLVED_VALID` (contestation fondée) ou `RESOLVED_REJECTED` (rejetée). Terminaux. |
| Effet | Un litige ouvert **ne change pas** l'état de la facture. Il agit sur le recouvrement (règle ci-dessous) et le cashflow (part contestée en `AT_RISK`). |
| Erreurs | `DISPUTE_ALREADY_OPEN` · `DISPUTE_INVOICE_NOT_DISPUTABLE` · `DISPUTE_AMOUNT_EXCEEDS_TOTAL` · `DISPUTE_REASON_REQUIRED` |
| Événements | `INVOICE_DISPUTED`, `INVOICE_DISPUTE_RESOLVED` (avec l'issue) |

**Recouvrement pendant un litige [VERROUILLÉ D1].** `collectible_minor = outstanding_minor` sans litige ouvert ; `0` pour un litige total (`disputed_amount_minor IS NULL`) ; sinon `max(outstanding_minor − disputed_amount_minor, 0)`. Le recouvrement standard est suspendu si et seulement si `collectible_minor = 0` (`suppression_code = DISPUTED`). Un litige partiel ne suspend donc pas le recouvrement de la part non contestée, et l'action tient compte du montant recouvrable.

**Limite V1 à connaître.** Sans avoirs, un litige **fondé** ne peut pas réduire le total d'une facture émise. La procédure V1 est : reverser les allocations, `VOID` la facture, en émettre une nouvelle, réallouer. Elle est lourde ; les avoirs (hors V1) la simplifieront.

---

## 4. Payment

| | Règle |
|---|---|
| **1 Créer** | Client non archivé, `amount_minor > 0`, devise = devise de l'organisation, `reference` unique par méthode (référence interne générée pour les espèces), `value_date <=` date courante **dans le fuseau de l'organisation** **[VALIDÉ N2, C10]** (un encaissement futur n'est pas réalisé), `received_at <= maintenant`. Clé d'idempotence obligatoire. Statut `RECEIVED`. |
| **2 Modifier** | `notes` uniquement. |
| **3 Immuable** | `amount_minor`, `currency`, `customer_id`, `reference`, `method`, `received_at`, `value_date`. Une erreur de saisie se corrige par **reversal + nouveau paiement** (C8). |
| **4 Transitions** | `RECEIVED → PARTIALLY_ALLOCATED → ALLOCATED` par allocations ; retour arrière par reversals d'allocations ; `* → REVERSED` par reversal du paiement (terminal), qui reverse **dans la même transaction** toutes ses allocations actives. |
| **5 Erreurs** | `PAYMENT_DUPLICATE_REFERENCE` · `PAYMENT_AMOUNT_INVALID` · `PAYMENT_CURRENCY_MISMATCH` · `PAYMENT_DATE_IN_FUTURE` · `PAYMENT_ALREADY_REVERSED` · `PAYMENT_REVERSAL_REASON_REQUIRED` · `CUSTOMER_ARCHIVED` · `IDEMPOTENCY_KEY_REUSED` |
| **6 Événements** | `PAYMENT_CREATED`, `PAYMENT_REVERSED` ; les allocations émettent les leurs (§5). |

Le disponible à affecter vaut `amount_minor - allocated_minor`. Il n'est jamais stocké [CONTRAT].

---

## 5. Allocation et reversal (`payment_allocations`)

| | Règle |
|---|---|
| **1 Créer (allocation)** | Paiement ≠ `REVERSED` ; facture en cycle de vie `ISSUED…OVERDUE` (pas `DRAFT`, `CANCELLED`, `VOID`) ; même client et même devise (garanti par les FK composites) ; `0 < montant <= min(disponible du paiement, solde de la facture)`. Une facture en litige **peut** recevoir une allocation : un paiement reçu est un fait. Verrous : paiement d'abord, factures triées par `id`. |
| **1 Créer (reversal)** | Vise une allocation d'origine (même paiement, même facture) ; montant `<=` reliquat non reversé de l'origine ; motif obligatoire ; autorisé quel que soit l'état de la facture (nécessaire pour annuler une facture). |
| **2 Modifier** | Rien. |
| **3 Immuable** | Tout : la table est append-only (T8). Seul le rôle de confidentialité peut toucher aux textes libres (contrat §17). |
| **4 Transitions** | Aucune (pas d'état propre). Elles produisent des transitions sur la facture (§3.2) et le paiement (§4) **dans la même transaction**. |
| **5 Erreurs** | `ALLOCATION_EXCEEDS_PAYMENT_AVAILABLE` · `ALLOCATION_EXCEEDS_INVOICE_OUTSTANDING` · `ALLOCATION_CUSTOMER_MISMATCH` · `ALLOCATION_CURRENCY_MISMATCH` · `ALLOCATION_INVOICE_NOT_PAYABLE` · `ALLOCATION_PAYMENT_REVERSED` · `REVERSAL_EXCEEDS_ORIGINAL` · `REVERSAL_REASON_REQUIRED` · `CONCURRENT_MODIFICATION` |
| **6 Événements** | `PAYMENT_ALLOCATED`, `PAYMENT_ALLOCATION_REVERSED` (agrégat `PAYMENT`, §10.2) + les événements de facture du §3.2 (agrégat `INVOICE`) |

Les erreurs `MISMATCH` sont attrapées en amont par le use case ; la base les rejette de toute façon (FK composite), c'est le filet de sécurité.

---

## 6. Promise

| | Règle |
|---|---|
| **1 Créer** | Enregistrée par un utilisateur. Portée facture : facture ouverte (`ISSUED…OVERDUE`, règlement ≠ `PAID`). Portée client (`invoice_id` NULL) : au moins une facture ouverte. `promised_amount_minor > 0`. Promesse de facture : `<=` solde de la facture. Promesse client : `<=` **encours ouvert et éligible** du client à la création (Σ `outstanding_minor` des factures `ISSUED…OVERDUE` non soldées ; la déduction des montants contestés dépend de D1) **[VALIDÉ N5]**. `promised_date >=` date courante dans le fuseau de l'organisation (C10). Client `ACTIVE`. Aucune autre promesse `ACTIVE` sur la même portée. `grace_days` copié depuis `org_settings`. |
| **2 Modifier** | `note` uniquement. Changer la date ou le montant = **annuler puis recréer** (l'historique reste lisible) **[VERROUILLÉ N11]** (aucun `UPDATE` de ces champs). |
| **3 Immuable** | Portée, montant, date, `grace_days`, devise. |
| **4 Transitions** | `ACTIVE → FULFILLED` : **montant constaté** `>=` montant promis, ou facture devenue `PAID` **[VALIDÉ N6]**. Montant constaté = Σ (allocations − reversals) de la portée (facture ou client), sur les paiements non `REVERSED` dont `value_date >=` date de création de la promesse (fuseau de l'organisation). Il est enregistré dans `promises.resolved_amount_minor` à la résolution. `ACTIVE → BROKEN` : `aujourd'hui > promised_date + grace_days` sans exécution. `ACTIVE → CANCELLED` : par un utilisateur, ou facture `VOID`/`CANCELLED`. États terminaux. |
| **5 Erreurs** | `PROMISE_ALREADY_ACTIVE` · `PROMISE_DATE_IN_PAST` · `PROMISE_AMOUNT_INVALID` · `PROMISE_AMOUNT_EXCEEDS_OUTSTANDING` · `PROMISE_INVOICE_NOT_OPEN` · `PROMISE_NOT_ACTIVE` (modification d'une promesse résolue) |
| **6 Événements** | `PROMISE_CREATED`, `PROMISE_FULFILLED`, `PROMISE_BROKEN`, `PROMISE_CANCELLED` |

Effets : une promesse `ACTIVE` suspend les relances **standard** ; `PROMISE_BROKEN` lève la suspension et pèse sur le risque.
**[VERROUILLÉ N6]** `FULFILLED` est terminal : la promesse a bien été satisfaite au moment où le paiement était valide. Si ce paiement est reversé ensuite, la promesse n'est ni rouverte ni transformée en `BROKEN`. Le reversal produit ses propres événements (`PAYMENT_ALLOCATION_REVERSED`, `INVOICE_SETTLEMENT_REVERTED`), dont les consommateurs demandent les recalculs de risque et de cashflow ; une nouvelle promesse peut être créée. VERQIA ne réécrit pas l'histoire d'une promesse.
**Promesse client sans facture ouverte.** Si une promesse client `ACTIVE` n'a plus aucune facture ouverte (par exemple après des `VOID`), elle est annulée automatiquement (`CANCELLED`, motif `NO_OPEN_INVOICE`). La vérification `FULFILLED` s'exécute sur `PAYMENT_ALLOCATED`, `INVOICE_PAID` et par balayage quotidien.

---

## 7. Collection Action (avec Hold et Approval)

### 7.1 Collection Action

| | Règle |
|---|---|
| **1 Créer** | Uniquement par le Collection Engine (via automatisation) ou par un utilisateur (`origin='MANUAL'`). Préconditions revalidées à la création **et** juste avant exécution, dans l'ordre : organisation active (`ORG_INACTIVE`) → client actif (`CUSTOMER_INACTIVE`, `CUSTOMER_ARCHIVED`) → facture ouverte (ni `PAID`, ni `VOID`/`CANCELLED`) → litige (montant recouvrable = 0, D1) → promesse active → hold en vigueur → limite de fréquence → contact utilisable (`NO_CONTACT`) → consentement (`NO_CONSENT`). Le consentement conditionne les messages sortants automatiques ; une tâche d'appel humaine exige seulement un contact joignable **[VALIDÉ N4]**. La première exception rencontrée donne le `suppression_code`. `level` entre 1 et 5 [VERROUILLÉ]. `decision_snapshot` obligatoire, avec **séparément** niveau de risque, niveau de priorité, niveau de recouvrement et version des règles. `dedup_key = {invoice_id}:{type}:L{level}:C{cycle}:R{occurrence}`, avec `cycle = invoices.collection_cycle` (§3.1 bis) et `occurrence` déterministe, produit par l'Automation Engine (jamais choisi par le Collection Engine ni fourni par un appelant, Collection V1.1 §19 C4). |
| **2 Modifier** | `scheduled_for` (tant que `PROPOSED`/`SCHEDULED`), `assigned_to`, `outcome`, `outcome_note`. |
| **3 Immuable** | `invoice_id`, `customer_id`, `type`, `level`, `origin`, `decision_snapshot`, `dedup_key`. Changer de niveau = annuler et recréer. |
| **4 Transitions** | `PROPOSED → SCHEDULED / PENDING_APPROVAL / SUPPRESSED` · `PENDING_APPROVAL → SCHEDULED / CANCELLED / SUPPRESSED` · `SCHEDULED → EXECUTING / SUPPRESSED / CANCELLED` · `SCHEDULED → DONE` (tâche humaine seulement, par un utilisateur, issue obligatoire) · `EXECUTING → DONE / SCHEDULED (retry) / FAILED` · tout état non terminal `→ CANCELLED`. `SUPPRESSED` : le système a empêché l'action parce que le contexte métier l'exigeait ; `CANCELLED` : un acteur ou une décision explicite l'annule. Terminaux : `DONE`, `FAILED`, `CANCELLED`, `SUPPRESSED`. |
| **5 Erreurs** | `ACTION_APPROVAL_REQUIRED` · `ACTION_MAX_ATTEMPTS_REACHED` · `ACTION_LEVEL_REGRESSION` · `ACTION_LEVEL_BELOW_MINIMUM` · `ACTION_INVALID_TRANSITION` · `ACTION_LEVEL_INVALID` · `CUSTOMER_INACTIVE` / `CUSTOMER_ARCHIVED` (création manuelle) |
| **Issues non fautives (C11)** | **REPLAY** : action déjà existante pour la même `dedup_key` (l'action existante est renvoyée). **SKIPPED** : action créée en `SUPPRESSED` avec son `suppression_code` (`PAID`, `VOIDED`, `DISPUTED`, `PROMISE_ACTIVE`, `HOLD_ACTIVE`, `FREQUENCY_LIMIT`, `NO_CONTACT`, `NO_CONSENT`, `CUSTOMER_INACTIVE`, `CUSTOMER_ARCHIVED`, `ORG_INACTIVE`). |
| **6 Événements** | `COLLECTION_ACTION_PROPOSED`, `_SCHEDULED`, `_EXECUTED`, `_FAILED`, `_CANCELLED`, `_SUPPRESSED` |

**Règles propres aux niveaux.**
- **Non-régression [VALIDÉ N7].** Pour une facture et un `collection_cycle` donnés : `niveau_atteint = max(level)` sur les actions en état `SCHEDULED`, `EXECUTING` ou `DONE`. Une nouvelle action de niveau `< niveau_atteint` est refusée (`ACTION_LEVEL_REGRESSION`), sauf action manuelle avec motif. Les états `PROPOSED`, `PENDING_APPROVAL`, `CANCELLED`, `SUPPRESSED` et `FAILED` ne comptent pas : une action de niveau 4 en attente d'approbation ne bloque pas un niveau 3, et une action annulée ne « consomme » aucun niveau.
- **Frontière niveaux 1 / 2 [VALIDÉ N8].** Le moteur ne connaît que le concept de niveau ; les seuils temporels vivent dans la définition d'automatisation versionnée. Le gabarit par défaut place le niveau 2 à partir de `INVOICE_DUE_SOON`.
- **Niveau minimal [VERROUILLÉ N7].** Les niveaux 1 et 2 s'appliquent à des factures non échues (cycle 0). Dès qu'une facture est `OVERDUE`, le niveau minimal de recouvrement automatique est **3** : aucune règle ne peut produire L1 ou L2 sur une facture en retard (`ACTION_LEVEL_BELOW_MINIMUM`).
- **[À CONFIRMER dans la passe Collection Engine]** Niveaux 3 à 5 avant `OVERDUE` : proposition, interdits sauf action manuelle motivée.
- Un horaire hors fenêtre de communication n'est **pas une erreur** : l'action est reprogrammée au prochain créneau autorisé.

### 7.2 Hold (suspension manuelle)

| | Règle |
|---|---|
| **Créer** | Rôle `MANAGER` ou plus, **motif obligatoire**, portée `INVOICE`/`CUSTOMER`/`ORGANIZATION`, cible cohérente avec la portée, `automation_id` facultatif (NULL = toutes). Pas de chevauchement pour la même cible, la même automatisation et le même type [CONTRAT]. |
| **Modifier** | `ends_at` (prolonger ou raccourcir, audité). |
| **Immuable** | Portée, cible, `kind`, `reason`, `placed_by`, `starts_at`. |
| **Transitions** | `ACTIVE → RELEASED` (avec `release_reason`) ou `ACTIVE → EXPIRED`. Terminaux. Le hold est en vigueur d'après `starts_at`/`ends_at`, indépendamment du balayage `EXPIRED`. |
| **Erreurs** | `HOLD_REASON_REQUIRED` · `HOLD_OVERLAP` · `HOLD_TARGET_MISMATCH` · `HOLD_NOT_ACTIVE` · `INSUFFICIENT_ROLE` |
| **Événements** | `COLLECTION_HOLD_PLACED`, `COLLECTION_HOLD_RELEASED` (l'expiration émet `RELEASED` avec `cause='EXPIRED'`) |

### 7.3 Approval

| | Règle |
|---|---|
| **Créer** | Par le moteur (action ou étape d'exécution), avec `reason`, `context`, `expires_at`, et un destinataire (utilisateur **ou** rôle). `kind` = `APPROVAL` ou `REVIEW`. |
| **Décider** | Approbateur éligible : rôle `MANAGER` ou plus **et** `approval_limit_minor >=` montant concerné ; différent du demandeur si la politique l'impose. Une seule décision. |
| **Transitions** | `PENDING → APPROVED / REJECTED / EXPIRED`. Terminaux. `APPROVED` reprend l'action (`SCHEDULED`) ; `REJECTED` et `EXPIRED` l'annulent (issues `APPROVAL_REJECTED`, `APPROVAL_EXPIRED`). Si la cible est résolue pendant l'attente : l'action passe en `SUPPRESSED`, l'approbation en `EXPIRED` avec `TARGET_RESOLVED`. |
| **Erreurs** | `APPROVER_NOT_ELIGIBLE` · `APPROVAL_ALREADY_DECIDED` · `APPROVAL_EXPIRED` · `SELF_APPROVAL_FORBIDDEN` · `APPROVAL_COMMENT_REQUIRED` (rejet) |
| **Événements** | `APPROVAL_REQUESTED`, `APPROVAL_GRANTED`, `APPROVAL_REJECTED` |

---

## 8. Risk et Priority (projections)

| | Règle |
|---|---|
| **1 Créer** | **Uniquement par les moteurs**, sur événement, sur demande explicite ou par balayage. Aucun endpoint d'écriture pour un utilisateur. `risk_profiles` : par client ; `priority_items` : par facture ouverte. |
| **2 Modifier** | Le profil courant est **remplacé** à chaque recalcul dont l'entrée a changé. Même `model_version` et même `input_hash` ⇒ **aucun nouveau snapshot ni événement, mais `computed_at` est mis à jour** (la barrière de fraîcheur du Rule Engine en dépend, `RULE_ENGINE_V1.md` §2.3). |
| **3 Immuable** | Chaque snapshot [CONTRAT T8]. |
| **4 Transitions** | Niveaux de risque `LOW / MEDIUM / HIGH / CRITICAL` ; de priorité `NONE / WATCH / ACTION / PRIORITY / CRITICAL`. Pas de machine à états stricte : tout niveau est atteignable depuis tout niveau. `priority_items` passe à `NONE` (ou disparaît) quand la facture est `DRAFT`, `PAID`, `CANCELLED` ou `VOID`. |
| **5 Erreurs** | `RISK_MODEL_UNKNOWN` · `PRIORITY_MODEL_UNKNOWN` · `CONCURRENT_MODIFICATION` (rejoué par le worker). Issues non fautives (C11) : **SKIPPED** pour un événement plus ancien que l'état courant ; **REPLAY** pour une entrée identique (`input_hash`). |
| **6 Événements** | `RISK_CHANGED` et `PRIORITY_CHANGED` **seulement si le niveau change**. Un changement de score sans changement de niveau produit un snapshot mais aucun événement. Demandes : `RISK_RECALCULATION_REQUESTED`, `PRIORITY_RECALCULATION_REQUESTED`. |

Règles de cohérence :
- Le risque ne dépend jamais du niveau de recouvrement, et inversement (contrat §19).
- Un recalcul relit l'état courant en base ; il ne se fie pas au payload de l'événement (C9 et contrat §12.1).
- Le nombre de recalculs est borné par `causation_depth`.
- **[VERROUILLÉ D2]** `UPDATE_PRIORITY` est supprimé de la liste blanche d'actions. Une automatisation émet `PRIORITY_RECALCULATION_REQUESTED` ; seul le Priority Engine modifie `priority_items`.

---

## 9. Cashflow

| | Règle |
|---|---|
| **1 Créer** | **Uniquement par le Cashflow Engine** : quotidien, sur demande, ou sur événement avec regroupement (au plus un run par couple horizon/scénario dans un intervalle court **[PROPOSÉ]**, pour qu'une rafale de paiements ne produise pas cent runs). Horizon ∈ {7, 30, 60, 90, 180, 365}, scénario ∈ {`BASE`, `OPTIMISTIC`, `PESSIMISTIC`} [VERROUILLÉ]. |
| **2 Modifier** | Le run évolue seulement de `RUNNING` vers `COMPLETED` ou `FAILED`, puis `is_current` bascule. Les lignes ne sont jamais modifiées. |
| **3 Immuable** | Un run `COMPLETED` (hypothèses, version de modèle, lignes). Un nouveau calcul crée un **nouveau** run. |
| **4 Transitions** | `RUNNING → COMPLETED / FAILED`. `is_current` : seul un run `COMPLETED` peut l'être ; on désactive l'ancien puis on active le nouveau, dans une transaction. |
| **5 Erreurs** | `CASHFLOW_HORIZON_INVALID` · `CASHFLOW_SCENARIO_INVALID` · `CASHFLOW_MODEL_UNKNOWN` · `CASHFLOW_RUN_CONFLICT` (un run est déjà `RUNNING` pour ce couple horizon/scénario avec un `input_hash` différent) · `CASHFLOW_INPUT_INCONSISTENT`. Même `input_hash` que le run courant : **REPLAY** (le run existant est renvoyé, pas d'erreur). |
| **6 Événements** | `CASHFLOW_UPDATED` quand un run devient courant ; `CASHFLOW_RECALCULATION_REQUESTED` |

Règles de calcul (sources dans le contrat §9) :
- `REALIZED` : paiements non `REVERSED`, à `value_date`.
- Un paiement reçu mais pas encore alloué reste `REALIZED`.
- `EXPECTED`, `PROBABLE` et `AT_RISK` ne comptent jamais deux fois la même facture : le solde d'une facture est réparti entre lignes, et la somme des `amount_minor` par facture ne dépasse pas son `outstanding_minor`. **[PROPOSÉ]** : contrôle applicatif à l'écriture du run.
- La part contestée d'une facture en litige va en `AT_RISK`.

---

## 9 bis. Import Batch (historique) [N14 verrouillé, détails à spécifier]

| | Règle |
|---|---|
| **1 Créer** | Par un `ADMIN` ou un `OWNER` : téléversement d'un fichier (CSV ou XLSX) → lot `UPLOADED`. Un même fichier (`file_hash`) n'est pas importé deux fois. Organisation `ACTIVE`. |
| **2 Modifier** | Avant `COMMITTED` : lignes de staging (`import_rows`) et `release_mode` / `release_max_per_day`. À partir de `COMMITTED` : rien. |
| **3 Immuable** | Un lot `COMMITTED` ou au-delà ne s'annule ni ne se supprime. Les corrections passent par les mécanismes normaux (reversal, `VOID`, nouvelle saisie). |
| **4 Transitions** | Voir tableau ci-dessous. |
| **5 Erreurs** | `IMPORT_FILE_ALREADY_IMPORTED` · `IMPORT_VALIDATION_FAILED` · `IMPORT_BATCH_NOT_READY` · `IMPORT_APPROVAL_REQUIRED` · `IMPORT_BATCH_COMMITTED` (modification ou annulation d'un lot engagé) · `IMPORT_NORMALIZATION_FAILED` · `IMPORT_RELEASE_MODE_INVALID` · `INSUFFICIENT_ROLE` |
| **6 Événements** | `IMPORT_BATCH_UPLOADED`, `_READY`, `_APPROVED`, `_COMMITTED`, `_NORMALIZED`, `_RELEASED`, `_FAILED`, `_CANCELLED` |

**Correspondance avec la séquence verrouillée**

| Séquence N14 | État du lot |
|---|---|
| IMPORT | `UPLOADED` |
| VALIDATION | `VALIDATING` → `READY` (ou `VALIDATION_FAILED`) |
| IMPORT_BATCH_READY | `READY` |
| ADMIN REVIEW / VALIDATION | `READY → APPROVED` (rôle `ADMIN` ou plus) |
| IMPORT_COMMITTED | `APPROVED → COMMITTED` (staging figé) |
| NORMALIZATION | `NORMALIZING` → `NORMALIZED` (création des entités par `ImportHistoricalInvoice` et use cases jumeaux) |
| ENGINE EVENTS | événements émis avec `import_batch_id` ; Risk, Priority, Cashflow recalculés par demandes regroupées |
| AUTOMATION ELIGIBILITY | `NORMALIZED → RELEASING` (automatique en mode `PACED`, sur commande en mode `HOLD`) |
| CONTROLLED EXECUTION | exécutions créées à l'étalement voulu ; `RELEASING → RELEASED` quand plus rien à libérer |

**Règles.**
- `5 000 factures importées ≠ 5 000 relances immédiates` : tant que le lot n'est pas au moins `RELEASING`, le répartiteur d'automatisations ne crée aucune exécution pour les événements portant son `import_batch_id`.
- La libération respecte les invariants habituels (revalidation avant chaque exécution, exceptions métier, niveau minimal 3 dès `OVERDUE`) et un plafond quotidien. Elle peut être mise en pause (`RELEASING ⇄ RELEASE_PAUSED`).
- Normalisation : par défaut V1, tout ou rien dans une transaction ; un échec laisse le lot en `FAILED` et **aucune** donnée créée. *(À spécifier : taille maximale, reprise par tranches au-delà.)*
- Toute facture importée porte `origin='IMPORTED'` et `import_batch_id`. `CreateInvoice` ne produit jamais un état autre que `DRAFT`.
- Écritures d'audit : engagement du lot, approbation, mise en pause et reprise de la libération (D3).

---

## 10. Catalogue d'événements (V1.1)

### 10.1 Quatre catégories (colonne `events.category`)

| Catégorie | Sens | Consommation |
|---|---|---|
| `MUTATION` | création ou mutation append-only d'un fait métier | diffusée à tous les abonnés |
| `TRANSITION` | changement d'état d'un agrégat | diffusée à tous les abonnés |
| `REQUEST` | demande de traitement adressée à un moteur | **un seul** destinataire ; regroupable (coalescing) |
| `RESULT` | résultat d'une projection ou d'un calcul | diffusée à tous les abonnés |

Règle C5 : un événement peut être une mutation, une transition, une demande ou un résultat. Seule la catégorie `TRANSITION` correspond à un changement d'état.

### 10.2 `aggregate_type`, `aggregate_id`, `aggregate_version`

- L'agrégat d'un événement est **l'agrégat racine dont la ligne est modifiée** par l'opération.
- `aggregate_version` = valeur de `version` de la racine **après** la modification, dans la transaction d'émission. Elle s'incrémente chaque fois que la ligne racine est modifiée, y compris ses colonnes de cache.
- `PAYMENT_ALLOCATED` et `PAYMENT_ALLOCATION_REVERSED` : agrégat `PAYMENT` (l'allocation modifie toujours `payments.allocated_minor`, donc `payments.version` avance). Il n'existe **pas** d'agrégat `PAYMENT_ALLOCATION` ; l'identifiant de l'allocation est dans le payload.
- La même transaction émet les événements de facture correspondants (`INVOICE_PARTIALLY_PAID`, `INVOICE_PAID`, `INVOICE_SETTLEMENT_REVERTED`) avec l'agrégat `INVOICE` et la `version` de la facture.
- Événements `REQUEST` : `aggregate_version` = NULL. Projections sans colonne `version` (`risk_profiles`, `priority_items`, `cashflow_runs`) : NULL.
- L'ordre n'est garanti qu'au sein d'un même `(aggregate_type, aggregate_id)`, par `aggregate_version` croissante. Aucun ordre n'est garanti entre agrégats : les handlers relisent l'état.
- Les événements émis pendant la normalisation d'un lot d'import portent `import_batch_id` ; les automatisations ne les consomment pas tant que le lot n'est pas au moins `RELEASING` (§9 bis).

### 10.3 Événements

Toutes les lignes portent en plus : `event_id`, `organization_id`, `occurred_at`, `category`, `correlation_id`, `causation_id`, `causation_depth`, `actor_type`, `actor_id`, `aggregate_type`, `aggregate_id`, `aggregate_version`. Payloads sans donnée personnelle (C9).

**MUTATION**
| Événements | Agrégat | Payload spécifique |
|---|---|---|
| `ORGANIZATION_CREATED`, `ORGANIZATION_UPDATED`, `ORG_SETTINGS_CHANGED` | organization | `changed_fields[]` |
| `CUSTOMER_CREATED`, `CUSTOMER_UPDATED` | customer | `changed_fields[]` |
| `CUSTOMER_CONTACT_ADDED`, `CUSTOMER_CONTACT_UPDATED` | customer | `contact_id`, `channel` |
| `USER_CREATED` | user | `user_id` |
| `MEMBER_ADDED`, `MEMBER_ROLE_CHANGED` | membership | `membership_id`, `role` |
| `INVOICE_CREATED` | invoice | `customer_id`, `total_minor`, `origin` |
| `INVOICE_DISPUTED` | invoice | `dispute_id`, `disputed_amount_minor?` |
| `PAYMENT_CREATED` | payment | `customer_id`, `amount_minor`, `currency`, `value_date` |
| `PAYMENT_ALLOCATED`, `PAYMENT_ALLOCATION_REVERSED` | payment | `allocation_id`, `invoice_id`, `amount_minor` |
| `PROMISE_CREATED` | promise | `invoice_id?`, `customer_id`, `promised_amount_minor`, `promised_date` |
| `COLLECTION_ACTION_PROPOSED` | collection_action | `invoice_id`, `type`, `level` |
| `COLLECTION_HOLD_PLACED` | hold | `scope`, `invoice_id?`, `customer_id?`, `automation_id?` |
| `APPROVAL_REQUESTED` | approval | `kind`, `target_type`, `target_id` |
| `NOTIFICATION_CREATED` | notification | `notification_id`, `channel`, `type` |
| `AUTOMATION_CREATED`, `AUTOMATION_VERSION_CREATED` | automation | `automation_id`, `version_no?` |
| `IMPORT_BATCH_UPLOADED` | import_batch | `batch_id`, `rows_total` |

**TRANSITION**
| Événements | Agrégat | Payload spécifique |
|---|---|---|
| `ORGANIZATION_SUSPENDED`, `_REACTIVATED`, `_CLOSED` | organization | `from_status`, `to_status` |
| `CUSTOMER_ARCHIVED`, `CUSTOMER_REACTIVATED`, `CUSTOMER_DEACTIVATED` | customer | `from_status`, `to_status` |
| `USER_STATUS_CHANGED` | user | `from_status`, `to_status` |
| `MEMBER_REMOVED` | membership | `membership_id` |
| `INVOICE_ISSUED` | invoice | `customer_id`, `total_minor`, `currency`, `due_date` |
| `INVOICE_DUE_SOON`, `INVOICE_DUE`, `INVOICE_OVERDUE` | invoice | `customer_id`, `outstanding_minor`, `due_date`, `collection_cycle` |
| `INVOICE_PARTIALLY_PAID`, `INVOICE_PAID` | invoice | `customer_id`, `paid_minor`, `outstanding_minor`, `settled_on?` |
| `INVOICE_SETTLEMENT_REVERTED` | invoice | `from_settlement`, `to_settlement`, `paid_minor` |
| `INVOICE_CANCELLED`, `INVOICE_VOIDED` | invoice | `customer_id`, `reason_code` |
| `INVOICE_DISPUTE_RESOLVED` | invoice | `dispute_id`, `outcome` |
| `PAYMENT_REVERSED` | payment | `reason_code`, `reversed_allocations_count` |
| `PROMISE_FULFILLED`, `PROMISE_BROKEN`, `PROMISE_CANCELLED` | promise | `invoice_id?`, `customer_id`, `resolved_amount_minor?` |
| `COLLECTION_ACTION_SCHEDULED`, `_EXECUTED`, `_FAILED`, `_CANCELLED`, `_SUPPRESSED` | collection_action | `invoice_id`, `type`, `level`, `suppression_code?` |
| `COLLECTION_HOLD_RELEASED` | hold | `scope`, `cause` (`RELEASED`, `EXPIRED`) |
| `APPROVAL_GRANTED`, `APPROVAL_REJECTED` | approval | `kind`, `target_type`, `target_id` |
| `AUTOMATION_ACTIVATED`, `_PAUSED`, `_DISABLED`, `_ARCHIVED` | automation | `automation_id`, `version_no` |
| `AUTOMATION_EXECUTION_STARTED`, `_COMPLETED`, `_FAILED`, `_CANCELLED` | automation_execution | `automation_id`, `version_no`, `subject_type`, `subject_id` |
| `NOTIFICATION_SENT`, `NOTIFICATION_FAILED` | notification | `notification_id`, `channel` |
| `SUBSCRIPTION_CHANGED` | subscription | `plan_code`, `status` |
| `IMPORT_BATCH_READY`, `_APPROVED`, `_COMMITTED`, `_NORMALIZED`, `_RELEASED`, `_FAILED`, `_CANCELLED` | import_batch | `batch_id`, `from_status`, `to_status` |

**REQUEST** (un seul destinataire ; regroupables)
| Événement | Destinataire | Payload spécifique |
|---|---|---|
| `RISK_RECALCULATION_REQUESTED` | Risk Engine | `customer_id`, `reason` |
| `PRIORITY_RECALCULATION_REQUESTED` | Priority Engine | `scope`, `reason`, `customer_id?`, `invoice_id?` |
| `CASHFLOW_RECALCULATION_REQUESTED` | Cashflow Engine | `horizon_days?`, `scenario?`, `reason` |

**RESULT**
| Événement | Agrégat | Payload spécifique |
|---|---|---|
| `RISK_CHANGED` | customer | `from_level`, `to_level`, `score` |
| `PRIORITY_CHANGED` | invoice | `from_level`, `to_level`, `rank_score` |
| `CASHFLOW_UPDATED` | cashflow_run | `run_id`, `horizon_days`, `scenario` |

Événements temporels du Scheduler (`INVOICE_DUE_SOON`, `_DUE`, `_OVERDUE`) : émis une seule fois par transition gardée (C3).
Les événements `REQUEST` sont idempotents et regroupables : plusieurs demandes pour la même cible dans un court intervalle produisent un seul calcul.

---

## 11. État des décisions (V1.2)

Toutes les décisions de conception sont fermées. Restent des points à **spécifier**.

### Décisions verrouillées

| # | Décision |
|---|---|
| D1 | Litige total : suspension. Litige partiel : recouvrement de la part non contestée (`collectible_minor`), suspension seulement si `collectible_minor = 0` |
| D2 | `UPDATE_PRIORITY` supprimé ; une automatisation émet `PRIORITY_RECALCULATION_REQUESTED` ; seul le Priority Engine modifie la projection |
| D3 | Audit : commandes, configuration, droits, holds, approbations, actions sensibles ; transitions temporelles du Scheduler dans `*_history` + `events` seulement |
| D4 | Niveaux 1 à 5 |
| D5 | Pas de `MANAGER_ALERT` comme type d'action ; c'est une notification |
| D6 | Archivage interdit tant qu'il existe une facture ouverte ; une facture rouverte ensuite reste non recouvrable, alerte aux `ADMIN`, jamais de réactivation automatique du client |
| D7, D8 | PII / anonymisation, rétention |
| D9 | Deux chemins de création (normal → `DRAFT`, import historique → reconstruction contrôlée) |
| N1–N5, N8–N10 | Validés (voir ci-dessus) |
| N6 | `FULFILLED` reste terminal après un reversal ; le reversal produit ses propres événements et ses effets sur le risque et le cashflow |
| N7 | Dès `OVERDUE`, niveau minimal 3 ; aucune règle ne produit L1/L2 sur une facture en retard |
| N11 | Modifier le montant ou la date d'une promesse = annulation + nouvelle promesse |
| N12 | `invoices.collection_cycle` stocké |
| N13 | Automatisations modèles créées en `DRAFT` ; aucune exécution tant qu'elles ne sont pas activées et que leurs préconditions ne sont pas satisfaites |
| N14 | Import par lots (§9 bis) |

### À spécifier (ne change pas le schéma)

1. **Import** : formats et validations par entité ; taille maximale d'un lot et reprise par tranches ; politique d'étalement de la libération ; rétention du staging (`import_rows.raw` contient des données personnelles).
2. **Stratégie de recouvrement par défaut** : seuils des niveaux 1 à 5, canaux, gabarits ; contenus de l'automatisation modèle.
3. **Préconditions d'activation d'une automatisation** (N13) : liste détaillée.
4. **Niveaux 3 à 5 avant échéance** : proposition, interdits sauf action manuelle motivée. À confirmer dans la passe Collection Engine.
5. **Catalogue des types de notification.**

### Prochaine passe

State Machines → Rule Engine → Collection Engine → Automation Engine → Risk / Priority → Cashflow → vérification PostgreSQL/Django. Les modèles Django ne commencent qu'après.
