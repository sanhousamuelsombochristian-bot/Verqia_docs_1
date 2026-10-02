# VERQIA — Preuves des invariants du Domain V1, tranche 1 (généré)

Généré par `architecture_registry/verify_domain.py --doc` à partir de `domain_catalogue.py`, `domain_proofs.py` et `domain_mutations.py`. Ne pas modifier à la main.

Chaque invariant du Domain (`DOMAIN_V1_TRANCHE1_FACTURE_ECHEANCE_PAIEMENT.md`, §5) a : une règle statique éventuelle, des tests qui le démontrent et des mutations de code qui savent le casser.
Un invariant n'est **prouvé** que si ses tests passent et si chacune de ses mutations est **tuée** (`--run --mutate`).

Règles statiques : **R-D1** imports : bibliothèque standard, noyau et `contracts` seulement (AR-01, DR2) · **R-D2** aucune horloge, aucun aléa, aucune entrée-sortie (AR-02) · **R-D3** aucun flottant ni division réelle (contrat §0) · **R-D4** le règlement et le statut ne s'écrivent que par `derive_*` ; le cycle de vie que par `transition` · **R-D5** le solde (`total − paid`) et la comparaison d'échéance ne vivent que dans le module des faits

## Invariants

| # | Invariant | Nature | Source | Tests | Mutations |
|---|---|---|---|---|---|
| IF1 | `0 ≤ paid ≤ total` | E | CK | 3 | `M-IF1-bounds-unchecked` |
| IF2 | règlement = fonction de (`paid`, `total`) : trois branches exclusives | E | CK, T4 | 3 | `M-IF2-partial-includes-total` |
| IF3 | `settled_on` renseigné si et seulement si `PAID`, et égal à la date de valeur la plus tardive des paiements de contribution positive (V7) | E | CK | 4 | `M-IF3-settled-on-without-full-payment`, `M-IF3-settled-on-earliest-instead-of-latest` |
| IF4 | `DRAFT`, `CANCELLED`, `VOID` implique `paid = 0` et règlement `UNPAID` | E | CK, T6 | 2 | `M-IF4-positive-settlement-on-unpayable`, `M-IF4-void-with-payments` |
| IF5 | `ISSUED…OVERDUE` implique `total > 0` | E | CK | 1 | `M-IF5-zero-total-issued` |
| IF6 | `issued_at` renseigné si et seulement si l'état n'est ni `DRAFT` ni `CANCELLED` | E | contrat §3.1 | 3 | `M-IF6-issued-at-not-written` |
| IF7 | `cancelled_at` et `cancel_reason` renseignés si et seulement si `CANCELLED` ou `VOID` | E | contrat §3.1 | 3 | `M-IF7-cancel-reason-not-written` |
| IF8 | `due_date ≥ issue_date` | E | CK | 1 | `M-IF8-dates-unchecked` |
| IF9 | `Σ line_total = total` et `line_total = arrondi(quantité × prix)` | E | T9, T7 | 3 | `M-IF9-rounding-down` |
| IF10 | après émission, `number`, `customer_id`, `currency`, `issue_date`, `due_date`, `total`, lignes sont inchangés par toute décision | T | T13, T7 | 3 | `M-IF10-body-rewritten` |
| IF11 | le cycle de vie n'avance qu'en avant, et seulement par une table de transitions | T | SM §3, T14 | 4 | `M-IF11-lifecycle-can-go-back`, `M-IF11-due-soon-window-off-by-one` |
| IF12 | `collection_cycle` ne décroît jamais ; il augmente de 0 ou 1 par décision | T | Invariants §3.1 bis | 5 | `M-IF12-cycle-incremented-by-two`, `M-IF12-rule-a-missing`, `M-IF12-rule-b-counted-twice` |
| IF13 | tout changement d'état porte son événement ; le seul changement sans événement de facture est `PARTIALLY_PAID → PARTIALLY_PAID` | T | C5 | 4 | `M-IF13-scan-without-event` |
| IF14 | un litige `OPEN` ne modifie ni le cycle de vie ni le règlement ; `VOID` est refusé tant qu'il existe | T | SM §5, T15 | 2 | `M-IF14-void-with-open-dispute` |
| IF15 | au plus un litige `OPEN` par facture | E | UQ partiel | 1 | `M-IF15-second-open-dispute` |
| IF16 | une facture `PAID` ne reçoit plus de transition temporelle ; son cycle de vie est recalculé en avant quand son règlement est annulé | T | SM §3 (gel), B3-a | 2 | `M-IF16-scan-touches-paid-invoices`, `M-IF16-no-recalculation-after-reversal` |
| IP1 | `0 ≤ allocated ≤ amount` et `amount > 0` | E | T1, CK | 2 | `M-IP1-payment-overallocated` |
| IP2 | `allocated = Σ lignes du registre` ; `paid` d'une facture = `Σ lignes du registre` de cette facture | E | T4, T5 | 3 | `M-IP2-allocated-off-by-one` |
| IP3 | statut = fonction de (`allocated`, `amount`) hors `REVERSED` ; `REVERSED` implique `allocated = 0` | E | CK | 3 | `M-IP3-status-never-allocated` |
| IP4 | aucune ligne positive sur un paiement `REVERSED` | T | T10 | 1 | `M-IP4-reversed-payment-accepts-allocation` |
| IP5 | `amount`, `currency`, `customer_id`, `reference`, `method`, `received_at`, `value_date` inchangés par toute décision | T | Invariants §4 | 2 | `M-IP5-amount-rewritten` |
| IA1 | ligne jamais nulle ; signe et `reverses_allocation_id` cohérents ; reversal avec motif | E | CK | 2 | `M-IA1-reversal-without-reason` |
| IA2 | pour chaque origine, `Σ reversals liés ≥ −montant d'origine` | E | T3 | 1 | `M-IA2-reversal-beyond-origin` |
| IA3 | aucune ligne positive nette sur une facture non payable | E | T6 | 1 | `M-IA3-allocation-to-unpayable-invoice` |
| IA4 | même client et même devise entre paiement, ligne et facture | E | FK composites | 1 | `M-IA4-customer-unchecked` |
| IA5 | le registre est append-only : aucune décision ne réécrit ni ne supprime une ligne existante | T | T8 | 1 | `M-IA5-ledger-rewritten` |
| IA6 | `Σ lignes d'une facture ∈ [0, total]` | E | T2 | 2 | `M-IA6-invoice-overallocated` |
| IX1 | conservation : `Σ payments.allocated = Σ invoices.paid = Σ registre` sur toute séquence de décisions valides | X | C12 | 4 | `M-IX1-reversal-adds-money` |
| IX2 | aucune création d'argent : `Σ paid` ne dépasse jamais `Σ amount` des paiements non `REVERSED` | X | C12 | 2 | `M-IP1-payment-overallocated` |
| IX3 | `ReversePayment` laisse `allocated = 0` et chaque facture touchée avec `paid` diminué exactement de ses allocations actives | X | EC-05 | 2 | `M-IX3-reverse-payment-forgets-allocations` |
| IN1 | déterminisme : mêmes entrées, même `Decision` | D | P8 | 3 | `M-IN1-nondeterministic-result` |
| IN2 | non-mutation : l'état d'entrée n'est jamais modifié | D | P8 | 2 | `M-IN2-input-mutated` |
| IN3 | indépendance de l'horloge système : résultat identique quelle que soit l'heure de l'hôte, jour local de l'organisation | D | TD23, AR-02 | 4 | `M-IN3-utc-day-instead-of-local-day` |
| IN4 | post-condition : l'état résultant d'une décision satisfait `check_*` | D | DD21 | 2 | `M-IF6-issued-at-not-written`, `M-IF7-cancel-reason-not-written` |
| IN5 | tout code d'erreur levé appartient au catalogue ; tout événement émis appartient aux `emits` du cas d'usage ; toute écriture appartient à ses états déclarés | D | P8, AP-05, AP-02 | 2 | `M-IN5-undeclared-event` |

