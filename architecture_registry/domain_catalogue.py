"""Catalogue des invariants du Domain V1, tranche 1 (Facture / Échéance / Paiement) : LA source. Le document de preuves, la porte (`verify_domain.py`) et les tests
en dérivent. Le texte est celui de la §5 de `DOMAIN_V1_TRANCHE1_FACTURE_ECHEANCE_PAIEMENT.md` ; il ne se réécrit pas pour faire coïncider des tests.
Un nouvel invariant exige sa preuve (`domain_proofs.py`).

Chaque entrée : (identifiant, énoncé, nature, source gelée). Natures : E = prédicat d'état, T = propriété de transition, X = inter-agrégats, D = propriété d'une décision.
"""
INVARIANTS = [
    # ---- facture (§5.1)
    ('IF1', '`0 ≤ paid ≤ total`', 'E', 'CK'),
    ('IF2', 'règlement = fonction de (`paid`, `total`) : trois branches exclusives', 'E', 'CK, T4'),
    ('IF3', '`settled_on` renseigné si et seulement si `PAID`, et égal à la date de valeur la plus tardive des paiements de contribution positive (V7)', 'E', 'CK'),
    ('IF4', '`DRAFT`, `CANCELLED`, `VOID` implique `paid = 0` et règlement `UNPAID`', 'E', 'CK, T6'),
    ('IF5', '`ISSUED…OVERDUE` implique `total > 0`', 'E', 'CK'),
    ('IF6', '`issued_at` renseigné si et seulement si l\'état n\'est ni `DRAFT` ni `CANCELLED`', 'E', 'contrat §3.1'),
    ('IF7', '`cancelled_at` et `cancel_reason` renseignés si et seulement si `CANCELLED` ou `VOID`', 'E', 'contrat §3.1'),
    ('IF8', '`due_date ≥ issue_date`', 'E', 'CK'),
    ('IF9', '`Σ line_total = total` et `line_total = arrondi(quantité × prix)`', 'E', 'T9, T7'),
    ('IF10', 'après émission, `number`, `customer_id`, `currency`, `issue_date`, `due_date`, `total`, lignes sont inchangés par toute décision', 'T', 'T13, T7'),
    ('IF11', 'le cycle de vie n\'avance qu\'en avant, et seulement par une table de transitions', 'T', 'SM §3, T14'),
    ('IF12', '`collection_cycle` ne décroît jamais ; il augmente de 0 ou 1 par décision', 'T', 'Invariants §3.1 bis'),
    ('IF13', 'tout changement d\'état porte son événement ; le seul changement sans événement de facture est `PARTIALLY_PAID → PARTIALLY_PAID`', 'T', 'C5'),
    ('IF14', 'un litige `OPEN` ne modifie ni le cycle de vie ni le règlement ; `VOID` est refusé tant qu\'il existe', 'T', 'SM §5, T15'),
    ('IF15', 'au plus un litige `OPEN` par facture', 'E', 'UQ partiel'),
    ('IF16', 'une facture `PAID` ne reçoit plus de transition temporelle ; son cycle de vie est recalculé en avant quand son règlement est annulé', 'T', 'SM §3 (gel), B3-a'),
    # ---- paiement et registre (§5.2)
    ('IP1', '`0 ≤ allocated ≤ amount` et `amount > 0`', 'E', 'T1, CK'),
    ('IP2', '`allocated = Σ lignes du registre` ; `paid` d\'une facture = `Σ lignes du registre` de cette facture', 'E', 'T4, T5'),
    ('IP3', 'statut = fonction de (`allocated`, `amount`) hors `REVERSED` ; `REVERSED` implique `allocated = 0`', 'E', 'CK'),
    ('IP4', 'aucune ligne positive sur un paiement `REVERSED`', 'T', 'T10'),
    ('IP5', '`amount`, `currency`, `customer_id`, `reference`, `method`, `received_at`, `value_date` inchangés par toute décision', 'T', 'Invariants §4'),
    ('IA1', 'ligne jamais nulle ; signe et `reverses_allocation_id` cohérents ; reversal avec motif', 'E', 'CK'),
    ('IA2', 'pour chaque origine, `Σ reversals liés ≥ −montant d\'origine`', 'E', 'T3'),
    ('IA3', 'aucune ligne positive nette sur une facture non payable', 'E', 'T6'),
    ('IA4', 'même client et même devise entre paiement, ligne et facture', 'E', 'FK composites'),
    ('IA5', 'le registre est append-only : aucune décision ne réécrit ni ne supprime une ligne existante', 'T', 'T8'),
    ('IA6', '`Σ lignes d\'une facture ∈ [0, total]`', 'E', 'T2'),
    # ---- inter-agrégats (§5.3)
    ('IX1', 'conservation : `Σ payments.allocated = Σ invoices.paid = Σ registre` sur toute séquence de décisions valides', 'X', 'C12'),
    ('IX2', 'aucune création d\'argent : `Σ paid` ne dépasse jamais `Σ amount` des paiements non `REVERSED`', 'X', 'C12'),
    ('IX3', '`ReversePayment` laisse `allocated = 0` et chaque facture touchée avec `paid` diminué exactement de ses allocations actives', 'X', 'EC-05'),
    # ---- décision (§5.3)
    ('IN1', 'déterminisme : mêmes entrées, même `Decision`', 'D', 'P8'),
    ('IN2', 'non-mutation : l\'état d\'entrée n\'est jamais modifié', 'D', 'P8'),
    ('IN3', 'indépendance de l\'horloge système : résultat identique quelle que soit l\'heure de l\'hôte, jour local de l\'organisation', 'D', 'TD23, AR-02'),
    ('IN4', 'post-condition : l\'état résultant d\'une décision satisfait `check_*`', 'D', 'DD21'),
    ('IN5', 'tout code d\'erreur levé appartient au catalogue ; tout événement émis appartient aux `emits` du cas d\'usage ; toute écriture appartient à ses états déclarés', 'D', 'P8, AP-05, AP-02'),
]
