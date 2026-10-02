"""Catalogue des invariants du Risk Domain V1 : LA source. Le document de preuves, la porte (`verify_risk_domain.py`) et
les tests en dérivent. Le texte est celui de RD16 (`RISK_DOMAIN_V1.md`, §16) ; il ne se réécrit pas pour faire coïncider
des tests. Un nouvel invariant exige sa preuve (`risk_proofs.py`).

Chaque entrée : (identifiant, énoncé, nature, source gelée). Natures : E = prédicat d'état, D = propriété d'une décision,
T = propriété de transition (niveau publié), X = frontière Application (hors Domain, mais démontrée par ce même harnais).
"""
INVARIANTS = [
    ('RI1', '0 ≤ score ≤ 100, maximum (100) et minimum (0) atteignables', 'E', 'RD16 §2.7'),
    ('RI2', 'chaque facteur reste dans ses bornes déclarées (RD4)', 'E', 'RD16 §2.3'),
    ('RI3', 'score monotone croissant en chacune de ses six composantes (D, historique L/M, B, Eo, R, T)', 'D', 'RD16 §7'),
    ('RI4', '`n < 3` ⇒ `history_late_pts = history_delay_pts = 0` et `confidence = LOW`', 'E', 'RP-G'),
    ('RI5', '(Domain) `NormalizedRiskInputs` égal ⇔ RD11.1 déclenché (`Decision` vide) — sans hachage', 'D', 'RP14, § DV2-8'),
    ('RI5bis', "(Application, hors Domain) `input_hash` égal ⇔ `NormalizedRiskInputs` égal", 'X', 'RP14, § DV2-8'),
    ('RI6', '`NormalizedRiskInputs` stable à l\'intérieur d\'une tranche de points, distinct entre tranches, sensible au niveau publié précédent', 'D', 'RD16 §2.7, §7'),
    ('RI7', '`factors` ne contient jamais de valeur brute ni de taille d\'échantillon', 'E', 'RP14'),
    ('RI8', 'niveau publié = fonction pure de (score, niveau publié précédent), jamais du score seul', 'T', 'RD7/RD8'),
    ('RI9', 'pas de plafond en Risk : niveau publié = niveau stabilisé', 'T', 'RD16 §3.4 vs §1.3'),
    ('RI10', '`RISK_CHANGED` émis SSI le niveau publié change ET qu\'un niveau précédent existait', 'T', 'RD16 §8, § DV2-7'),
    ('RI11', '(Domain) `Decision.writes` non vide SSI `NormalizedRiskInputs` diffère de `previous.normalized_inputs`', 'T', 'RD16 §8, § DV2-8'),
    ('RI12', '`NormalizedRiskInputs` inchangé ⇒ `Decision` totalement vide ; `computed_at` n\'apparaît dans AUCUNE `Decision`', 'T', 'RD16 §8, § DV2-8'),
    ('RI13', 'déterminisme, non-mutation de l\'entrée, indépendance de l\'horloge système', 'D', 'RD16 §5.3 (repris de la tranche 1)'),
    ('RI14', 'conservation de l\'éligibilité : `has_ever_issued=False` jamais de profil, `True` peut avoir score 0', 'E', 'RD3'),
    # ---- au-delà de RD16 : propriétés d'Application/infrastructure démontrées par ce même harnais (même esprit que RI5bis),
    # ajoutées pour la fermeture des mutations MUT-R (M8 à M11) ; RD16 ne les numérote pas, ce document les rend traçables.
    ('RI15', "(Application) isolation tenant : deux organisations ne partagent jamais une lecture, un snapshot ou un événement Risk, même avec un `customer_id` identique", 'X', 'TD17/TD26'),
    ('RI16', "(Application) le profil et son duplicata LOG (`risk_snapshots`) sont écrits dans LA MÊME unité, jamais l'un sans l'autre", 'X', 'DV2-9, TD25'),
    ('RI17', '(Application) les sept lectures déclarées de B5 sont celles qui atteignent réellement le Domain, sans substitution silencieuse', 'X', 'B5, RD2.3'),
]