## Mutations

| Mutation | Fichiers | Tests qui doivent tomber |
|---|---|---|
| `M-IF1-bounds-unchecked` | settlement.py | 1 |
| `M-IF2-partial-includes-total` | facts.py | 2 |
| `M-IF3-settled-on-without-full-payment` | settlement.py | 2 |
| `M-IF3-settled-on-earliest-instead-of-latest` | settlement.py | 2 |
| `M-IF4-positive-settlement-on-unpayable` | settlement.py | 1 |
| `M-IF4-void-with-payments` | lifecycle.py | 1 |
| `M-IF5-zero-total-issued` | lifecycle.py | 1 |
| `M-IF6-issued-at-not-written` | lifecycle.py | 1 |
| `M-IF7-cancel-reason-not-written` | lifecycle.py | 1 |
| `M-IF8-dates-unchecked` | body.py | 1 |
| `M-IF9-rounding-down` | invariants.py | 3 |
| `M-IF10-body-rewritten` | lifecycle.py | 1 |
| `M-IF11-lifecycle-can-go-back` | lifecycle.py | 2 |
| `M-IF11-due-soon-window-off-by-one` | facts.py | 2 |
| `M-IF12-cycle-incremented-by-two` | lifecycle.py | 1 |
| `M-IF12-rule-a-missing` | lifecycle.py | 2 |
| `M-IF12-rule-b-counted-twice` | settlement.py | 2 |
| `M-IF13-scan-without-event` | lifecycle.py | 2 |
| `M-IF14-void-with-open-dispute` | lifecycle.py | 1 |
| `M-IF15-second-open-dispute` | dispute.py | 1 |
| `M-IF16-scan-touches-paid-invoices` | lifecycle.py | 2 |
| `M-IF16-no-recalculation-after-reversal` | settlement.py | 1 |
| `M-IP1-payment-overallocated` | allocations.py | 1 |
| `M-IP2-allocated-off-by-one` | allocations.py | 1 |
| `M-IP3-status-never-allocated` | facts.py | 2 |
| `M-IP4-reversed-payment-accepts-allocation` | allocations.py | 1 |
| `M-IP5-amount-rewritten` | allocations.py | 1 |
| `M-IA1-reversal-without-reason` | allocations.py | 1 |
| `M-IA2-reversal-beyond-origin` | allocations.py | 1 |
| `M-IA3-allocation-to-unpayable-invoice` | allocations.py | 1 |
| `M-IA4-customer-unchecked` | allocations.py | 1 |
| `M-IA5-ledger-rewritten` | allocations.py | 1 |
| `M-IA6-invoice-overallocated` | allocations.py | 1 |
| `M-IX1-reversal-adds-money` | settlement.py | 2 |
| `M-IX3-reverse-payment-forgets-allocations` | facts.py | 2 |
| `M-IN1-nondeterministic-result` | dispute.py | 1 |
| `M-IN2-input-mutated` | lifecycle.py | 1 |
| `M-IN3-utc-day-instead-of-local-day` | calendar.py | 2 |
| `M-IN5-undeclared-event` | lifecycle.py | 2 |

`DOMAIN_COUNT = 35` invariants · `MUTATIONS = 39`.

