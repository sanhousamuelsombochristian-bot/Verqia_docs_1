# VERQIA — Domain V1 · Tranche 1 : Facture / Échéance / Paiement

Statut : **GELÉ le 2026-09-21** (empreinte `architecture_registry/domain_freeze.json`, 39 fichiers, 0 amendement). Direction validée (V1 à V8, V7 définitif) ; amendements B3 et B4 appliqués ; écarts DV1-1 et DV1-2 résolus ; code, référence indépendante, tests, coureur et porte de fermeture vérifiés. Toute modification passe par le journal `AMENDMENTS` de `domain_freeze.py`.
Méthode : proposition, décisions, états, transitions, invariants, cas nominaux, contre-exemples, cas limites, correspondance avec la référence exécutable, tests, validation, gel. Le code ne commence qu'après la validation de ce document.

Sources gelées relues pour cette tranche (aucune n'est rouverte) : State Machines V1 §3 à §6 et §16 ; Invariants V1.2 §3 à §5 et §10 ; Data Contract V1.3 §3, §4, §14 (T1 à T15) ; Engine Contracts V1.1 EC-05, EC-06 ; Architecture technique V1 (TD2, TD23, TD55, TD58, AR-01 à AR-03) ; Application Contract V1 (P8) et les 12 `UseCaseSpec` de `invoices` et `payments` ; contrats générés (`commands.py`, `events.py`, `kernel/errors.py`) ; `reference_model/`.

---

## 0. Périmètre et frontière

**Dans la tranche.** Les agrégats `Invoice` (corps, cycle de vie, règlement dérivé, cycle de recouvrement, litige), `Payment` (enregistrement, statut dérivé) et le registre d'allocations (`payment_allocations`), avec les 12 cas d'usage gelés qui les écrivent, plus la fonction d'échéance et les **faits financiers dérivés** que les tranches suivantes consomment.

| Cas d'usage gelé | Écrit (états du registre) | Décision Domain |
|---|---|---|
| `invoices.CreateInvoice` | `invoices.body` | `decide_create_invoice` |
| `invoices.IssueInvoice` | `invoices.lifecycle` | `decide_issue_invoice` |
| `invoices.CancelInvoice` | `invoices.lifecycle` | `decide_cancel_invoice` |
| `invoices.VoidInvoice` | `invoices.lifecycle` | `decide_void_invoice` |
| `invoices.InvoiceLifecycleScan` | `invoices.lifecycle` | `decide_lifecycle_scan` |
| `invoices.OpenInvoiceDispute` / `ResolveInvoiceDispute` | `invoices.dispute` | `decide_open_dispute` / `decide_resolve_dispute` |
| `invoices.ApplySettlement` (service C12) | `invoices.settlement`, `invoices.collection_cycle` | `decide_apply_settlement` |
| `payments.CreatePayment` | `payments.record` | `decide_create_payment` |
| `payments.AllocatePayment` | `payments.allocations`, `payments.allocated` (+ appel C12) | `decide_allocate_payment` |
| `payments.ReverseAllocation` | idem | `decide_reverse_allocation` |
| `payments.ReversePayment` | idem | `decide_reverse_payment` |

**Hors tranche** (tranches suivantes, dans l'ordre demandé) : Risque, Priorité, Action, Réconciliation, Prévision. Elles **consomment** les faits de la §1.4 ; aucune ne recalcule `outstanding`, retard, montant recouvrable ni règlement. Hors tranche aussi : `ImportHistoricalInvoice` (imports), promesses.

**Le Domain ne « fait » rien, il décide.** Interdits dans le Domain : Django, PostgreSQL, Redis, HTTP, e-mail, fournisseur externe, planificateur, horloge système, lecture ou écriture externe, mutation d'état. Vérifié par AR-01 (imports), AR-02 (aucune lecture d'horloge), et par les tests de pureté de la §10.

---

## 1. Proposition Domain

### 1.1 Frontière (inchangée)

```
State + Command + as_of  ──►  Domain.decide()  ──►  Decision   (ou DomainError du catalogue)
```

`Decision` porte : `writes` (un `StateWrite` par état du registre touché), `events`, `audit`, `result`, `outcome`. Le Domain ne connaît ni acteur, ni rôle, ni verrou, ni transaction, ni clé d'idempotence, ni identifiant d'événement : l'Application les ajoute (P5, P10).

Deux sortes de refus, jamais confondues :
- **`DomainError(code)`** : règle métier ou état incompatible. Code du catalogue gelé (`kernel/errors.py`). Aucune écriture, aucun événement.
- **`PreconditionViolated`** : une hypothèse *structurelle* (P3) que l'Application devait garantir n'est pas tenue (montant ≤ 0, doublon de facture dans une même commande, instant naïf…). C'est un défaut de l'appelant, jamais une erreur de l'utilisateur ; l'Application le traduit en erreur interne.

### 1.2 Forme des entrées (état)

Objets immuables (`frozen`), construits par l'Application à partir de la lecture P7 :

| Objet | Contenu | Origine |
|---|---|---|
| `InvoiceState` | id, customer_id, number, currency, issue_date, due_date, total_minor, paid_minor, lifecycle, settlement, collection_cycle, issued_at, settled_on, cancelled_at, cancel_reason, state_changed_at, version, origin, `lines`, `open_dispute` (ou rien) | `invoices` |
| `InvoiceLine` | position, description, quantity_e4, unit_price_minor, line_total_minor | `invoices` |
| `DisputeState` | id, status, reason, disputed_amount_minor ou rien (litige total), opened_at, resolved_at, resolution_note, version | `invoices` |
| `PaymentState` | id, customer_id, currency, reference, method, amount_minor, allocated_minor, received_at, value_date, status, version, `ledger` (lignes du paiement, pour les reversals ; `contributions` par facture, voir §1.3) | `payments` |
| `AllocationRow` | id, payment_id, invoice_id, customer_id, currency, amount_minor (signé), reverses_allocation_id, source, reason, allocated_at | `payments` |
| `OrgFacts` | status, timezone, currency, due_soon_days | `organizations.OrgStatus` (forme de niveau C) |
| `CustomerFacts` | status (`ACTIVE`, `INACTIVE`, `ARCHIVED`) | `customers.CustomerFacts` |
| `InvoiceFacts` (vue publique) | voir §1.4 | `invoices.InvoiceFacts` |
| `Taken` | faits d'unicité : `invoice_number_taken`, `payment_reference_taken` | lecture par clé naturelle (V2) |
| `new_ids` | identifiants frais, consommés dans l'ordre | `IdGenerator` (V4) |

`quantity_e4` : quantité en dix-millièmes (`numeric(18,4)` du contrat) ; tout le Domain est en **entiers**, comme la référence exécutable.

### 1.3 Composition C12 en Domain pur

`payments` ne peut pas importer le Domain d'`invoices` (I3/AR-03 : seul `contracts` est importable) et TD55 interdit à `payments` d'écrire le solde d'une facture par sa propre fonction. La composition est donc :

1. `payments.decide_allocate_payment` (et `reverse_*`) contrôle ses gardes avec `InvoiceFacts` (lecture de contrat) et rend, en plus de ses écritures et événements, une **demande de service** `ApplySettlement{invoice_id, delta_minor, contributions}` par facture touchée (une seule par facture, deltas cumulés). `contributions` est un **fait** issu du registre de `payments` : pour chaque paiement lié à la facture, `(payment_id, value_date, net_minor)` **après** l'opération ; `invoices` ne lit jamais ce registre (DR2).
2. L'Application exécute chaque demande **dans la même transaction** (C12) : elle lit la facture, appelle `invoices.decide_apply_settlement`, fusionne écritures et événements.
3. `decide_apply_settlement` est la **seule** fonction qui écrit `paid_minor`, `settlement_state`, `settled_on` et `collection_cycle` (TD55). Elle revalide T2 et T6 en défense en profondeur (`DB_INVARIANT_VIOLATED` si une violation atteignait ce point).

Conséquence sur le coureur (étape « Domain runner », pas ici) : `Decision` gagne un champ additif `calls`. Le contrat gelé (P8) n'est pas touché : il dit « une décision » sans en figer les champs.

### 1.4 Faits financiers dérivés (publics, source unique)

Les faits sont calculés par des fonctions pures (`invoices.domain.facts`, `payments.domain.facts`) et **livrés comme données** : `invoice_facts(...)` rend une `InvoiceFacts` et `payment_facts(...)` une `PaymentFacts` (formes de niveau C : `verqia/invoices/contracts/facts.py`, `verqia/payments/contracts/facts.py`). Risque, Priorité, Action, Réconciliation et Prévision **reçoivent** ces valeurs par la requête de contrat ; elles n'importent pas le Domain d'`invoices` (DR2) et ne recalculent rien. Un test statique (R-D5) interdit `total − paid` et la comparaison d'échéance hors du module des faits.

| Fait | Définition |
|---|---|
| `outstanding` | `total_minor − paid_minor` |
| `is_open` | `lifecycle ∈ {ISSUED, DUE_SOON, DUE, OVERDUE}` **et** `settlement ≠ PAID` |
| `is_payable` | `lifecycle ∈ {ISSUED, DUE_SOON, DUE, OVERDUE}` |
| `disputed_part` | litige `OPEN` sans montant : `outstanding` ; avec montant : `min(montant, outstanding)` ; sinon 0 |
| `collectible` (D1 verrouillé) | sans litige : `outstanding` ; litige total : 0 ; sinon `max(outstanding − montant, 0)` |
| `due_position(due, today, due_soon_days)` | `OVERDUE` si `today > due` ; `DUE` si `today = due` ; `DUE_SOON` si `due − due_soon_days ≤ today < due` ; sinon `NOT_YET` |
| `days_late` | `max(0, today − due)` |
| `days_to_due` | `max(0, due − today)` |
| `is_late` | `today > due` (fonction de dates, pas de `lifecycle`) |
| `settlement_delay_days` | `settled_on − due_date` si `PAID`, sinon rien (peut être négatif) |
| `payment_available` | 0 si `REVERSED`, sinon `amount_minor − allocated_minor` |
| `today` | `local_date(as_of, org.timezone)` (K20, jamais le fuseau du serveur) |

---

## 2. Décisions (DD1 à DD24)

Préfixe `DD` (décision Domain) pour ne pas les confondre avec les D1 à D9 des Invariants. Chaque décision applique un texte gelé ; les rares choix nouveaux sont marqués **[NOUVEAU]** et repris en §11.

| # | Décision | Source gelée |
|---|---|---|
| DD1 | La décision est `decide(state, command, as_of)`, pure et déterministe. Refus = `DomainError` du catalogue, jamais un état partiel. Hypothèses structurelles violées = `PreconditionViolated`. | P8, DR1 |
| DD2 | Le temps est `as_of`, tz-aware. « Aujourd'hui » = `local_date(as_of, org.timezone)`. Toute colonne temporelle écrite (`issued_at`, `state_changed_at`, `cancelled_at`, `opened_at`, `resolved_at`, `allocated_at`) vaut `as_of`. Aucune lecture d'horloge. Un instant naïf est refusé. | TD23, C10, K20 |
| DD3 | **[NOUVEAU]** Le Domain ne génère aucun identifiant. Les entités créées reçoivent `new_ids[0..n]` ; le nombre requis est une fonction pure `ids_needed(state, command)`. | TD22, contrat §0 (V4) |
| DD4 | Argent = entiers en unité mineure, plafond `bigint` (2⁶³−1) ; toute valeur au-delà est une `PreconditionViolated`. Aucun flottant. Total de ligne = `(quantity_e4 × prix + 5000) // 10000` (demi vers le haut, valeurs ≥ 0). | Contrat §0 |
| DD5 | **Retard = fonction de dates.** `lifecycle` est la *projection persistée* de `due_position`, avec le délai du balayage. Les moteurs lisent `due_position`, `days_late`, `is_late`, pas `lifecycle`. | Invariants §3.1 ; référence (`overdue = due < as_of`) |
| DD6 | **Position = la garde vraie la plus avancée.** Les gardes de `DUE_SOON`, `DUE`, `OVERDUE` se recouvrent ; le résultat est unique. `due_soon_days = 0` : `DUE_SOON` est inatteignable (`ISSUED → DUE` direct, sans événement `DUE_SOON`). | SM §3 (sauts autorisés) |
| DD7 | Le cycle de vie est **monotone** (`ISSUED < DUE_SOON < DUE < OVERDUE`) : la position n'est appliquée que si elle est strictement en avant de l'état courant. Une horloge en retard donne `SKIPPED`, jamais un recul. | SM §3 |
| DD8 | Les tables de transitions sont **la** source (T14 est générée depuis elles) : 12 couples pour le cycle de vie, 9 pour le paiement, 2 pour le litige. Toute décision qui change un état passe par `transition(table, ancien, nouveau)`. | SM §0, T14 |
| DD9 | Le règlement (`paid_minor`, `settlement_state`, `settled_on`) et `payments.status` sont **dérivés** : ils ne s'écrivent que par `derive_*` calculé sur les nouvelles sommes, jamais champ par champ. | SM §0, T4, T5 |
| DD10 | Le registre d'allocations est **append-only**. Le solde d'une facture et l'`allocated_minor` d'un paiement sont des sommes nettes. Un reversal est une ligne négative liée à son origine. `reversible(origine) = origine.montant + Σ reversals liés` pour une ligne positive, 0 pour une ligne négative. | T1 à T3, T8 |
| DD11 | **[V7 validé, précisé le 2026-09-21]** `settled_on` = `value_date` du paiement qui **réalise** le règlement, au sens **chronologique** : la date de valeur la plus tardive parmi les paiements dont la contribution nette à la facture est positive, quand la facture est soldée. Le résultat **ne dépend pas de l'ordre d'application** des allocations ; il est effacé à tout retour en arrière et recalculé au règlement suivant. Les paiements contributeurs sont fournis à `apply_settlement` (§1.3). | Contrat §3.1 (« date réelle de règlement, pas la date de saisie ») |
| DD12 | `collection_cycle` augmente de 1 **exactement** : (a) à l'entrée en `OVERDUE` par transition ; (b) quand un règlement `PAID → non payé` survient alors que le cycle de vie est **déjà** `OVERDUE`. Jamais les deux dans une décision. Jamais décrémenté. | Invariants §3.1 bis |
| DD13 | **Rattrapage à l'émission** : `DRAFT → ISSUED`, puis **un seul saut** vers la position du jour : une transition, un événement, une ligne d'historique. Pas de chaîne `ISSUED → DUE_SOON → DUE → OVERDUE`. | S3, SM §3 |
| DD14 | **Recalcul après annulation de règlement** : quand `PAID → non payé`, la position du jour est appliquée en avant seulement, dans la même décision (V1). | Contrat §3.1, SM §3 |
| DD15 | **[V5 validé avec contrainte]** Une décision écrit **au plus une fois** chaque état du registre par agrégat. **Le Domain ne calcule ni n'écrit aucune version** : `EventOut.aggregate_version` reste vide en sortie du Domain, et l'Application attribue la version réellement persistée (C3, C4) au moment d'appliquer la décision. Les événements d'un même agrégat sortent dans l'ordre causal, que l'Application conserve ; ses versions sont cohérentes avec la transaction. Le Domain n'est pas responsable de la concurrence. | §10.2, C4 |
| DD16 | **Tout ou rien** pour les commandes à plusieurs lignes. Ordre des contrôles fixé (précédence des erreurs, §7) ; ordre des événements canonique : événements du paiement dans l'ordre des lignes, puis événements de facture par `invoice_id` croissant. | EC5 (ordre des verrous) |
| DD17 | Une facture touchée plusieurs fois dans une même commande (plusieurs allocations à une facture lors d'un `ReversePayment`) produit **une** transition de règlement, du règlement initial au règlement final, donc un seul événement de facture. | SM §4 |
| DD18 | Les rôles, l'authentification, l'existence (`NOT_FOUND`), l'idempotence et les verrous ne sont pas du Domain. Le Domain suppose l'appelant autorisé. | P4, P5 |
| DD19 | Les faits d'unicité (`number`, `reference`) sont des **entrées** (`Taken`) : le Domain ne peut pas les deviner, la contrainte SQL reste le filet. | V2 |
| DD20 | `cancel_reason := reason_code` (les commandes ne portent que le code) ; la référence d'un paiement en espèces est `CASH-<payment_id>` (déterministe). | Contrat §3.1, §4.1 |
| DD21 | Le Domain expose `check_invoice`, `check_payment`, `check_allocations` (les invariants de la §5 comme prédicats). Ils servent aux tests, aux propriétés et, plus tard, à l'import (`NormalizeImportBatch`). | Invariants §9 bis |
| DD22 | **Garde d'organisation active** (`ORG_NOT_ACTIVE`) là où le texte gelé l'exige : `IssueInvoice` (SM §3), `AllocatePayment`, `ReverseAllocation`, `ReversePayment` (EC-05). Ailleurs, non exigée, donc non ajoutée. | SM §3, EC-05 |
| DD23 | Un reversal reste possible quel que soit l'état de la facture et du client (cas D6 : un client `ARCHIVED` peut voir sa facture rouverte). Une allocation ne contrôle pas le statut du client, seulement l'égalité des clients. | Invariants §5, SM §2 |
| DD24 | L'audit est produit pour les commandes d'utilisateur (`audit = REQUIRED` : 10 cas d'usage), pas pour `InvoiceLifecycleScan` ni `ApplySettlement` (C13). L'historique d'état (`invoice_state_history`) est une partie de la valeur de l'écriture (dimension, ancien, nouveau, motif) ; acteur et `event_id` sont ajoutés par l'Application. | C13, contrat §3.3 |

---

## 3. États autorisés

### 3.1 Cycle de vie de la facture

`DRAFT`, `ISSUED`, `DUE_SOON`, `DUE`, `OVERDUE`, `CANCELLED` (terminal), `VOID` (terminal).

| État | `issued_at` | `cancelled_at`, `cancel_reason` | `total` | `paid` | Corps (lignes, dates, client) |
|---|---|---|---|---|---|
| `DRAFT` | vide | vides | ≥ 0 | 0 | modifiable **[V6]** |
| `ISSUED`, `DUE_SOON`, `DUE`, `OVERDUE` | renseigné | vides | > 0 | 0 ≤ paid ≤ total | **immuable** (T7, T13) |
| `CANCELLED` | vide | renseignés | ≥ 0 | 0 | immuable |
| `VOID` | renseigné | renseignés | > 0 | 0 | immuable |

### 3.2 Règlement (dérivé)

| `paid` | `settlement` | `settled_on` |
|---|---|---|
| 0 | `UNPAID` | vide |
| 0 < paid < total | `PARTIALLY_PAID` | vide |
| paid = total > 0 | `PAID` | renseigné |

Toujours `UNPAID` tant que le cycle de vie est `DRAFT`, `CANCELLED` ou `VOID`.

### 3.3 Litige

`OPEN` → `RESOLVED_VALID` ou `RESOLVED_REJECTED` (terminaux). Un seul `OPEN` par facture. `resolved_at` renseigné si et seulement si le statut n'est pas `OPEN`.

### 3.4 Paiement

`RECEIVED`, `PARTIALLY_ALLOCATED`, `ALLOCATED`, `REVERSED` (terminal). Hors `REVERSED` : `RECEIVED` si `allocated = 0`, `PARTIALLY_ALLOCATED` si `0 < allocated < amount`, `ALLOCATED` si `allocated = amount`. `REVERSED` implique `allocated = 0`.

### 3.5 Ligne d'allocation

Positive (allocation) : `reverses_allocation_id` vide, `source ∈ {MANUAL, AUTO_MATCH}`. Négative (reversal) : `reverses_allocation_id` renseigné, `source = REVERSAL`, motif renseigné. Jamais nulle.

---

## 4. Transitions

### 4.1 Tables (source unique, DD8)

**Cycle de vie de la facture (12 couples).**

| De | Vers | Décision | Garde | Événement |
|---|---|---|---|---|
| `DRAFT` | `ISSUED` | `IssueInvoice` | §7.2 | `INVOICE_ISSUED` |
| `DRAFT` | `CANCELLED` | `CancelInvoice` | — | `INVOICE_CANCELLED` |
| `ISSUED` | `DUE_SOON` | scan, rattrapage, recalcul | position `DUE_SOON`, règlement ≠ `PAID` | `INVOICE_DUE_SOON` |
| `ISSUED`, `DUE_SOON` | `DUE` | idem | position `DUE` | `INVOICE_DUE` |
| `ISSUED`, `DUE_SOON`, `DUE` | `OVERDUE` | idem | position `OVERDUE` ; `cycle + 1` | `INVOICE_OVERDUE` |
| `ISSUED`, `DUE_SOON`, `DUE`, `OVERDUE` | `VOID` | `VoidInvoice` | `paid = 0`, aucun litige `OPEN` | `INVOICE_VOIDED` |

**Paiement (9 couples).** `RECEIVED → PARTIALLY_ALLOCATED`, `RECEIVED → ALLOCATED`, `PARTIALLY_ALLOCATED → ALLOCATED`, `ALLOCATED → PARTIALLY_ALLOCATED`, `ALLOCATED → RECEIVED`, `PARTIALLY_ALLOCATED → RECEIVED`, `RECEIVED`, `PARTIALLY_ALLOCATED` et `ALLOCATED → REVERSED`. Les couples sont des **changements** : `PARTIALLY_ALLOCATED → PARTIALLY_ALLOCATED` (montant modifié) n'est pas une transition.

**Litige (2 couples).** `OPEN → RESOLVED_VALID`, `OPEN → RESOLVED_REJECTED`. La création (`→ OPEN`) est un INSERT.

**Règlement (dérivé).** `UNPAID → PARTIALLY_PAID` (`INVOICE_PARTIALLY_PAID`) ; `UNPAID`, `PARTIALLY_PAID → PAID` (`INVOICE_PAID`) ; `PAID → PARTIALLY_PAID`, `PAID → UNPAID`, `PARTIALLY_PAID → UNPAID` (`INVOICE_SETTLEMENT_REVERTED`) ; `PARTIALLY_PAID → PARTIALLY_PAID` (aucun événement de facture).

**Interdit** : `DRAFT → VOID`, `CANCELLED → *`, `VOID → *`, tout recul du cycle de vie, `ISSUED… → CANCELLED` (utiliser `VOID`), `ISSUED… → DRAFT`, `REVERSED → *`.

### 4.2 Effets de chaque décision

| Décision | Écritures | Événements (dans l'ordre) | `outcome` |
|---|---|---|---|
| `create_invoice` | `invoices.body` : facture `DRAFT` (lignes, total, dates, devise de l'organisation, `origin = NATIVE`) | `INVOICE_CREATED` | `OK` |
| `issue_invoice` | `invoices.lifecycle` : `ISSUED` (+ saut éventuel), `issued_at`, `state_changed_at`, `collection_cycle` (+1 si `OVERDUE`), historique | `INVOICE_ISSUED`, puis au plus un de `DUE_SOON`, `DUE`, `OVERDUE` | `OK` |
| `cancel_invoice` | `invoices.lifecycle` : `CANCELLED`, `cancelled_at`, `cancel_reason` | `INVOICE_CANCELLED` | `OK` |
| `void_invoice` | `invoices.lifecycle` : `VOID`, `cancelled_at`, `cancel_reason` | `INVOICE_VOIDED` | `OK` |
| `lifecycle_scan` | `invoices.lifecycle` : position du jour si en avant ; `collection_cycle` (+1 si `OVERDUE`) | l'événement de la transition | `OK` ou `SKIPPED` |
| `open_dispute` | `invoices.dispute` : litige `OPEN` | `INVOICE_DISPUTED` | `OK` |
| `resolve_dispute` | `invoices.dispute` : issue, `resolved_at`, note | `INVOICE_DISPUTE_RESOLVED` | `OK` |
| `apply_settlement` | `invoices.settlement` (paid, settlement, settled_on), `invoices.collection_cycle` ; si `PAID → non payé` : recalcul avant (V1, `invoices.lifecycle`) | événement de règlement (§4.1), puis événement temporel éventuel | — |
| `create_payment` | `payments.record` : paiement `RECEIVED` | `PAYMENT_CREATED` | `OK` |
| `allocate_payment` | `payments.allocations` (lignes positives), `payments.allocated` (cache, statut), demandes `ApplySettlement` | `PAYMENT_ALLOCATED` par ligne | `OK` |
| `reverse_allocation` | ligne négative, `payments.allocated`, une demande | `PAYMENT_ALLOCATION_REVERSED` | `OK` |
| `reverse_payment` | une ligne négative par allocation active, `payments.allocated = 0`, statut `REVERSED`, `payment_reversals`, demandes groupées par facture | `PAYMENT_ALLOCATION_REVERSED` par allocation, puis `PAYMENT_REVERSED(reason_code, count)` | `OK` |

Pour les trois décisions de `payments`, les événements de facture (`INVOICE_*`) ne sont **pas** produits par elles mais par les sous-décisions `apply_settlement`, fusionnées à la suite des événements du paiement (§1.3) ; les `emits` de chaque cas d'usage restent donc ceux du registre.

Charges utiles d'événements : celles des classes gelées de `contracts/events.py`. Précisions : `collection_cycle` d'un événement temporel = valeur **après** la transition ; `PAYMENT_ALLOCATION_REVERSED` porte l'identifiant de la **ligne de reversal** et le montant reversé en valeur **positive** ; `INVOICE_SETTLEMENT_REVERTED` ne porte pas `customer_id` (contrat gelé).

---

## 5. Invariants

Trois natures : **[E]** prédicat d'état (vrai avant et après toute décision) ; **[T]** propriété de transition (entre l'état avant et après) ; **[X]** propriété inter-agrégats sur un ensemble de décisions. Chacun devient une ligne du registre de fermeture (§10.4) avec un test et une mutation.

### 5.1 Facture

| # | Invariant | Nature | Source |
|---|---|---|---|
| IF1 | `0 ≤ paid ≤ total` | E | CK |
| IF2 | règlement = fonction de (`paid`, `total`) : trois branches exclusives | E | CK, T4 |
| IF3 | `settled_on` renseigné si et seulement si `PAID` | E | CK |
| IF4 | `DRAFT`, `CANCELLED`, `VOID` implique `paid = 0` et règlement `UNPAID` | E | CK, T6 |
| IF5 | `ISSUED…OVERDUE` implique `total > 0` | E | CK |
| IF6 | `issued_at` renseigné si et seulement si l'état n'est ni `DRAFT` ni `CANCELLED` | E | contrat §3.1 |
| IF7 | `cancelled_at` et `cancel_reason` renseignés si et seulement si `CANCELLED` ou `VOID` | E | contrat §3.1 |
| IF8 | `due_date ≥ issue_date` | E | CK |
| IF9 | `Σ line_total = total` (à l'émission, puis immuable) et `line_total = arrondi(quantity × prix)` | E | T9, T7 |
| IF10 | après émission, `number`, `customer_id`, `currency`, `issue_date`, `due_date`, `total`, lignes sont inchangés par toute décision | T | T13, T7 |
| IF11 | le cycle de vie n'avance qu'en avant, et seulement par une table de transitions | T | SM §3, T14 |
| IF12 | `collection_cycle` ne décroît jamais ; il augmente de 0 ou 1 par décision | T | Invariants §3.1 bis |
| IF13 | tout changement d'état porte son événement ; le seul changement sans événement de facture est `PARTIALLY_PAID → PARTIALLY_PAID` | T | C5 |
| IF14 | un litige `OPEN` ne modifie ni le cycle de vie ni le règlement ; `VOID` est refusé tant qu'il existe | T | SM §5, T15 |
| IF15 | au plus un litige `OPEN` par facture | E | UQ partiel |
| IF16 | une facture `PAID` ne reçoit plus de transition temporelle | T | SM §3 (gel) |

### 5.2 Paiement et registre

| # | Invariant | Nature | Source |
|---|---|---|---|
| IP1 | `0 ≤ allocated ≤ amount` et `amount > 0` | E | T1, CK |
| IP2 | `allocated = Σ lignes du registre` ; `paid` d'une facture = `Σ lignes du registre` de cette facture | E | T4, T5 |
| IP3 | statut = fonction de (`allocated`, `amount`) hors `REVERSED` ; `REVERSED` implique `allocated = 0` | E | CK |
| IP4 | aucune ligne positive sur un paiement `REVERSED` | T | T10 |
| IP5 | `amount`, `currency`, `customer_id`, `reference`, `method`, `received_at`, `value_date` inchangés par toute décision | T | Invariants §4 |
| IA1 | ligne jamais nulle ; signe et `reverses_allocation_id` cohérents ; reversal avec motif | E | CK |
| IA2 | pour chaque origine, `Σ reversals liés ≥ −montant d'origine` | E | T3 |
| IA3 | aucune ligne positive nette sur une facture non payable | E | T6 |
| IA4 | même client et même devise entre paiement, ligne et facture | E | FK composites |
| IA5 | le registre est append-only : aucune décision ne réécrit ni ne supprime une ligne existante | T | T8 |
| IA6 | `Σ lignes d'une facture ∈ [0, total]` | E | T2 |

### 5.3 Inter-agrégats et décision

| # | Invariant | Nature |
|---|---|---|
| IX1 | **Conservation** : sur toute séquence de décisions valides, `Σ payments.allocated = Σ invoices.paid = Σ registre` | X |
| IX2 | **Aucune création d'argent** : `Σ paid` ne dépasse jamais `Σ amount` des paiements non `REVERSED` | X |
| IX3 | `ReversePayment` laisse `allocated = 0` et chaque facture touchée avec `paid` diminué exactement de ses allocations actives | X |
| IN1 | **Déterminisme** : mêmes entrées, même `Decision` | décision |
| IN2 | **Non-mutation** : l'état d'entrée n'est jamais modifié | décision |
| IN3 | **Indépendance de l'horloge système** : résultat identique quelle que soit l'heure de l'hôte | décision |
| IN4 | **Post-condition** : l'état résultant d'une décision satisfait `check_*` | décision |
| IN5 | tout code d'erreur levé appartient au catalogue ; tout événement émis appartient aux `emits` du cas d'usage ; toute écriture appartient à ses états déclarés | décision |

---

## 6. Cas nominaux

Fixture commune : organisation `O` (`EUR`, fuseau `UTC`, `ACTIVE`, `due_soon_days = 7`), client `C1` `ACTIVE`, facture `F1` (`total 11 501`, émise le 2026-09-01, échéance 2026-09-30). `as_of` à 09:00 UTC du jour indiqué.

| # | Décision et donnée | Résultat attendu |
|---|---|---|
| N1 | `create_invoice` : 2 lignes (20 000 × 5 000 → 10 000 ; 5 000 × 3 001 → 1 501 par demi vers le haut) | `DRAFT`, total 11 501, `UNPAID`, cycle 0 ; `INVOICE_CREATED(C1, 11 501, NATIVE)` ; audit |
| N2 | `issue_invoice` le 2026-09-10 | `ISSUED` ; un seul événement `INVOICE_ISSUED` ; 1 ligne d'historique |
| N3 | `issue_invoice` le 2026-09-25 (fenêtre) | `DUE_SOON` ; événements `ISSUED`, `DUE_SOON` ; 2 lignes d'historique |
| N4 | `issue_invoice` le 2026-10-05 (en retard) | `OVERDUE`, cycle 1 ; événements `ISSUED`, `OVERDUE(cycle 1)` ; pas de `DUE_SOON` ni `DUE` |
| N5 | `issue_invoice` le 2026-09-30 | `DUE` ; événements `ISSUED`, `DUE` |
| N6 | `lifecycle_scan` sur `ISSUED` le 2026-09-23 | `DUE_SOON`, `SKIPPED` la veille |
| N7 | scan sur `DUE_SOON` le 2026-09-30 puis sur `DUE` le 2026-10-01 | `DUE`, puis `OVERDUE` avec cycle 0 → 1 |
| N8 | scan sur `ISSUED` le 2026-10-15 (balayage manqué) | saut direct `OVERDUE`, un seul événement, cycle 1 |
| N9 | scan sur `OVERDUE`, `PAID`, `DRAFT`, `CANCELLED`, `VOID` | `SKIPPED`, aucune écriture |
| N10 | `create_payment` 5 000, `VIR-001`, valeur 2026-09-10 | `RECEIVED`, `allocated 0` ; `PAYMENT_CREATED` ; paiement en espèces : référence `CASH-<id>` |
| N11 | `allocate_payment` : paiement 5 000 → `F1` (dû 11 501) 5 000 | paiement `ALLOCATED` ; `F1` `PARTIALLY_PAID` (5 000 / 6 501) ; événements `PAYMENT_ALLOCATED`, `INVOICE_PARTIALLY_PAID` |
| N12 | `allocate_payment` : paiement 6 501 (valeur 2026-09-12) → `F1` (5 000 payés) | `F1` `PAID`, `settled_on = 2026-09-12`, cycle de vie inchangé (gel) ; `INVOICE_PAID` |
| N13 | `allocate_payment` : paiement 20 000 → `F1` 11 501 et `F2` (dû 9 000) 8 499 | paiement `ALLOCATED` ; `F1` `PAID`, `F2` `PARTIALLY_PAID` ; ordre : deux `PAYMENT_ALLOCATED`, puis `INVOICE_PAID(F1)`, `INVOICE_PARTIALLY_PAID(F2)` |
| N14 | `allocate_payment` : paiement 10 000, allocation 4 000 | `PARTIALLY_ALLOCATED`, disponible 6 000 |
| N15 | `reverse_allocation` de 2 000 sur `F1` `PARTIALLY_PAID` (5 000) | paid 3 000, encore `PARTIALLY_PAID` : `PAYMENT_ALLOCATION_REVERSED` seul, aucun événement de facture |
| N16 | `reverse_allocation` de 1 501 sur `F1` `PAID` (`OVERDUE`) | `PARTIALLY_PAID`, `settled_on` vide, cycle +1 ; `INVOICE_SETTLEMENT_REVERTED(PAID → PARTIALLY_PAID)` ; pas d'événement `OVERDUE` |
| N17 | `reverse_payment` de 8 000 (allocations 5 000 sur `F1`, 3 000 sur `F2`, sans autre paiement sur ces factures) | paiement `REVERSED`, `allocated 0`, 2 lignes négatives ; `PAYMENT_ALLOCATION_REVERSED` ×2, `PAYMENT_REVERSED(count 2)`, puis un `INVOICE_SETTLEMENT_REVERTED` par facture |
| N18 | `open_dispute` 4 000 sur `F1` (dû 6 501) | litige `OPEN`, `INVOICE_DISPUTED` ; `collectible = 2 501` ; sans montant : `collectible = 0` ; cycle de vie et règlement inchangés |
| N19 | `resolve_dispute` (rejeté) | `RESOLVED_REJECTED`, `INVOICE_DISPUTE_RESOLVED(outcome)` |
| N20 | `void_invoice` sur `F1` `ISSUED`, `paid 0`, sans litige | `VOID`, `cancelled_at = as_of`, `cancel_reason = reason_code` ; `INVOICE_VOIDED` |
| N21 | `cancel_invoice` sur un `DRAFT` | `CANCELLED` ; `INVOICE_CANCELLED` |
| N22 | `allocate` sur facture avec litige `OPEN` | accepté (« un paiement reçu est un fait ») |
| N23 | `allocate` puis `reverse_allocation` du même montant | facture et paiement retrouvent exactement leur état initial de sommes ; cycle inchangé (facture jamais `PAID`) |

---

## 7. Contre-exemples

Chaque ligne : refus **fermé** (aucune écriture, aucun événement, état d'entrée intact). Codes du catalogue gelé sauf mention **[absent]**.

### 7.1 Précédence des contrôles

`état` avant `contexte` (organisation, client) avant `données`. Première violation rencontrée, dans l'ordre :

| Décision | Ordre des contrôles |
|---|---|
| `create_invoice` | client `ARCHIVED` → `CUSTOMER_ARCHIVED` ; `INACTIVE` → `CUSTOMER_INACTIVE` ; `due < issue` → `INVOICE_DATES_INVALID` ; numéro pris → `INVOICE_NUMBER_TAKEN` |
| `issue_invoice` | pas `DRAFT` → `INVALID_TRANSITION` ; organisation → `ORG_NOT_ACTIVE` ; client (`ARCHIVED` puis `INACTIVE`) ; sans ligne → `INVOICE_EMPTY` ; `total ≤ 0` → `INVOICE_TOTAL_MUST_BE_POSITIVE` ; `due < issue` → `INVOICE_DATES_INVALID` ; `Σ lignes ≠ total` → `DB_INVARIANT_VIOLATED` |
| `cancel_invoice` | pas `DRAFT` → `INVALID_TRANSITION` |
| `void_invoice` | hors `ISSUED…OVERDUE` → `INVALID_TRANSITION` ; `paid > 0` → `INVOICE_HAS_PAYMENTS` ; litige `OPEN` → `INVOICE_HAS_OPEN_DISPUTE` **[absent, V3]** |
| `open_dispute` | non payable ou `PAID` → `DISPUTE_INVOICE_NOT_DISPUTABLE` **[absent]** ; déjà un `OPEN` → `DISPUTE_ALREADY_OPEN` **[absent]** ; motif vide → `DISPUTE_REASON_REQUIRED` **[absent]** ; montant > total → `DISPUTE_AMOUNT_EXCEEDS_TOTAL` **[absent]** |
| `resolve_dispute` | litige absent ou pas `OPEN` → `INVALID_TRANSITION` |
| `create_payment` | client `ARCHIVED` → `CUSTOMER_ARCHIVED` (un client `INACTIVE` est accepté) ; montant ≤ 0 → `PAYMENT_AMOUNT_INVALID` ; devise ≠ organisation → `PAYMENT_CURRENCY_MISMATCH` ; `value_date > today` ou `received_at > as_of` → `PAYMENT_DATE_IN_FUTURE` ; référence prise → `PAYMENT_DUPLICATE_REFERENCE` |
| `allocate_payment` | organisation → `ORG_NOT_ACTIVE` ; paiement `REVERSED` → `ALLOCATION_PAYMENT_REVERSED` ; puis **par ligne, dans l'ordre reçu** : facture non payable → `ALLOCATION_INVOICE_NOT_PAYABLE` ; client → `ALLOCATION_CUSTOMER_MISMATCH` ; devise → `ALLOCATION_CURRENCY_MISMATCH` ; montant > dû → `ALLOCATION_EXCEEDS_INVOICE_OUTSTANDING` ; enfin `Σ lignes > disponible` → `ALLOCATION_EXCEEDS_PAYMENT_AVAILABLE` |
| `reverse_allocation` | organisation ; motif vide → `REVERSAL_REASON_REQUIRED` ; montant > `reversible(origine)` (y compris origine négative, ou paiement déjà `REVERSED`) → `REVERSAL_EXCEEDS_ORIGINAL` |
| `reverse_payment` | organisation ; déjà `REVERSED` → `PAYMENT_ALREADY_REVERSED` ; motif vide → `PAYMENT_REVERSAL_REASON_REQUIRED` |

### 7.2 Cas de refus (à convertir en tests)

| # | Cas | Attendu |
|---|---|---|
| C1 | `issue_invoice` sur `ISSUED`, `CANCELLED`, `VOID` | `INVALID_TRANSITION` |
| C2 | `issue_invoice` sans ligne ; total 0 ; client `INACTIVE` ; client `ARCHIVED` ; organisation suspendue | `INVOICE_EMPTY` ; `INVOICE_TOTAL_MUST_BE_POSITIVE` ; `CUSTOMER_INACTIVE` ; `CUSTOMER_ARCHIVED` ; `ORG_NOT_ACTIVE` |
| C3 | `cancel_invoice` sur `ISSUED…OVERDUE`, `VOID` | `INVALID_TRANSITION` (pour annuler une émise : `VOID`) |
| C4 | `void_invoice` sur `DRAFT`, `CANCELLED`, `VOID` | `INVALID_TRANSITION` |
| C5 | `void_invoice` avec 1 minor payé, y compris facture `PAID` | `INVOICE_HAS_PAYMENTS` |
| C6 | `void_invoice` avec litige `OPEN` | refus (V3) |
| C7 | scan avec règlement `PAID` alors que l'échéance est dépassée | `SKIPPED`, cycle de vie gelé |
| C8 | `open_dispute` sur `DRAFT`, `CANCELLED`, `VOID`, `PAID` ; deuxième litige ; montant > total ; motif vide | codes de 7.1 |
| C9 | `allocate` sur `DRAFT`, `CANCELLED`, `VOID` | `ALLOCATION_INVOICE_NOT_PAYABLE` |
| C10 | `allocate` sur facture `PAID` (dû 0) | `ALLOCATION_EXCEEDS_INVOICE_OUTSTANDING` |
| C11 | `allocate` d'un client à la facture d'un autre client ; devise différente | `ALLOCATION_CUSTOMER_MISMATCH` ; `ALLOCATION_CURRENCY_MISMATCH` |
| C12 | `allocate` de disponible + 1 ; de dû + 1 | `ALLOCATION_EXCEEDS_PAYMENT_AVAILABLE` ; `ALLOCATION_EXCEEDS_INVOICE_OUTSTANDING` |
| C13 | `allocate` sur paiement `REVERSED` | `ALLOCATION_PAYMENT_REVERSED` (T10) |
| C14 | commande à 3 lignes dont la 3ᵉ invalide | refus total, aucune ligne appliquée |
| C15 | `reverse_allocation` de reliquat + 1 ; deuxième reversal complet ; reversal d'une ligne négative | `REVERSAL_EXCEEDS_ORIGINAL` |
| C16 | `reverse_allocation` sans motif ; `reverse_payment` sans motif | `REVERSAL_REASON_REQUIRED` ; `PAYMENT_REVERSAL_REASON_REQUIRED` |
| C17 | `reverse_payment` deux fois | `PAYMENT_ALREADY_REVERSED` |
| C18 | `create_payment` : montant 0 ; autre devise ; valeur demain (fuseau de l'organisation) ; `received_at` futur ; référence prise ; client `ARCHIVED` | codes de 7.1 |
| C19 | `resolve_dispute` sur litige déjà résolu | `INVALID_TRANSITION` |
| C20 | `apply_settlement` (défense) : delta positif sur facture non payable ; `paid` hors `[0, total]` | `DB_INVARIANT_VIOLATED` |
| C21 | instant `as_of` naïf ; montant hors `bigint` ; deux lignes pour la même facture ; montant ≤ 0 dans une ligne | `PreconditionViolated` |
| C22 | tout refus ci-dessus | l'état d'entrée est **identique** octet pour octet (IN2) |

---

## 8. Cas limites

| # | Cas | Attendu |
|---|---|---|
| L1 | `due_soon_days = 0` : veille de l'échéance, puis jour de l'échéance | reste `ISSUED`, puis `DUE` ; aucun `DUE_SOON` |
| L2 | `due_soon_days = 90`, facture émise à 30 jours de l'échéance | rattrapage immédiat en `DUE_SOON` |
| L3 | émission le jour de l'échéance (`due = issue = today`) | `ISSUED` puis `DUE` |
| L4 | fuseau `Pacific/Auckland`, `as_of = 2026-09-29T23:30Z` (jour local 09-30, échéance 09-30) | `DUE`, alors que la date UTC est le 09-29 |
| L5 | fuseau `America/Los_Angeles`, `as_of = 2026-10-01T05:00Z` (jour local 09-30) | encore `DUE`, pas `OVERDUE` |
| L6 | changement d'heure dans la fenêtre (cas d'or `R13`, `R14` du fuseau) | jour local identique pour tous les instants d'un même jour local |
| L7 | échéance 2028-02-29 : le 2028-03-01 | `OVERDUE` ; fenêtre `DUE_SOON` qui franchit février/mars |
| L8 | horloge en retard : facture `OVERDUE`, `today < due` | `SKIPPED` (DD7), jamais de recul |
| L9 | facture `PAID`, gelée en `ISSUED`, échéance dépassée, règlement annulé | recalcul en avant `ISSUED → OVERDUE` : `INVOICE_SETTLEMENT_REVERTED` puis `INVOICE_OVERDUE`, cycle **+1 une seule fois** (règle a, pas b) |
| L10 | facture `PAID` gelée `OVERDUE`, règlement annulé | cycle +1 (règle b), **aucun** événement `OVERDUE` (pas de transition) |
| L11 | `PARTIALLY_PAID → UNPAID` sur facture `OVERDUE` | cycle inchangé (la règle b exige `PAID →`) |
| L12 | facture soldée en retard : `settled_on > due_date` | `settlement_delay_days > 0`, cycle de vie `OVERDUE + PAID` |
| L13 | facture soldée avant échéance, gelée `DUE_SOON`, l'échéance passe | le scan ne la touche pas ; `is_late` devient vrai (fonction de dates) mais `is_open` reste faux : les moteurs combinent les deux |
| L14 | quantité 0,0001 × 4 999 puis 0,0001 × 5 000 | ligne 0 puis ligne 1 (demi vers le haut) |
| L15 | total à 2⁶³−1 ; somme de lignes qui dépasse | `PreconditionViolated` (pas de débordement silencieux) |
| L16 | montant égal au dû ; égal au disponible ; dû + 1 | accepté ; accepté ; refusé |
| L17 | litige de montant = total ; litige > dû après paiement partiel | accepté (T11 borne au total) ; `collectible = max(dû − montant, 0) = 0` |
| L18 | `reverse_payment` sans allocation active | `REVERSED`, `count 0`, aucune demande de règlement |
| L19 | `reverse_payment` : deux allocations sur la même facture | une seule demande (deltas cumulés), un seul `INVOICE_SETTLEMENT_REVERTED` (DD17) |
| L20 | `reverse_allocation` sur facture d'un client `ARCHIVED` | accepté (DD23, cas D6) |
| L21 | facture `PAID` avec litige `OPEN` préexistant | le litige reste `OPEN` ; `collectible = 0` |
| L22 | paiement dont `value_date` précède l'émission de la facture | l'allocation est acceptée (la règle Q4 de la Réconciliation ne concerne que la suspension) |
| L23 | **V7** : facture soldée par A (valeur J+5) et B (valeur J+2), allocations dans l'ordre A puis B, puis B puis A ; puis reversal du plus tardif et nouveau règlement | `settled_on = J+5` dans les deux ordres ; après reversal de A et règlement par C (valeur J+7) : `J+7` ; propriété testée sur toute permutation |
| L24 | paiement `CASH` | `reference = CASH-<payment_id>` |
| L25 | rejeu d'une même décision sur le même état | même `Decision` (IN1) |

---

## 9. Correspondance avec la référence exécutable

### 9.1 Ce que couvre `reference_model/`

`verqia_models.py` (Risque `risk-1.0`, Priorité `prio-1.0`, Prévision `cash-1.0`, Réconciliation RP23) et ses 35 tests **ne contiennent aucune règle de facture, d'allocation ni de règlement**. Ils *supposent* des faits financiers en entrée. Cette tranche n'a donc pas de référence de son propre domaine : c'est un constat, non un défaut, et il est traité en V8. **Depuis le 2026-09-21 (V8), `reference_model/finance_ref.py` couvre cette tranche** : stdlib seule, aucun import du Domain ni de `verqia_models`, oracle écrit à la main (31 tests), 18 cas de chronologie, 42 refus, cas d'or `golden_finance.json` ; les 35 tests existants sont inchangés.

### 9.2 Faits que le Domain doit produire à l'identique de ce que la référence consomme

| Référence | Entrée financière consommée | Fait du Domain | Test de correspondance |
|---|---|---|---|
| `unallocated_of(p)` | `amount − allocated` | `payment_available` (0 si `REVERSED`, que la référence filtre par statut) | égalité sur tout paiement non `REVERSED` |
| `payment_qualifies` (Q1 à Q4) | statut, non alloué, client, devise, facture ouverte, `value_date ≥ issue_date` | `status`, `payment_available`, `customer_id`, `currency`, `is_open`, `value_date`, `issue_date` | la référence reçoit les faits du Domain et rend la même qualification |
| `reserve_unallocated` | `outstanding`, `disputed = min(montant, outstanding)` | `outstanding`, `disputed_part` ; `coll = outstanding − disp` égale `collectible` | égalité, y compris litige total (`disputed_part = outstanding`) |
| `invoice_lines` (`overdue`, `dod`) | `due < as_of`, `(as_of − due).days` | `is_late`, `days_late` | égalité pour toute paire (`due`, `today`) |
| `prio_points` (`overdue`, `Dd`, `Dj`) | retard en jours, jours avant échéance | `is_late`, `days_late`, `days_to_due` | égalité |
| `local_date`, `barrier_lifted_at` | date locale d'un instant | `today` (K20) : fonction `local_date` déplacée dans `kernel` telle quelle | cas d'or de fuseau `R11` à `R14` |

Constat : `kernel` ne contient pas encore `local_date` (K20 la lui attribue). Elle est reprise de la référence, sans changement de comportement.

### 9.3 Correspondance avec les documents gelés

| Exigence gelée | Ce qui la couvre |
|---|---|
| T14 « couples générés depuis la table de transitions du Domain » | DD8 ; test d'égalité entre les tables et `STATE_MACHINES_V1.md` §3, §5, §6 |
| T1 à T6, T9, T10, T13 | IP1, IA2, IP2, IA3, IF9, IP4, IF10 |
| Catalogue d'événements §10.3 | charges utiles des classes gelées ; IN5 |
| Codes d'erreur §3 à §5 | §7 ; IN5 (25 codes présents au catalogue ; 4 codes de litige décidés mais absents, plus 1 à nommer pour T15 : V3) |

---

## 10. Tests Domain (à écrire après validation)

Tous sans base, sans réseau, sans horloge, sans Django. Voix : unittest, comme l'existant.

| Famille | Contenu | Ordre de grandeur |
|---|---|---|
| DT-A tables | 12 + 9 + 2 couples ; interdits de la §4.1 ; égalité avec les tables du document ; génération de T14 | 20 |
| DT-B échéance | `due_position` sur la grille (`due`, `today`, `due_soon_days ∈ {0, 1, 7, 90}`) ; fuseaux L4 à L7 ; monotonie | 25 |
| DT-C nominaux | N1 à N23 avec états, événements (type, charge, ordre ; aucune version : DD15), écritures, audit | 45 |
| DT-D refus | §7.1 (précédence) et C1 à C22, avec vérification d'intégrité de l'état d'entrée | 55 |
| DT-E limites | L1 à L25 | 30 |
| DT-F propriétés | générateur déterministe (graine fixe) de séquences valides et invalides sur N factures, M paiements ; un **interpréteur de test** applique décisions et demandes de service ; après chaque pas : `check_*`, IX1 à IX3, IF10 à IF13, IA5 | 12 propriétés, 2 000 séquences |
| DT-G pureté | imports interdits (AR-01) ; aucune lecture d'horloge (`datetime.now`, `today`, `time.time` remplacés par une levée) ; entrée gelée ; deux exécutions identiques ; instant naïf refusé | 10 |
| DT-H raccord | codes ⊂ catalogue ; événements ⊂ `emits` ; écritures ⊂ `domain` du `UseCaseSpec` ; charges utiles = classes gelées ; identifiants consommés = `ids_needed` | 12 |
| DT-R référence | §9.2 sur états produits par le Domain | 10 |

### 10.1 Mutations prévues (exécutables, comme la porte AP ; tout survivant est un échec)

`paid ≤ total` retiré ; `settled_on` pris sur `as_of` ; règle (b) du cycle supprimée ; cycle incrémenté deux fois ; recul du cycle de vie autorisé ; transition sans événement ; allocation à `VOID` acceptée ; `<` à la place de `≤` sur le disponible ; reversal au-delà de l'origine ; litige > total accepté ; retard lu sur `lifecycle` au lieu des dates ; date UTC à la place de la date locale ; gel `PAID` retiré ; recalcul après annulation retiré ; deux transitions au lieu d'un saut ; ordre des événements inversé ; un événement par allocation au lieu d'un par facture ; `settled_on` non effacé ; `REVERSED` accepte une allocation ; devise non contrôlée ; client non contrôlé ; arrondi vers le bas ; `DUE_SOON` atteint avec `due_soon_days = 0` ; `ReversePayment` oublie une allocation ; version non incrémentée. **≈ 25 mutations.**

### 10.2 Règles statiques

`R-D1` aucun import hors `kernel` et des `contracts` ; `R-D2` aucune horloge ; `R-D3` aucun flottant ; `R-D4` aucune écriture d'état hors `derive_*` et `transition` ; `R-D5` `total − paid` et comparaison d'échéance uniquement dans le module des faits.

### 10.3 Porte de fermeture

Comme pour AP : un registre `DOMAIN_INVARIANTS` (IF, IP, IA, IX, IN) où chaque entrée porte sa référence de test et sa mutation ; `DOMAIN_COUNT = PROVEN + UNTESTED` ; un invariant ajouté sans preuve fait échouer la porte. Le texte des invariants reste celui de la §5 une fois gelé.

---

## 11. Validation : écarts constatés et décisions du 2026-09-21

Ces points ont été découverts en confrontant les décisions aux 12 `UseCaseSpec` gelés. **Tous sont tranchés le 2026-09-21** (colonne « Décision »). Aucun ne touche PostgreSQL. **B3 ne modifie aucune règle métier** : il corrige des incohérences entre contrats déjà gelés.

| # | Constat | Pourquoi ce n'est pas un choix libre | Recommandation | Décision (2026-09-21) |
|---|---|---|---|---|
| **V1** | **Contradiction interne au gel.** Invariants §3.1, Data Contract §3.1 et State Machines §3/§16 (ligne 1) disent que le cycle de vie est **recalculé immédiatement**, dans la transaction, quand un règlement est annulé. Le registre gelé n'autorise que `invoices.settlement` et `invoices.collection_cycle` à `ApplySettlement` et aux trois cas d'usage de `payments`, et ne leur laisse émettre aucun événement temporel. State Machines §16 (ligne 3) dit « par événement ». | L'écriture `invoices.lifecycle` serait refusée par le coureur (`state_not_owned`). | Amendement **B3-a** : ajouter `invoices.lifecycle` et `INVOICE_DUE_SOON/DUE/OVERDUE` aux effets de `ApplySettlement` et des trois cas d'usage. Aucune nouvelle transaction, aucun nouveau cas d'usage, liste C12 fermée inchangée. Solution de repli : le balayage suivant recalcule ; la fonction pure est la même. | **B3-a validé et appliqué.** Le recalcul est immédiat, dans la transaction du reversal ; le balayage reste un filet de sécurité, jamais le mécanisme principal. |
| **V2** | **`reads` déclarés incomplets.** Les gardes gelées exigent des faits que sept cas d'usage ne déclarent pas : `IssueInvoice` (client, organisation, fuseau, `due_soon_days`), `InvoiceLifecycleScan` (fuseau, `due_soon_days`), `CreateInvoice` (devise, statut de l'organisation), `CreatePayment` (client, devise, fuseau), `AllocatePayment`, `ReverseAllocation`, `ReversePayment` (`InvoiceFacts`, organisation, fuseau). Les modules ont le droit de lire (`invoices` : `OrgStatus`, `CustomerFacts` ; `payments` : aussi `InvoiceFacts`) ; les cas d'usage ne le déclarent pas. `OrgSettings` n'a pas `invoices` comme consommateur. | Le coureur refuse tout appel non déclaré (`call_not_declared`). | Amendement **B3-b** : déclarer ces lectures. Donner à `OrgStatus` (forme de niveau C, donc sans changer son nom ni ses consommateurs) le contenu `{status, timezone, currency, due_soon_days}`. Côté coureur (hors contrat) : lecture par clé naturelle (`number`, `reference`) et lecture du registre d'un paiement. | **B3-b validé et appliqué** : huit cas d'usage déclarent leurs lectures ; `OrgStatus` porte `{status, timezone, currency, due_soon_days}` (niveau C). |
| **V3** | **Codes absents du catalogue gelé.** `DISPUTE_ALREADY_OPEN`, `DISPUTE_AMOUNT_EXCEEDS_TOTAL`, `DISPUTE_INVOICE_NOT_DISPUTABLE`, `DISPUTE_REASON_REQUIRED` sont décidés en Invariants §3.3 mais absents de `kernel/errors.py` (104 codes). Le refus de `VOID` avec litige `OPEN` (T15, validé S5) n'a aucun code. `ReversePayment` déclare `REVERSAL_REASON_REQUIRED` alors qu'Invariants §4 nomme `PAYMENT_REVERSAL_REASON_REQUIRED`. | Un code hors catalogue viole IN5 ; réutiliser un mauvais code trompe le client. | Amendement **B3-c** : ajouter les 4 codes déjà décidés, plus `INVOICE_HAS_OPEN_DISPUTE` (422) ; aligner la déclaration de `ReversePayment` sur Invariants §4. Alternative : `INVALID_TRANSITION` avec un détail pour `VOID`. | **B3-c validé et appliqué** : cinq codes ajoutés (109 au catalogue) ; cause racine corrigée : le générateur d'Annexe A ignorait la ligne `| Erreurs |` du tableau du litige. |
| **V4** | **Identifiants** (DD3). Les commandes gelées ne portent pas l'identifiant des lignes d'allocation ni du litige, et le Domain pur ne peut pas en produire. | Le contrat impose UUIDv7 généré côté application. | `new_ids` fourni par l'Application, nombre requis = fonction pure. Un champ additif du coureur, pas du contrat. | **Validé.** L'Application génère `invoice_id`, `payment_id`, `allocation_id`, l'identifiant du litige ; le Domain les reçoit (`new_ids`) et n'appelle jamais un générateur. |
| **V5** | **Version d'agrégat à événements multiples** (DD15). Plusieurs événements d'une même facture dans une transaction partagent la version après écriture ; §10.2 ne prévoit pas d'ex æquo. | Ordre par version croissante annoncé. | Une écriture, une version ; ordre par rang dans la décision (identifiants d'événements monotones). | **Validé avec contrainte** : le Domain ne fabrique pas la version ; l'Application l'attribue (DD15). |
| **V6** | **Aucun cas d'usage ne modifie un brouillon** (Invariants §3 « Modifier » : client, dates, lignes ; `notes`, `external_ref` après émission). Seul `CreateInvoice` écrit `invoices.body`. | Ajouter un cas d'usage est un amendement de registre. | Constater : en V1, corriger un brouillon = `CancelInvoice` puis `CreateInvoice`. Ne rien ajouter maintenant. | **Confirmé** : aucune mutation métier d'un brouillon en V1 ; aucun nouvel état `EDIT_DRAFT`, aucune nouvelle règle de concurrence. |
| **V7** | **Date de règlement** (DD11). `settled_on` est la date de valeur du paiement qui solde. Si deux paiements soldent une facture dans l'ordre inverse de leurs dates de valeur, la « date réelle » est la plus tardive, pas celle du dernier alloué. | Le texte gelé dit « le paiement soldant » ; la version littérale ne demande aucune lecture de plus. | Garder la lecture littérale et documenter la limite (L23). | **Validé et précisé** : la date de valeur du paiement qui réalise le règlement, indépendante de l'ordre d'application (DD11, L23), testée par propriété. |
| **V8** | **Pas de référence exécutable pour cette tranche** (§9.1). | Le Domain serait son propre juge. | Ajouter, sans toucher aux 35 tests existants, `reference_model/finance_ref.py` : trois fonctions naïves en entiers (règlement d'un registre, position d'échéance, disponibilité) et des cas d'or `F1…`. Les tests DT-R comparent le Domain à cette référence, écrite avant lui. | **Feu vert, réalisé** : `finance_ref.py`, indépendante et naïve, établie avant le Domain. |

### Séquence retenue

```text
contrats gelés → amendement B3 → finance_ref.py indépendante → cas d’or → Domain V1 → tests Domain + tests différentiels → validation → GEL
```

Règle maintenue : **aucun code du Domain V1 tant que B3 et `finance_ref.py` ne sont pas établis et vérifiés** (ils le sont : voir §12). Le Domain reste écrit **contre** la référence, jamais l'inverse : `reference(x) == domain(x)` est une vérification différentielle, pas un calque.

---

## 12. Gel

État au 2026-09-21 :

| Étape | État |
|---|---|
| Validation du document et des points V1 à V8 | **faite** |
| Amendement B3 (B3-a, B3-b, B3-c) | **appliqué et vérifié** : registre 0 erreur ; contrats 147 fichiers, 109 codes ; empreinte de gel de l'Application régénérée (3 amendements) ; porte AP 15/15, 40 mutations sur 40 tuées ; 230 tests du coureur ; matrice 215 tests, 732 jetons, 0 non couvert |
| Référence `finance_ref.py`, cas d'or `golden_finance.json` | **établie et vérifiée** : 31 tests, 35 tests existants inchangés |
| Code du Domain (`invoices.domain`, `payments.domain`, types de sortie du noyau) | **écrit** : 8 + 4 décisions pures, tables de transitions, faits, invariants comme prédicats (phases 1 et 2) |
| Tests DT-A à DT-R et tests différentiels contre `finance_ref.py` | **verts** : 79 tests, 11 s réelles avec 2 000 séquences aléatoires ; différentiel : 18 chronologies d'or, 400 aléatoires, 42 refus, faits |
| Porte de fermeture (35 invariants : IF 16, IP 5, IA 6, IX 3, IN 5 ; règles statiques R-D1 à R-D5) | **fermée** : `verify_domain.py --run --mutate` : 35 sur 35 prouvés, 39 mutations sur 39 tuées ; `DOMAIN_PROOFS_V1.md` généré |
| Arbitrage DV1-1 et DV1-2 : **B4** (B4-a, B4-b) | **fait et appliqué le 2026-09-21** : registre, contrats et gel régénérés, `KNOWN_WRITE_SCOPE_GAPS` vide |
| Domain runner (types de `kernel/decision.py`, `Decision.calls`, `new_ids`, lecture par clé, application des `RowChange`, versions par l'Application) | **fait** : 17 tests génériques du coureur (sans aucun Domain) ; 11 tests DT-RUN où le vrai Domain traverse le vrai pipeline ; 300 séquences aléatoires (≈ 4 500 pas) où le coureur et l'interpréteur minimal concordent (état, événements, historique, audit, refus) ; 18 chronologies d'or de bout en bout |
| Empreinte de gel de la tranche, puis gel | **fait le 2026-09-21** : `domain_freeze.py`, `test_domain_freeze.py` (5 tests) ; la porte `verify_domain.py` échoue si l'empreinte diffère |
Les tranches Risque, Priorité, Action, Réconciliation et Prévision ne démarrent qu'après le gel de celle-ci, et importent les faits de la §1.4.

Journal : 2026-09-21 : proposition initiale. 2026-09-21 : validation V1 à V8 ; B3 appliqué ; DD11 et DD15 précisés (V7, V5) ; `finance_ref.py` établie. Aucun code du Domain écrit. 2026-09-21 : code du Domain écrit (phases 1 à 4) ; deux écarts DV1 signalés, non corrigés dans le Domain. 2026-09-21 : B4 appliqué (DV1-1, DV1-2) ; Domain runner ; empreinte posée ; **Domain V1, tranche 1, gelé**.


---

## 13. Écarts signalés pendant l'implémentation (DV1)

Règle de travail : un écart avec un contrat gelé n'est **jamais** corrigé dans le Domain. Il est signalé, arbitré, puis traité par un amendement. Les tests le rendent visible : `KNOWN_WRITE_SCOPE_GAPS` (`domain_tests/test_dt_purity_contracts.py`) listait les écarts connus. **Arbitrage du 2026-09-21 : DV1-1 → option (a), DV1-2 → retrait, réunis dans l'amendement B4. La liste est désormais vide** ; toute divergence nouvelle, ou tout écart réintroduit, fait échouer le test.

### DV1-1 — `collection_cycle` à l'entrée en `OVERDUE` : l'état n'est déclaré ni pour `IssueInvoice` ni pour `InvoiceLifecycleScan`  — **RÉSOLU : B4-a**

| | |
|---|---|
| **Source contradictoire** | Invariants §3.1 bis et Data Contract §3.1 : `collection_cycle` est « incrémenté par le Domain dans la transaction qui fait entrer la facture en `OVERDUE` (transition) ». Registre gelé (`commands.py`) : `IssueInvoice` et `InvoiceLifecycleScan` n'écrivent que `invoices.lifecycle` ; `invoices.collection_cycle` est un état distinct (nature « cache ») écrit seulement par `ApplySettlement` et les trois cas d'usage C12. |
| **Comportement observé** | Le Domain rend, pour une émission tardive (`DRAFT → ISSUED → OVERDUE`) ou un balayage qui fait entrer en `OVERDUE`, deux écritures : `invoices.lifecycle` **et** `invoices.collection_cycle` (`expect {collection_cycle: n}`, `set {collection_cycle: n+1}`). Le coureur refuserait la seconde (`state_not_owned`, `check_state_write`). Sans elle, la règle (a) est impossible : deux entrées en `OVERDUE` successives (facture soldée, règlement annulé, relancée) ne compteraient pas. |
| **Impact** | Bloque l'exécution réelle de `IssueInvoice` (facture émise en retard, cas N4) et de `InvoiceLifecycleScan` (cas N7, N8) ; la structure de `dedup_key` des actions (Invariants §7.1) dépend du cycle. Aucun impact sur le Domain lui-même : la fonction pure est la même quelle que soit la réponse. |
| **Options** | **(a)** amendement **B4** : déclarer `invoices.collection_cycle` dans les écritures de `IssueInvoice` et de `InvoiceLifecycleScan` (deux lignes du Command Registry, régénération, empreinte de gel, journal). **(b)** fusionner le compteur dans l'état `invoices.lifecycle` (redéfinir la clé) : casse la déclaration déjà validée de `ApplySettlement` (B3-a) et la séparation « cache / état ». **(c)** faire incrémenter le cycle par un handler sur `INVOICE_OVERDUE` : contredit « dans la transaction qui fait entrer » et introduit une fenêtre où l'événement précède le compteur. |
| **Recommandation** | **(a)**. Même nature que B3 : mécanique, aucune règle métier nouvelle, cohérente avec ce que `ApplySettlement` déclare déjà. |

### DV1-2 — lectures sur-déclarées par B3-b : `invoices.InvoiceFacts` pour `ReverseAllocation` et `ReversePayment`  — **RÉSOLU : B4-b**

| | |
|---|---|
| **Source contradictoire** | B3-b a déclaré `invoices.InvoiceFacts` (et `organizations.OrgStatus`) pour `AllocatePayment`, `ReverseAllocation` et `ReversePayment`. |
| **Comportement observé** | Seule `AllocatePayment` consomme `InvoiceFacts` (gardes : facture payable, client, devise, dû). Un reversal est autorisé quel que soit l'état de la facture et du client (DD23) : `ReverseAllocation` et `ReversePayment` n'ont besoin que de `OrgStatus` et du registre de leur propre paiement. |
| **Impact** | Aucun sur le comportement. Une lecture déclarée mais inutilisée élargit inutilement ce que ces cas d'usage ont le droit d'appeler, et fausse la trace « fait déclaré → garde ». |
| **Options** | **(a)** retirer `invoices.InvoiceFacts` de ces deux cas d'usage dans le même amendement que DV1-1. **(b)** conserver : sans effet, mais imprécis. |
| **Recommandation** | **(a)**, groupé avec DV1-1 dans **B4** ; c'est une correction de mon propre B3-b, découverte par le Domain. |

### Arbitrage (2026-09-21)

| Écart | Décision | Traitement |
|---|---|---|
| DV1-1 | option (a) : **B4-a** ; (b) et (c) rejetées (nouvelle décision métier ; fenêtre d'incohérence, alors que `dedup_key` dépend du cycle) | `IssueInvoice` et `InvoiceLifecycleScan` déclarent `invoices.collection_cycle` ; la règle reste `transition vers OVERDUE → collection_cycle + 1 → INVOICE_OVERDUE` dans une même unité |
| DV1-2 | retrait : **B4-b** | `AllocatePayment` seule lit `InvoiceFacts` ; `ReverseAllocation` et `ReversePayment` ne lisent que `OrgStatus` |

### Domain runner : ce que le coureur ajoute, et ce qu'il n'ajoute pas

| Ajouté au coureur (générique, sans règle métier) | Où est la règle |
|---|---|
| Adoption des types de `kernel/decision.py` ; `Decision.calls` : un service C12 déclaré est lu, décidé par l'implémentation de **son propriétaire** et vérifié contre **sa** spécification et celle de l'appelant, avant la première écriture ; appliqué dans la même unité | dans `invoices.decide_apply_settlement`, jamais dans le coureur |
| `new_ids` : l'Application génère les identifiants demandés par `impl.ids` (jamais lors d'un rejeu) | `ids_needed` du Domain |
| Lecture par clé naturelle (`Read.key`, `many`), après les verrous, sous le tenant lié | ce qu'il faut lire est dit par le Domain ; les vues (jointures) sont de l'infrastructure |
| Application des `RowChange` par un `row_writer` d'infrastructure (garde d'état C3 : `CONCURRENT_MODIFICATION`, rejouable) ; versions d'agrégat attribuées par l'Application (une par décision et par agrégat) | le Domain ne connaît aucune version (DD15) |

La composition (dépôt en mémoire, vues, assembleur d'état, câblage des 12 cas d'usage) est dans `domain_tests/runner_wiring.py` : le seul endroit qui importe à la fois les Domains, le coureur et les doubles. `verify_runner.py` continue d'interdire au coureur d'importer une couche `domain`. Non traité ici, volontairement : la validation structurelle P3 des charges utiles de niveau C (le transport ne connaît que les classes de contrat sans champs) et la résolution des verrous avant lecture (`Platform.targets`), qui relèvent de l'infrastructure réelle.

### Choix d'implémentation qui ne contredisent aucun contrat (pour information)

| Choix | Pourquoi |
|---|---|
| Types de sortie du Domain (`Decision`, `StateWrite`, `RowChange`, `EventOut`, `ServiceCall`…) dans `verqia/kernel/decision.py` | Le Domain ne peut pas importer `application_runner` (couches, DR1). Le champ `calls` est additif ; le coureur adoptera ces types à l'étape « Domain runner ». |
| Formes de niveau C des faits dans `verqia/<module>/contracts/facts.py` ; `OrgFacts`, `CustomerFacts`, `TakenFacts` dans `verqia/kernel/facts.py` | Seul `contracts` est importable entre modules (DR2). Données seulement, hygiène des contrats appliquée. |
| Charges utiles de niveau C = sous-classes des classes de contrat gelées (`CreateInvoice`, `OpenInvoiceDispute`, `ResolveInvoiceDispute`, `ScanInvoice`, `CreatePayment`, `SettlementRequest`) | Un `isinstance` sur le contrat reste vrai ; aucun champ n'est ajouté à un fichier généré. |
| `gen_contracts.py` et `verify_contracts.py` reconnaissent `verqia/<module>/domain/*.py` et `contracts/facts.py` comme manuscrits | Le contrôle de dérive les aurait signalés « en trop » ; les fichiers du Domain sont vérifiés par leurs propres tests et par `verify_domain.py`. |
| La composition C12 (`ServiceCall` → `invoices.decide_apply_settlement`) est jouée par un interpréteur de test (`domain_tests/support.py`), pas par le coureur | Phase 3 : la composition est démontrée sans faire du coureur une source de règles ; le raccord réel est l'étape « Domain runner ». |
