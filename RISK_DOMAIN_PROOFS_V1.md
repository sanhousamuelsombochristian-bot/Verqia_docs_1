# VERQIA — Preuves des invariants du Risk Domain V1 (généré)

Généré par `architecture_registry/verify_risk_domain.py --doc` à partir de `risk_catalogue.py`, `risk_proofs.py` et `risk_mutations.py`. Ne pas modifier à la main.

Chaque invariant (`RISK_DOMAIN_V1.md`, RD16, + RI15-RI17 d'infrastructure) a : une règle statique éventuelle, des tests qui le démontrent et des mutations de code qui savent le casser.
Un invariant n'est **prouvé** que si ses tests passent et si chacune de ses mutations est **tuée** (`--run --mutate`).

Règles statiques : **R-R1** imports : bibliothèque standard, noyau et `contracts` seulement (AR-01, DR2) · **R-R2** aucune horloge, aucun aléa, aucun flottant, aucune entrée-sortie (AR-02)

## Invariants

| # | Invariant | Nature | Source | Tests | Mutations |
|---|---|---|---|---|---|
| RI1 | 0 ≤ score ≤ 100, maximum (100) et minimum (0) atteignables | E | RD16 §2.7 | 1 | `M1-score-drops-a-component` |
| RI2 | chaque facteur reste dans ses bornes déclarées (RD4) | E | RD16 §2.3 | 4 | `M5-broken-points-wrong-multiplier`, `M2-aggregate-d-eo-drops-the-is-late-filter` |
| RI3 | score monotone croissant en chacune de ses six composantes (D, historique L/M, B, Eo, R, T) | D | RD16 §7 | 1 | `M5-broken-points-wrong-multiplier` |
| RI4 | `n < 3` ⇒ `history_late_pts = history_delay_pts = 0` et `confidence = LOW` | E | RP-G | 2 | `M5-broken-points-wrong-multiplier` |
| RI5 | (Domain) `NormalizedRiskInputs` égal ⇔ RD11.1 déclenché (`Decision` vide) — sans hachage | D | RP14, § DV2-8 | 3 | `M6-steady-state-branch-disabled` |
| RI5bis | (Application, hors Domain) `input_hash` égal ⇔ `NormalizedRiskInputs` égal | X | RP14, § DV2-8 | 1 | `M8-input-hash-becomes-a-constant` |
| RI6 | `NormalizedRiskInputs` stable à l'intérieur d'une tranche de points, distinct entre tranches, sensible au niveau publié précédent | D | RD16 §2.7, §7 | 1 | `M1-score-drops-a-component` |
| RI7 | `factors` ne contient jamais de valeur brute ni de taille d'échantillon | E | RP14 | 1 | `M5-broken-points-wrong-multiplier` |
| RI8 | niveau publié = fonction pure de (score, niveau publié précédent), jamais du score seul | T | RD7/RD8 | 2 | `M3-stabilise-drops-the-hysteresis-reprieve` |
| RI9 | pas de plafond en Risk : niveau publié = niveau stabilisé | T | RD16 §3.4 vs §1.3 | 1 | `M3-stabilise-drops-the-hysteresis-reprieve` |
| RI10 | `RISK_CHANGED` émis SSI le niveau publié change ET qu'un niveau précédent existait | T | RD16 §8, § DV2-7 | 3 | `M7-event-emitted-without-a-level-change` |
| RI11 | (Domain) `Decision.writes` non vide SSI `NormalizedRiskInputs` diffère de `previous.normalized_inputs` | T | RD16 §8, § DV2-8 | 3 | `M6-steady-state-branch-disabled` |
| RI12 | `NormalizedRiskInputs` inchangé ⇒ `Decision` totalement vide ; `computed_at` n'apparaît dans AUCUNE `Decision` | T | RD16 §8, § DV2-8 | 2 | `M6-steady-state-branch-disabled` |
| RI13 | déterminisme, non-mutation de l'entrée, indépendance de l'horloge système | D | RD16 §5.3 (repris de la tranche 1) | 2 | `M4-eligibility-always-true` |
| RI14 | conservation de l'éligibilité : `has_ever_issued=False` jamais de profil, `True` peut avoir score 0 | E | RD3 | 2 | `M4-eligibility-always-true` |
| RI15 | (Application) isolation tenant : deux organisations ne partagent jamais une lecture, un snapshot ou un événement Risk, même avec un `customer_id` identique | X | TD17/TD26 | 1 | `M9-events-leak-across-organizations` |
| RI16 | (Application) le profil et son duplicata LOG (`risk_snapshots`) sont écrits dans LA MÊME unité, jamais l'un sans l'autre | X | DV2-9, TD25 | 1 | `M10-snapshot-duplication-disabled` |
| RI17 | (Application) les sept lectures déclarées de B5 sont celles qui atteignent réellement le Domain, sans substitution silencieuse | X | B5, RD2.3 | 2 | `M11-a-declared-read-is-silently-dropped` |

## Mutations

| Mutation | Fichiers | Tests qui doivent tomber |
|---|---|---|
| `M1-score-drops-a-component` | scoring.py | 1 |
| `M2-aggregate-d-eo-drops-the-is-late-filter` | aggregation.py | 1 |
| `M3-stabilise-drops-the-hysteresis-reprieve` | scoring.py | 1 |
| `M4-eligibility-always-true` | profile.py | 1 |
| `M5-broken-points-wrong-multiplier` | scoring.py | 1 |
| `M6-steady-state-branch-disabled` | profile.py | 1 |
| `M7-event-emitted-without-a-level-change` | profile.py | 1 |
| `M8-input-hash-becomes-a-constant` | runner_wiring.py | 1 |
| `M9-events-leak-across-organizations` | runner_wiring.py | 1 |
| `M10-snapshot-duplication-disabled` | runner_wiring.py | 1 |
| `M11-a-declared-read-is-silently-dropped` | runner_wiring.py | 1 |

`RISK_DOMAIN_COUNT = 18` invariants · `MUTATIONS = 11`.

