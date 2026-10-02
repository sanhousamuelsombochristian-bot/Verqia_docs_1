# VERQIA — Preuves des invariants du Priority Domain V1 (généré)

Généré par `architecture_registry/verify_priority_domain.py --doc` à partir de `priority_catalogue.py`, `priority_proofs.py` et `priority_mutations.py`. Ne pas modifier à la main.

Chaque invariant (`PRIORITY_DOMAIN_V1.md`, PD1-PD11 + DV3, + PI17-PI20 d'infrastructure) a : une règle statique éventuelle, des tests qui le démontrent et des mutations de code qui savent le casser.
Un invariant n'est **prouvé** que si ses tests passent et si chacune de ses mutations est **tuée** (`--run --mutate`).

Règles statiques : **P-R1** imports : bibliothèque standard, noyau, `priority` (propre module) et `contracts` des autres seulement (AR-01-équivalent, DR2) · **P-R2** aucune horloge, aucun aléa, aucun flottant, aucune entrée-sortie (AR-02-équivalent)

## Invariants

| # | Invariant | Nature | Source | Tests | Mutations |
|---|---|---|---|---|---|
| PI1 | 0 ≤ score ≤ 95, maximum (95, PAS 100 : retard et échéance s'excluent) et minimum (0) atteignables, entier | E | PD5 | 1 | `PM1-rank-score-drops-attention` |
| PI2 | chaque facteur (montant, retard, risque, échéance, attention) reste dans ses bornes déclarées (PD4) | E | PD4 | 5 | `PM2-amount-points-wrong-multiplier` |
| PI3 | score non-décroissant en montant, en retard et en niveau de risque | D | PD4 | 1 | `PM5-risk-level-ignored` |
| PI4 | `previous_level` réellement pris en compte par l'hystérésis, jamais ignoré (distinct du score seul) | D | PD7 | 2 | `PM4-hysteresis-ignores-the-real-previous-level` |
| PI5 | `PriorityNormalizedInputs` égal ⇔ `Decision` vide (aucune écriture), sans hachage | D | PD11.1 | 1 | `PM18-steady-state-branch-disabled` |
| PI5bis | (Application, hors Domain) `input_hash` égal ⇔ `PriorityNormalizedInputs` égal | X | PD10.2 | 1 | `PM15-input-hash-becomes-a-constant` |
| PI6 | `reasons.factors` ne contient jamais de valeur brute, uniquement des points normalisés (`pts=N`) | E | PD10.2 | 1 | `PM19-reasons-factor-format-drops-the-pts-prefix` |
| PI7 | niveau publié = fonction pure de (score, niveau publié précédent), jamais du score seul | T | PD7 | 2 | `PM3-stabilise-drops-the-hysteresis-reprieve` |
| PI8 | frontière d'hystérésis : `score+MARGIN == seuil` MAINTIENT le niveau, `score+MARGIN < seuil` permet la descente | T | PD7 | 2 | `PM12-threshold-boundary-shifted` |
| PI9 | plafonds : le plus bas des plafonds actifs l'emporte (`min`), un plafond ne relève JAMAIS un niveau | T | PD7, §3.4 | 2 | `PM6-promise-or-hold-cap-removed`, `PM7-dispute-cap-condition-inverted` |
| PI10 | `caps`/`reasons.caps` liste la CONDITION active, pas seulement l'effet (signal explicatif, même règle que `reconciliation_pending`) | E | PD7 | 1 | `PM7-dispute-cap-condition-inverted` |
| PI11 | `dispute_no_collectible` est une DÉRIVATION du Domain (`has_open_dispute ET collectible_minor==0`), jamais un champ brut reçu séparément | E | § DV3-5 | 1 | `PM8-dispute-no-collectible-drops-the-collectible-check` |
| PI12 | `reconciliation_pending` n'entre JAMAIS dans le score, le niveau ni les plafonds — seulement `normalized_inputs`/`input_hash`/`reasons.signals` | D | PD9 | 2 | `PM9-reconciliation-pending-leaks-into-the-score` |
| PI13 | `PRIORITY_CHANGED` émis SSI le niveau publié change ET qu'un `previous` existait | T | PD11.2, § DV2-7-équivalent | 2 | `PM13-event-emitted-on-score-only-change` |
| PI14 | `Decision.writes` non vide SSI `PriorityNormalizedInputs` diffère de `previous.normalized_inputs` ; `computed_at` n'apparaît dans AUCUNE `Decision` | T | PD11.1 | 2 | `PM18-steady-state-branch-disabled` |
| PI15 | éligibilité à TROIS états : `DRAFT` ⇒ aucun élément ; fermée (non-`DRAFT`) ⇒ élément `NONE`/`CLOSED` ; active ⇒ calcul complet | E | PD3 | 3 | `PM10-draft-treated-as-active`, `PM11-closed-invoice-treated-as-active` |
| PI16 | déterminisme, non-mutation de l'entrée, indépendance de l'horloge système, aucun flottant/aléa/E-S | D | purity (AR-01/AR-02-équivalent) | 2 | `PM1-rank-score-drops-attention` |
| PI17 | (Application) `PriorityRecalculationRequested{scope=CUSTOMER}` est résolu par ÉNUMÉRATION bornée (≤ 200) DANS L'INFRASTRUCTURE, jamais dans `priority.domain` ; `RecomputePriority` ne porte jamais `scope`/`customer_id` (§ DV3-9) | X | PD11.5 | 3 | `PM14-customer-batch-cap-removed` |
| PI18 | (Application) isolation tenant : deux organisations ne partagent jamais une lecture, un instantané ou un événement Priority, même avec un `invoice_id` identique | X | TD17/TD26 | 2 | `PM16-events-leak-across-organizations` |
| PI19 | (Application) le `risk_level` consommé par Priority est la sortie RÉELLEMENT publiée et committée par Risk, jamais recalculée par Priority (RP-E : Risk → Priority, jamais l'inverse) | X | PD2.2 | 1 | `PM17-the-risk-level-read-is-silently-dropped` |
| PI20 | (Application) les cinq lectures déclarées de DV3-8/B6 sont celles qui atteignent réellement le Domain, sans substitution silencieuse | X | B6, PD2.2 | 2 | `PM17-the-risk-level-read-is-silently-dropped` |

## Mutations

| Mutation | Fichiers | Tests qui doivent tomber |
|---|---|---|
| `PM1-rank-score-drops-attention` | scoring.py | 1 |
| `PM2-amount-points-wrong-multiplier` | scoring.py | 1 |
| `PM3-stabilise-drops-the-hysteresis-reprieve` | scoring.py | 1 |
| `PM4-hysteresis-ignores-the-real-previous-level` | profile.py | 1 |
| `PM5-risk-level-ignored` | scoring.py | 1 |
| `PM6-promise-or-hold-cap-removed` | scoring.py | 1 |
| `PM7-dispute-cap-condition-inverted` | scoring.py | 1 |
| `PM8-dispute-no-collectible-drops-the-collectible-check` | profile.py | 1 |
| `PM9-reconciliation-pending-leaks-into-the-score` | facts.py | 1 |
| `PM10-draft-treated-as-active` | profile.py | 1 |
| `PM11-closed-invoice-treated-as-active` | profile.py | 1 |
| `PM12-threshold-boundary-shifted` | model.py | 1 |
| `PM13-event-emitted-on-score-only-change` | profile.py | 1 |
| `PM14-customer-batch-cap-removed` | runner_wiring.py | 1 |
| `PM15-input-hash-becomes-a-constant` | runner_wiring.py | 1 |
| `PM16-events-leak-across-organizations` | runner_wiring.py | 1 |
| `PM17-the-risk-level-read-is-silently-dropped` | runner_wiring.py | 1 |
| `PM18-steady-state-branch-disabled` | profile.py | 1 |
| `PM19-reasons-factor-format-drops-the-pts-prefix` | facts.py | 1 |

`PRIORITY_DOMAIN_COUNT = 21` invariants · `MUTATIONS = 19`.

