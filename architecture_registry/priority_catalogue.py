"""Catalogue des invariants du Priority Domain V1 : LA source. Le document de preuves, la porte
(`verify_priority_domain.py`) et les tests en dérivent. Le texte est celui de `PRIORITY_DOMAIN_V1.md` (PD1 à PD11,
DV3-1 à DV3-9) ; il ne se réécrit pas pour faire coïncider des tests. Un nouvel invariant exige sa preuve
(`priority_proofs.py`).

Chaque entrée : (identifiant, énoncé, nature, source gelée). Natures : E = prédicat d'état, D = propriété d'une
décision, T = propriété de transition (niveau publié), X = frontière Application (hors Domain, mais démontrée par
ce même harnais). Numérotation PI (Priority Invariant), indépendante de RI (Risk).
"""
INVARIANTS = [
    ('PI1', '0 ≤ score ≤ 95, maximum (95, PAS 100 : retard et échéance s\'excluent) et minimum (0) atteignables, entier', 'E', 'PD5'),
    ('PI2', 'chaque facteur (montant, retard, risque, échéance, attention) reste dans ses bornes déclarées (PD4)', 'E', 'PD4'),
    ('PI3', 'score non-décroissant en montant, en retard et en niveau de risque', 'D', 'PD4'),
    ('PI4', '`previous_level` réellement pris en compte par l\'hystérésis, jamais ignoré (distinct du score seul)', 'D', 'PD7'),
    ('PI5', '`PriorityNormalizedInputs` égal ⇔ `Decision` vide (aucune écriture), sans hachage', 'D', 'PD11.1'),
    ('PI5bis', "(Application, hors Domain) `input_hash` égal ⇔ `PriorityNormalizedInputs` égal", 'X', 'PD10.2'),
    ('PI6', '`reasons.factors` ne contient jamais de valeur brute, uniquement des points normalisés (`pts=N`)', 'E', 'PD10.2'),
    ('PI7', 'niveau publié = fonction pure de (score, niveau publié précédent), jamais du score seul', 'T', 'PD7'),
    ('PI8', "frontière d'hystérésis : `score+MARGIN == seuil` MAINTIENT le niveau, `score+MARGIN < seuil` permet la descente", 'T', 'PD7'),
    ('PI9', 'plafonds : le plus bas des plafonds actifs l\'emporte (`min`), un plafond ne relève JAMAIS un niveau', 'T', 'PD7, §3.4'),
    ('PI10', "`caps`/`reasons.caps` liste la CONDITION active, pas seulement l'effet (signal explicatif, même règle que `reconciliation_pending`)", 'E', 'PD7'),
    ('PI11', '`dispute_no_collectible` est une DÉRIVATION du Domain (`has_open_dispute ET collectible_minor==0`), jamais un champ brut reçu séparément', 'E', '§ DV3-5'),
    ('PI12', '`reconciliation_pending` n\'entre JAMAIS dans le score, le niveau ni les plafonds — seulement `normalized_inputs`/`input_hash`/`reasons.signals`', 'D', 'PD9'),
    ('PI13', '`PRIORITY_CHANGED` émis SSI le niveau publié change ET qu\'un `previous` existait', 'T', 'PD11.2, § DV2-7-équivalent'),
    ('PI14', '`Decision.writes` non vide SSI `PriorityNormalizedInputs` diffère de `previous.normalized_inputs` ; `computed_at` n\'apparaît dans AUCUNE `Decision`', 'T', 'PD11.1'),
    ('PI15', 'éligibilité à TROIS états : `DRAFT` ⇒ aucun élément ; fermée (non-`DRAFT`) ⇒ élément `NONE`/`CLOSED` ; active ⇒ calcul complet', 'E', 'PD3'),
    ('PI16', 'déterminisme, non-mutation de l\'entrée, indépendance de l\'horloge système, aucun flottant/aléa/E-S', 'D', 'purity (AR-01/AR-02-équivalent)'),
    # ---- au-delà du Domain pur : propriétés d'Application/infrastructure démontrées par ce même harnais (même
    # esprit que RI15-RI17 pour Risk), pour la fermeture des mutations MUT-P.
    ('PI17', "(Application) `PriorityRecalculationRequested{scope=CUSTOMER}` est résolu par ÉNUMÉRATION bornée (≤ 200) DANS L'INFRASTRUCTURE, jamais dans `priority.domain` ; `RecomputePriority` ne porte jamais `scope`/`customer_id` (§ DV3-9)", 'X', 'PD11.5'),
    ('PI18', "(Application) isolation tenant : deux organisations ne partagent jamais une lecture, un instantané ou un événement Priority, même avec un `invoice_id` identique", 'X', 'TD17/TD26'),
    ('PI19', "(Application) le `risk_level` consommé par Priority est la sortie RÉELLEMENT publiée et committée par Risk, jamais recalculée par Priority (RP-E : Risk → Priority, jamais l'inverse)", 'X', 'PD2.2'),
    ('PI20', "(Application) les cinq lectures déclarées de DV3-8/B6 sont celles qui atteignent réellement le Domain, sans substitution silencieuse", 'X', 'B6, PD2.2'),
]
