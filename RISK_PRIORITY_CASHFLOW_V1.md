# VERQIA — Risk / Priority / Cashflow V1.1

Références : Data Contract V1.3 (figé), Invariants V1.2, State Machines V1, Rule Engine V1.1, Collection Engine V1.1, Automation Engine V1.1, Engine Contracts V1.1.
Statut : **V1.1 — VALIDÉ.** RP1 à RP13 acceptées (RP4, RP5, RP6, RP12 amendées) ; **RP14 à RP22 VALIDÉES** ; **RP23 amendée et transférée à Collection Engine V1.2** (§3.4 bis, §12). Tous les amendements correspondants sont appliqués au contrat V1.3, au Rule Engine et à Engine Contracts.

Objet : définir **comment les trois projections se calculent** : données d'entrée, barèmes, fenêtres et unités, `input_hash`, moment où un `RESULT` est produit, reconstruction d'une projection périmée. Le document complète l'interface posée par Engine Contracts (EC-14).

**Spécification exécutable.** Les barèmes sont implémentés dans `reference_model/verqia_models.py` (arithmétique entière, sans horloge). Chaîne de vérification retenue :

```
modèle de référence → cas d'or (golden_cases.json) → tests de propriétés → implémentation SQL → tests différentiels
```

Les exemples chiffrés de ce document (§2.7, §3.6, §4.9) sont la sortie de ce modèle ; ses 25 tests (propriétés, cas d'or, conservation, promotion monotone) passent. Toute évolution d'un barème passe par le modèle de référence **puis** par ce document.

---

## 0. Position et principes

```
Sources de vérité ──→ Risk (client) ──RISK_CHANGED──→ Priority (facture)
        │                     │
        └─────────────────────┴──→ Cashflow (organisation)
```

| # | Principe |
|---|---|
| RP-A | **Grilles de points explicables**, pas de modèle statistique opaque : chaque point s'explique par une donnée observable. Aucun apprentissage automatique en V1. |
| RP-B | **Arithmétique entière** partout : points, pour-mille, points de base. **Chaque division est nommée** (`floor` ou demi vers le haut) ; deux exécutions donnent exactement le même résultat. |
| RP-C | **Fonction pure des sources** : une projection est entièrement reconstructible depuis les tables sources, à `as_of` donné. |
| RP-D | **Modèle versionné** (`model_version`) ; les paramètres vivent dans le code du modèle. Aucun n'est réglable par l'organisation en V1, sauf `critical_amount_minor`, qui existe déjà. |
| RP-E | **Un sens de dépendance** : Risk → Priority ; Cashflow lit le niveau de risque ; Risk ne lit ni Priority ni Cashflow. |
| RP-F | **Convergence par événements `RESULT`** : les moteurs de projection convergent entre eux par leurs événements ; seule la couche de **décision** (Rule Engine) applique la barrière de fraîcheur. |
| RP-G | **Jamais de donnée inventée** : un historique insuffisant contribue **zéro** au score de risque et est signalé (`confidence = LOW`). |
| RP-H | **`risk_level` est un indicateur d'attention métier**, pas une estimation statistique de défaut. |

---

## 1. Contrat commun des projections

### 1.1 Cycle d'un recalcul

```
déclencheur (événement de refresh, demande, rafraîchissement quotidien, filet de sécurité)
  → verrou consultatif (moteur, sujet) — un seul recalcul à la fois par sujet
  → lecture des sources (instantané stable)
  → entrées normalisées → input_hash
  → si input_hash = celui de la projection courante :  computed_at seul est mis à jour, fin
  → sinon : calcul → niveau (§1.3) → écriture de la projection courante
            → nouveau snapshot (clé : sujet, model_version, input_hash)
            → si le NIVEAU publié change : événement RESULT
```

### 1.2 `input_hash` et contenu d'un snapshot (RP6, RP14)

- **Définition** : SHA-256 (hexadécimal) du JSON canonique de `{model, org, subject, inputs}` où `inputs` sont les **entrées normalisées**. JSON canonique : clés triées, aucun espace, **entiers et chaînes uniquement** (aucun flottant).
- **Entrées normalisées** : les entrées **après** regroupement en tranches et plafonnement, c'est-à-dire les **points** de chaque facteur (jamais les valeurs brutes), plus le **niveau publié précédent** et, pour Priority, les indicateurs de plafond. Ainsi 17 ou 18 jours de retard, dans la même tranche, donnent le **même** hash.
- **Règle de contenu (RP14, normative)** : *tout ce qui est persisté dans un snapshot identifié par un `input_hash` est dérivé exclusivement des entrées normalisées et de la version du modèle.* Les valeurs brutes (17 ou 18 jours, 8 ou 9 factures soldées) **ne font pas partie du snapshot déterminant**. Elles s'affichent en lisant les faits **courants** à l'interface, jamais depuis le snapshot. Sinon `input_hash` égal ne garantirait plus « sortie égale ».
- **Métadonnées de provenance** : `computed_at` et `trigger_event_id` sont hors contenu déterminant (ils changent à chaque recalcul sans que le snapshot change).
- **Niveau précédent dans le hash** : c'est le niveau **publié** (celui de la ligne persistée), seul niveau reconstructible à l'identique. Sans lui, un même jeu de points donnant deux niveaux selon l'historique ferait échouer l'enregistrement du second changement (clé d'unicité du snapshot).
- **Propriété** : `input_hash` égal ⇒ sortie égale, y compris `factors` et `reasons`.
- **Portée de RP14 (normatif).** La règle du contenu déterminant s'applique à **Risk et Priority** : leur hash porte sur des entrées **normalisées**, leur snapshot est compact, les valeurs brutes se relisent dans les sources. **Cashflow fait l'inverse, volontairement** : son `input_hash` porte sur les entrées **brutes** du run (identifiants, montants, dates), parce qu'un run est un objet **complet et daté** dont `assumptions` et les lignes doivent être reproductibles à l'identique. Ne pas appliquer RP14 uniformément aux trois moteurs (Engine Contracts X17).

### 1.3 Niveaux : chaîne de calcul normative (RP15)

```
score
  → niveau brut                      (seuils)
  → hystérésis                       (sur le niveau PUBLIÉ précédent)
  → niveau stabilisé
  → plafonds métier                  (Priority seulement)
  → niveau publié                    (persisté ; devient le « niveau précédent » du calcul suivant)
```

**Hystérésis** : la montée est immédiate ; la descente exige `score + 3 <` seuil du niveau courant. Avec `niveau(x)` le niveau brut de `x` et `P` le niveau publié précédent :

```
si niveau(score) ≥ P :  stabilisé = niveau(score)
sinon                :  stabilisé = max( niveau(score), niveau(score + 3) )
```

**Pourquoi le niveau publié et non le niveau stabilisé avant plafond** : le niveau stabilisé avant plafond n'est pas persisté ; il ne pourrait pas être reconstruit. Le niveau publié l'est. Conséquence voulue : quand un plafond disparaît, le niveau remonte immédiatement au niveau brut (la montée est immédiate), sans lissage.

Exemple (seuil `HIGH` = 50), scores `44, 46, 49, 51, 48, 47, 49, 50, 46, 45, 44` : avec hystérésis `MMMHHHHHMMM` (2 changements) ; sans `MMMHMMMHMMM` (4).

### 1.4 Événements de rafraîchissement définitifs (RP7, appliqués au Rule Engine §2.3)

| Projection | `refresh_events` |
|---|---|
| `risk_profiles` | `INVOICE_ISSUED`, `INVOICE_OVERDUE`, `INVOICE_PARTIALLY_PAID`, `INVOICE_PAID`, `INVOICE_SETTLEMENT_REVERTED`, **`INVOICE_VOIDED`**, `PAYMENT_ALLOCATED`, `PAYMENT_ALLOCATION_REVERSED`, `PAYMENT_REVERSED`, `PROMISE_BROKEN`, `PROMISE_FULFILLED`, `RISK_RECALCULATION_REQUESTED` |
| `priority_items` | `INVOICE_ISSUED`, `INVOICE_DUE_SOON`, `INVOICE_DUE`, `INVOICE_OVERDUE`, `INVOICE_PARTIALLY_PAID`, `INVOICE_PAID`, `INVOICE_SETTLEMENT_REVERTED`, `INVOICE_VOIDED`, `INVOICE_CANCELLED`, `INVOICE_DISPUTED`, `INVOICE_DISPUTE_RESOLVED`, **`PAYMENT_CREATED`**, **`PAYMENT_ALLOCATED`**, **`PAYMENT_ALLOCATION_REVERSED`**, `PAYMENT_REVERSED`, `PROMISE_CREATED`, `PROMISE_BROKEN`, `PROMISE_FULFILLED`, `PROMISE_CANCELLED`, `COLLECTION_HOLD_PLACED`, `COLLECTION_HOLD_RELEASED`, **`COLLECTION_ACTION_EXECUTED`**, `RISK_CHANGED`, `PRIORITY_RECALCULATION_REQUESTED` |

Ajouts en gras par rapport aux listes provisoires : `INVOICE_VOIDED` réduit l'exposition d'un client ; un paiement partiel qui laisse la facture `PARTIALLY_PAID` n'émet **aucun** événement de facture (Invariants §3.2) mais change le restant dû, donc la priorité ; `COLLECTION_ACTION_EXECUTED` alimente le facteur « attention » ; `PAYMENT_CREATED` fait apparaître le signal de rapprochement (§3.4 bis).

### 1.5 Fraîcheur : rafraîchissement quotidien, filet de sécurité, reconstruction (RP9, RP22)

Les facteurs qui dépendent du **jour** (jours de retard, jours avant l'échéance) changent sans événement. Deux jobs distincts, chacun avec un objectif mesurable :

| Job | Cadence | Sujets | Objectif de service (SLO) |
|---|---|---|---|
| `ProjectionDailyRefresh` | chaque jour à 05:00, heure locale de l'organisation | tous les sujets **actifs** | **99 %** des projections actives ont un `computed_at` du jour local courant à 08:00 |
| `ProjectionSafetyNet` | toutes les 2 heures | sujets actifs dont `computed_at` a plus de 24 h (filet contre un événement perdu) | âge p99 d'une projection active ≤ 26 h ; **alerte** dès qu'une projection active dépasse 36 h |

Ces objectifs sont **mesurés** (âge des projections, §8) ; le délai réel dépend de la cadence et de la disponibilité des workers, il n'est pas une garantie absolue.
**Sujet actif** : un client qui a au moins une facture ouverte (Risk) ; une facture ouverte (Priority).

- **Reconstruction** (`RebuildProjection`, commande d'administration ou système) : recalcule un périmètre (un client, une organisation, tout) à `as_of` donné, par tranches étalées ; idempotente et déterministe (mêmes fonctions). Usages : défaut corrigé, reprise d'un handler `DEAD`, import.
- **Mise à niveau de modèle** (RP10) : opération d'administration avec **aperçu du nombre de changements de niveau** ; les `RESULT` qui en résultent portent `cause = MODEL_UPGRADE` et sont regroupés ; les snapshots gardent leur ancienne version.

### 1.6 Concurrence et transaction

Un recalcul lit en instantané stable et écrit dans la **même** transaction ; un verrou consultatif `(moteur, sujet)` sérialise deux recalculs du même sujet (le second lit le résultat du premier ; l'`input_hash` le rend sans effet). Une collision résiduelle est un `CONCURRENT_MODIFICATION` rejoué.

---

## 2. Risk Engine V1 (par client) — `risk-1.0`

### 2.1 Éligibilité

Un profil de risque existe si le client a au moins une facture **émise** (ni `DRAFT`, ni `CANCELLED`). Sinon, aucun profil : `customer.risk_level` vaut `UNKNOWN` pour le Rule Engine.

### 2.2 Entrées

| Symbole | Donnée | Fait |
|---|---|---|
| `D` | plus grand nombre de jours de retard parmi les factures ouvertes | `customer.max_days_overdue` |
| `n` | nombre de factures soldées sur les 12 derniers mois | `customer.settled_invoice_count_12m` |
| `L` | part des factures soldées en retard (`settled_on > due_date`), en **pour-mille** entier | `customer.late_payment_rate_12m` |
| `M` | délai moyen de paiement en jours (voir formule §5), plafonné entre 0 et 30 pour le calcul | `customer.avg_days_to_pay_12m` |
| `B` | promesses `BROKEN` sur 12 mois | `customer.broken_promises_12m` |
| `Eo` / `C` | exposition **en retard** en unité mineure / montant critique | `customer.overdue_exposure_minor`, `org_settings.critical_amount_minor` |
| `R` | paiements annulés sur 12 mois | `customer.reversed_payments_12m` |
| `T` | tendance du délai (jours) ; inconnue s'il y a moins de 2 factures dans l'une des deux fenêtres | `customer.delay_trend_90d` |

Fenêtres : « 12 mois » = les 12 mois calendaires précédant `as_of` (fuseau de l'organisation) ; « 90 jours » = 90 jours calendaires. **Échantillon minimal** : `n >= 3`, sinon `L` et `M` sont inconnus et contribuent 0 (RP-G).

### 2.3 Barème (points, total maximal 100)

| Facteur | Points | Règle (divisions entières = `floor`) |
|---|---:|---|
| **Retard actuel** | 0 à 30 | `D` = 0 → 0 · 1 à 7 → 5 · 8 à 15 → 12 · 16 à 30 → 20 · 31 à 60 → 26 · 61 ou plus → 30 |
| **Historique de retard** | 0 à 25 | si `n >= 3` : `⌊L × 15 / 1000⌋` **+** `⌊min(max(M,0), 30) × 10 / 30⌋` ; sinon 0 |
| **Promesses rompues** | 0 à 15 | `min(15, 5 × B)` |
| **Exposition en retard** | 0 à 15 | si `C > 0` : `min(15, ⌊Eo × 15 / C⌋)` ; sinon 0 |
| **Paiements annulés** | 0 à 10 | `min(10, 5 × R)` |
| **Tendance** | 0 à 5 | si `T > 0` : `min(5, ⌊T × 5 / 10⌋)` ; sinon 0 |

**Score** = somme (0 à 100). **Niveaux** : `LOW` 0–24 · `MEDIUM` 25–49 · `HIGH` 50–74 · `CRITICAL` 75–100, avec la chaîne du §1.3.

### 2.4 Sortie et contenu du snapshot (RP12, RP14)

- `risk_profiles` : `score`, `level`, `model_version` (`risk-1.0`), `factors`, `input_hash`, `computed_at`.
- **Entrées normalisées du hash** : `delay_pts`, `history_late_pts`, `history_delay_pts`, `broken_pts`, `exposure_pts`, `reversed_pts`, `trend_pts`, `confidence`, `previous_level`.
- **`factors`** : un objet `{"factors": [{"factor", "normalized_input", "points", "max"}, …], "meta": {"confidence"}}`. `normalized_input` est la valeur **normalisée** (`pts=20`, `late=11;delay=6`) ; **aucune valeur brute** n'y figure (RP14). `meta` ne contient que `confidence` (`LOW` si `n < 3`), pas de taille d'échantillon.
- **Valeurs brutes affichées** : l'interface les lit dans les faits courants ; elles ne sont pas stockées dans le snapshot.
- **`RISK_CHANGED`** (`RESULT`) : émis seulement si le niveau **publié** change, avec `from_level`, `to_level`, `score`.

### 2.5 Cas limites

| Cas | Traitement |
|---|---|
| Aucune facture émise | pas de profil ; `risk_level = UNKNOWN` |
| Historique insuffisant (`n < 3`) | facteur « historique » = 0 ; `confidence = LOW` |
| `C = 0` | facteur « exposition » = 0 |
| Client sans facture ouverte | `D = 0`, `Eo = 0` ; le score reflète l'historique |
| Facture importée | prise en compte comme les autres ; recalcul du lot par demandes regroupées par client |

### 2.6 Ce que le score n'est pas

Il n'estime pas une probabilité de défaut et n'utilise aucune donnée extérieure (RP-H). Il alimente la priorité, les conditions des règles et la pondération de la trésorerie.

### 2.7 Cas de référence (tests d'or)

`C = 1 000 000`.

| Cas | `D` | `n` | `L`‰ | `M` | `B` | `Eo` | `R` | `T` | Points (retard · hist. · promesses · expo. · annulés · tendance) | Score | Niveau |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| G1 nouveau client, 3 j de retard | 3 | 0 | — | — | 0 | 100 000 | 0 | — | 5 · 0 · 0 · 1 · 0 · 0 | **6** | LOW |
| G2 mauvais payeur chronique | 20 | 8 | 750 | 20 | 1 | 600 000 | 0 | 4 | 20 · 17 · 5 · 9 · 0 · 2 | **53** | HIGH |
| G3 situation critique | 70 | 10 | 900 | 40 | 3 | 2 000 000 | 2 | 10 | 30 · 23 · 15 · 15 · 10 · 5 | **98** | CRITICAL |
| G4 bon payeur, échéance non dépassée | 0 | 12 | 100 | 3 | 0 | 0 | 0 | 0 | 0 · 2 · 0 · 0 · 0 · 0 | **2** | LOW |
| G5 historique insuffisant, gros retard | 35 | 2 | — | — | 0 | 1 500 000 | 0 | — | 26 · 0 · 0 · 15 · 0 · 0 | **41** | MEDIUM |

Propriétés vérifiées : score maximal atteignable = **100** ; toujours dans [0, 100] ; **monotone** en chaque facteur ; **`input_hash` identique** pour 17 et 18 jours de retard (même tranche) et **distinct** pour 15 et 16 ; `factors` identique dans les deux cas.

---

## 3. Priority Engine V1 (par facture) — `prio-1.0`

### 3.1 Éligibilité et lien avec le risque

Une **facture ouverte** (`invoice.is_open`) reçoit une priorité ; une facture non ouverte a un élément au niveau `NONE`, score 0, motif `CLOSED` ; une facture `DRAFT` n'en a pas.
La priorité utilise le **niveau** de risque, **jamais son score** : elle n'a besoin que de `RISK_CHANGED`, qui ne se produit que sur changement de niveau publié. C'est ce qui limite fortement le nombre de recalculs.

### 3.2 Entrées

| Symbole | Donnée | Fait |
|---|---|---|
| `A` | montant restant dû | `invoice.outstanding_minor` |
| `C` | montant critique | `org_settings.critical_amount_minor` |
| `Dd` | jours de retard (0 si non échue) | `invoice.days_overdue` |
| `Dj` | jours avant l'échéance (négatif si échue) | `invoice.days_to_due` |
| — | niveau de risque du client | `customer.risk_level` (`UNKNOWN` si absent) |
| `S` | jours depuis la dernière action **réalisée** (`DONE`) sur la facture dans le cycle courant ; **sans aucune action, `S = Dd`** | `invoice.days_since_last_action` |
| — | promesse applicable, hold en vigueur, montant recouvrable | `invoice.active_promise`, `invoice.hold_active`, `invoice.collectible_minor` |

### 3.3 Barème (points ; domaine de `prio-1.0` : 0 à 95)

| Facteur | Points | Règle |
|---|---:|---|
| **Montant** | 0 à 30 | si `C > 0` : `min(30, ⌊A × 30 / C⌋)` ; sinon 0 |
| **Retard** | 0 à 30 | facture en retard : `Dd` 1 à 7 → 8 · 8 à 15 → 16 · 16 à 30 → 24 · 31 ou plus → 30 ; sinon 0 |
| **Risque du client** | 0 à 25 | `LOW` 0 · `MEDIUM` 8 · `HIGH` 17 · `CRITICAL` 25 · inconnu 5 |
| **Échéance imminente** | 0 à 5 | facture **non** en retard : `Dj` 0 à 3 → 5 · 4 à 7 → 2 ; sinon 0 |
| **Attention requise** | 0 à 10 | facture en retard : `S` ≥ 10 → 10 · 5 à 9 → 5 ; sinon 0 |

**Score** (`rank_score`) = somme, domaine **0 à 95** : « retard » et « échéance imminente » s'excluent.
**Niveaux** (RP16) : `NONE` 0–19 · `WATCH` 20–39 · `ACTION` 40–59 · `PRIORITY` 60–79 · **`CRITICAL` 80–95**. La borne 95 est propre à `prio-1.0` ; la colonne `rank_score` reste bornée à 100 par le contrat (borne de stockage, plus large que le domaine d'un modèle donné, pour permettre une version future).

### 3.4 Plafonds et chaîne de calcul (RP15)

La chaîne du §1.3 s'applique : score → niveau brut → **hystérésis sur le niveau publié précédent** → **plafond** → niveau publié.

| Situation | Plafond |
|---|---|
| promesse applicable **ou** hold en vigueur | `WATCH` |
| litige rendant le montant recouvrable nul (`collectible_minor = 0`) | `ACTION` |

Le score n'est pas modifié par un plafond ; seul le niveau l'est, et le motif figure dans `reasons`. **Le niveau publié (plafonné) devient le niveau précédent du calcul suivant**, jamais un niveau « avant plafond » non persisté. Exemple : niveau publié `CRITICAL`, score 85, une promesse apparaît → publié `WATCH` ; la promesse disparaît → le niveau précédent est `WATCH`, le niveau brut `CRITICAL` est atteint aussitôt (montée immédiate) → publié `CRITICAL`.
Un plafond ne relève jamais un niveau (vérifié).

### 3.4 bis Signal de rapprochement (RP23 amendée)

Trois notions à ne pas confondre :

| Notion | Sens | Utilisée par |
|---|---|---|
| **`OUTSTANDING`** | montant réellement dû selon la **source de vérité** (allocations confirmées) | Risk, Priority, Collection |
| **`UNALLOCATED`** | argent effectivement **reçu** mais pas encore affecté | Cashflow (réserve FIFO, CF3) |
| **`RECONCILIATION_PENDING`** | **problème opérationnel** : un paiement attend son affectation | interface ; barrière de Collection (V1.2) |

- Un paiement non alloué **ne signifie pas** que la facture est réglée : le moteur ne sait pas s'il concerne cette facture, une autre, ou une facture future. Plafonner la priorité reviendrait à transformer une **incertitude de rapprochement** en **conclusion métier**.
- **Définition** (alignée sur Collection V1.2, RN8) : `reconciliation_pending = invoice.reconciliation_pending`, c'est-à-dire au moins un paiement qualifiant (Q1 à Q5) dont la fenêtre de suspension n'est pas écoulée. Le signal affiché et la barrière appliquée sont la **même** information. `customer.unallocated_payment_minor` reste réservé à Cashflow (CF3).
- **Priority** : le signal fait partie des **entrées normalisées** (donc du hash et de `reasons`, RP14) sous forme d'un indicateur booléen ; il **ne modifie ni le `rank_score`, ni le niveau, ni les plafonds**. Le **montant** non alloué est une valeur brute : l'interface le lit dans les faits courants (« Paiement reçu non encore affecté : 100 000 »).
- **Risk** : aucun changement.
- **Cashflow** : CF3 inchangé.
- **Fin de fenêtre** : le fait change avec le temps, sans événement ; le rafraîchissement quotidien de 05:00 (`ProjectionDailyRefresh`) le rattrape.
- **Rafraîchissement** : `PAYMENT_CREATED` (nouveau paiement non alloué) est ajouté aux `refresh_events` de Priority ; `PAYMENT_ALLOCATED` et `PAYMENT_ALLOCATION_REVERSED` y figurent déjà.
- **Barrière de recouvrement** : elle est définie par Collection Engine V1.2, pas ici.

### 3.5 Sortie, contenu du snapshot et recalcul par lots (RP14, RP21)

- `priority_items` : `level`, `rank_score`, `reasons`, `model_version` (`prio-1.0`), `input_hash`, `computed_at`.
- **Entrées normalisées du hash** : `amount_pts`, `delay_pts`, `risk_pts`, `due_pts`, `attention_pts`, `previous_level`, `cap_promise_or_hold`, `cap_dispute`, `reconciliation_pending`. `reasons` est dérivé de ces seules entrées (facteurs normalisés, plafonds, signaux), sans valeur brute.
- **File de travail** : éléments de niveau ≠ `NONE`, triés par **niveau décroissant, puis `rank_score` décroissant, puis restant dû décroissant, puis échéance croissante, puis identifiant** (ordre total, stable).
- **`PRIORITY_CHANGED`** (`RESULT`) : seulement si le niveau publié change.
- **Recalcul en masse (RP21)** : `RISK_CHANGED` **ne recalcule pas** toutes les factures d'un client dans une transaction. Son handler émet une seule demande `PRIORITY_RECALCULATION_REQUESTED{scope: CUSTOMER, customer_id}` ; le Priority Engine traite les factures ouvertes du client **par lots reprenables** (200 par transaction, curseur par identifiant, demande de continuation), chaque lot étant idempotent (`input_hash`). Une panne ne rejoue que le lot concerné ; un état transitoirement hétérogène entre deux lots est accepté (convergence).

### 3.6 Cas de référence (tests d'or)

`C = 1 000 000`.

| Cas | Points (montant · retard · risque · échéance · attention) | Score | Niveau publié |
|---|---|---:|---|
| P1 1 200 000, 20 j de retard, risque `HIGH`, dernière action il y a 12 j | 30 · 24 · 17 · 0 · 10 | **81** | CRITICAL |
| P2 50 000, échéance dans 2 j, risque `LOW` | 1 · 0 · 0 · 5 · 0 | **6** | NONE |
| P3 400 000, 5 j de retard, `MEDIUM`, action il y a 2 j | 12 · 8 · 8 · 0 · 0 | **28** | WATCH |
| P4 700 000, 40 j de retard, risque inconnu, aucune action | 21 · 30 · 5 · 0 · 10 | **66** | PRIORITY |
| P5 comme P1, niveau précédent `CRITICAL`, promesse active | 30 · 24 · 17 · 0 · 10 | **81** | WATCH (plafond) |
| P6 comme P1, niveau précédent `CRITICAL`, litige sans recouvrable | 30 · 24 · 17 · 0 · 10 | **81** | ACTION (plafond) |
| P7 comme P1, avec un paiement non alloué du client | 30 · 24 · 17 · 0 · 10 | **81** | CRITICAL (inchangé) ; signal `RECONCILIATION_PENDING` dans `reasons`, hash différent |

Le tableau de bord compte simplement les éléments par niveau : « 157 factures → 43 à surveiller → 17 à traiter → 6 prioritaires → 2 critiques » est une requête sur `priority_items`.

---

## 4. Cashflow Engine V1 (par organisation) — `cash-1.0`

### 4.1 Ce qu'un calcul produit

Un **run** = un couple (horizon, scénario) à une date `as_of`, avec des **lignes** par période, catégorie et facture ou paiement source (contrat §9). Horizons : 7, 30, 60, 90, 180, 365 jours. Scénarios : `BASE`, `OPTIMISTIC`, `PESSIMISTIC`. Devise : celle de l'organisation.
**Fenêtre** : du **premier jour du mois** de `as_of` (fuseau de l'organisation) à `as_of + horizon`. **Périodes** : horizon 7 → jours ; 30, 60, 90 → semaines ISO ; 180, 365 → mois calendaires ; coupées aux bornes de la fenêtre.

### 4.2 Chaîne de conservation : paiement reçu → alloué ou non → restant dû → prévision (RP18, RP19)

C'est l'invariant financier central du moteur.

| # | Règle |
|---|---|
| **CF1** | **Un encaissement est constaté une seule fois** : `REALIZED` = paiements non `REVERSED` dont `value_date ∈ [début de fenêtre, as_of]`, **pour leur montant intégral**, alloués ou non. |
| **CF2** | **L'argent alloué réduit le restant dû** (`invoices.outstanding_minor`, source de vérité) : il n'est donc **jamais prévu** une seconde fois. |
| **CF3** | **L'argent reçu mais non alloué est *réservé*** : pour chaque client, le montant non alloué `U` (`Σ (amount_minor − allocated_minor)` des paiements `RECEIVED` ou `PARTIALLY_ALLOCATED`, **quelle que soit leur date**) est déduit des prévisions de ses factures ouvertes, dans l'ordre **FIFO** (échéance croissante, puis identifiant) ; la réserve réduit d'abord la part **recouvrable**, puis la part **contestée**. Une facture couverte entièrement par la réserve ne produit **aucune** ligne. |
| **CF4** | **Conservation** : pour une facture, la somme des montants de ses lignes ≤ son restant dû ; pour un client, `Σ lignes prévisionnelles + réserve ≤ Σ restants dus`. |
| **CF5** | **`REALIZED` est un constat historique, jamais une prévision** : il n'est jamais pondéré ni combiné à une probabilité ; les lignes `EXPECTED`, `PROBABLE`, `AT_RISK` sont exclusivement des prévisions. Le total affiché est `Σ REALIZED (poids 1) + Σ montants pondérés des prévisions`. |
| **CF6** | Un paiement `REVERSED` ne produit aucun `REALIZED` ni réserve ; ses allocations annulées rétablissent le restant dû dans la source de vérité. |

**Hypothèse de CF3** : le non-alloué d'un client est présumé destiné à ses factures ouvertes. Si c'était en réalité une avance pour une facture future, la prévision est **prudente** (sous-estimée), jamais surestimée. Exemple (§4.9, C9) : deux factures ouvertes de 300 000 et 500 000, 200 000 reçus non alloués → la prévision baisse de 200 000, exactement le montant déjà encaissé.

### 4.3 Catégories

| Catégorie | Contenu | Probabilité |
|---|---|---|
| `REALIZED` | encaissements (CF1) | 1, sans pondération (CF5) |
| `EXPECTED` | part recouvrable, après réserve, d'une facture **non échue**, à sa date attendue | selon risque |
| `PROBABLE` | facture échue (§4.5) ou montant promis | selon risque, retard, promesse |
| `AT_RISK` | part contestée ; facture échue de risque `CRITICAL` ou de plus de 60 jours de retard | faible ; **non datée** (dernière période, `undated = true`) |

### 4.4 Date de paiement attendue

| Grandeur | Règle |
|---|---|
| Délai du client `d` | `customer.avg_days_to_pay_12m` **plafonné entre 0 et 60** si `n >= 3` ; sinon le **délai moyen de l'organisation** (moyenne des factures soldées sur 12 mois si elles sont au moins 10), sinon 7 jours |
| Délai par scénario | `BASE` : `d` · `OPTIMISTIC` : `⌊d / 2⌋` · `PESSIMISTIC` : `d + ⌊d / 2⌋ + 7` |
| Date attendue `t` | `échéance + délai du scénario` |
| Facture échue dont `t` est déjà passée | `t = as_of + 7` (`BASE`), `+ 3` (`OPTIMISTIC`), `+ 14` (`PESSIMISTIC`) |
| Hors fenêtre | une ligne dont la date dépasse `as_of + horizon` n'est pas comptée dans ce run |

### 4.5 Probabilité et arrondis : ordre des opérations (RP20, normatif)

Points de base : 10 000 = 100 %. **Chaque opération est entière et ordonnée ainsi :**

```
1. base        = clamp( P_risque + ajustement_scénario , 1 000 , 10 000 )
2. p           = ⌊ base × décote_retard / 10 000 ⌋
3. p_contesté  = ⌊ p / 2 ⌋
4. p_promesse  = max( 3 000 , 8 000 − 1 500 × B )
5. pondéré     = ⌊ ( montant × p + 5 000 ) / 10 000 ⌋        (arrondi demi vers le haut)
```

| Niveau de risque | `LOW` | `MEDIUM` | `HIGH` | `CRITICAL` | inconnu |
|---|---:|---:|---:|---:|---:|
| `P_risque` | 9 700 | 9 000 | 7 500 | 5 000 | 8 500 |

| Scénario | `BASE` | `OPTIMISTIC` | `PESSIMISTIC` |
|---|---:|---:|---:|
| Ajustement | 0 | + 500 | − 1 500 |

| Jours de retard | 0–15 | 16–30 | 31–60 | 61–90 | plus de 90 |
|---|---:|---:|---:|---:|---:|
| Décote | 10 000 | 9 000 | 7 500 | 5 500 | 3 500 |

L'arrondi de l'étape 5 est **identique** à celui de la colonne générée `weighted_minor` du contrat (`round` sur un `numeric`, demi vers le haut pour les montants positifs) ; l'équivalence est vérifiée sur 20 000 cas aléatoires. Les divisions des délais (`⌊d / 2⌋`) et des moyennes (§5) sont aussi des `floor` nommés.

**Règles d'affectation**, pour chaque facture ouverte, **après la réserve de CF3** :
1. **Part contestée** (`min(montant contesté, restant dû)` après réserve) → `AT_RISK`, probabilité `p_contesté`, non datée.
2. **Promesse applicable** dont la date est dans la fenêtre → `PROBABLE` à la date promise, montant `min(montant promis, part recouvrable)`, probabilité `p_promesse`. Le reste suit la règle suivante.
3. **Facture non échue** → `EXPECTED` à `t`.
4. **Facture échue** de risque `CRITICAL` **ou** de plus de 60 jours de retard → `AT_RISK`, non datée.
5. **Autre facture échue** → `PROBABLE` à `t`.

### 4.6 `assumptions`, `input_hash`, explication

- **`assumptions`** : `model_version`, `as_of`, début de fenêtre, granularité, tableaux du §4.4 et §4.5, délai moyen de l'organisation utilisé, devise ; le run est reproductible sans lire le code.
- **`input_hash`** : SHA-256 du JSON canonique de `assumptions` et des entrées triées : pour chaque facture ouverte `(identifiant, restant dû, montant contesté, échéance, niveau de risque, délai du client)` ; pour chaque client `(identifiant, montant non alloué)` ; pour chaque promesse applicable `(identifiant, date, montant)` ; pour chaque paiement de la fenêtre `(identifiant, montant, date de valeur)`. `as_of` y figure : un nouveau jour donne un nouveau run. Les entrées du run sont **brutes** (le run est daté et complet), donc la règle RP14 y est vérifiée par construction : tout ce que le run persiste est dérivé de ces entrées.
- **Explication de chaque ligne** : `basis` (`DUE_DATE_PLUS_DELAY`, `PROMISE`, `DISPUTED_PORTION`, `OVERDUE_RISK`), `delay_days`, `delay_source` (`CUSTOMER` ou `ORG`), niveau de risque, décomposition de la probabilité (base, scénario, décote), `undated`, montant réservé au titre de CF3.

### 4.7 Un seul run courant (RP17)

Le contrat §9.1 porte déjà l'index unique partiel `(organization_id, horizon_days, scenario) WHERE is_current`, la contrainte `is_current ⇒ COMPLETED` et l'unicité d'un run `RUNNING` par triplet. Ce qui manquait était l'**énoncé dans le contrat d'interface** et la règle de promotion. `RunCashflow` garantit :

1. Pour chaque `(organisation, horizon, scénario)`, **au plus un run `is_current`** (index unique partiel).
2. La promotion est **atomique** : sous verrou consultatif sur le triplet, dans une seule transaction, l'ancien run est désactivé puis le nouveau activé.
3. La promotion est **monotone** : un run ne devient courant que si son `(as_of, computed_at)` est **plus récent** que celui du run courant. Un run retardataire, terminé après un run plus récent, reste `COMPLETED` non courant.
4. Une violation d'unicité résiduelle est un `CONCURRENT_MODIFICATION` rejoué ; la règle de monotonie tranche alors.
5. Un run `FAILED` n'est jamais courant.

### 4.8 Cadence, événements, péremption

| Élément | Règle |
|---|---|
| Runs **planifiés** chaque jour par organisation (05:00 local) | `BASE` sur les 6 horizons ; `OPTIMISTIC` et `PESSIMISTIC` sur 30 et 90 jours : **10 runs** |
| Runs **déclenchés par événement** | `BASE` sur 30 et 90 jours, via `CASHFLOW_RECALCULATION_REQUESTED` **regroupées sur 5 minutes** |
| Runs **à la demande** | tout horizon et scénario, avec limite de fréquence |
| Même `input_hash` que le run courant | run existant renvoyé (`REPLAY`) |
| `CASHFLOW_UPDATED` (`RESULT`) | quand un run devient courant **avec un `input_hash` différent** du précédent |
| Péremption | un run courant de plus de 26 h déclenche une alerte ; l'interface affiche sa date de calcul |

### 4.9 Exemples chiffrés (tests d'or)

Facture de **500 000**, échéance **2026-10-15**, client `MEDIUM`, délai moyen 6 jours, horizon 30 jours, aucun litige ni promesse ni non-alloué.

| `as_of` | Scénario | Catégorie | Date | Probabilité | Pondéré |
|---|---|---|---|---:|---:|
| 2026-10-01 | `BASE` | `EXPECTED` | 2026-10-21 | 0,9000 | 450 000 |
| 2026-10-01 | `OPTIMISTIC` | `EXPECTED` | 2026-10-18 | 0,9500 | 475 000 |
| 2026-10-01 | `PESSIMISTIC` | `EXPECTED` | 2026-10-31 | 0,7500 | 375 000 |
| 2026-10-20 (5 j de retard) | `BASE` | `PROBABLE` | 2026-10-21 | 0,9000 | 450 000 |
| 2026-10-20 | `OPTIMISTIC` | `PROBABLE` | 2026-10-23 (date attendue passée, `+ 3`) | 0,9500 | 475 000 |
| 2026-10-20 | `PESSIMISTIC` | `PROBABLE` | 2026-10-31 | 0,7500 | 375 000 |

**C7 · litige et promesse** (`as_of` 2026-10-20, `BASE`, litige de 200 000, promesse de 150 000 au 2026-10-25, une promesse rompue) : somme des montants = 500 000.

| Ligne | Catégorie | Montant | Date | Probabilité | Pondéré |
|---|---|---:|---|---:|---:|
| part contestée | `AT_RISK` | 200 000 | non datée | 0,4500 | 90 000 |
| promesse | `PROBABLE` | 150 000 | 2026-10-25 | 0,6500 | 97 500 |
| reste | `PROBABLE` | 150 000 | 2026-10-21 | 0,9000 | 135 000 |

**C8 · 66 jours de retard, risque `HIGH`** : `AT_RISK`, 500 000, non datée, probabilité 0,4125, pondéré **206 250**.

**C9 · non-alloué (CF3)** — `as_of` 2026-10-20, `BASE`, client `MEDIUM` (délai 6 jours), factures `I1` 300 000 (échéance 2026-10-10) et `I2` 500 000 (échéance 2026-10-15), **200 000 reçus non alloués**. Sans réserve : 800 000 prévus. Avec réserve : **600 000** (réserve de 200 000 prise sur `I1`, la plus ancienne).

| Facture | Catégorie | Montant | Date | Probabilité | Pondéré |
|---|---|---:|---|---:|---:|
| `I1` (100 000 après réserve) | `PROBABLE` | 100 000 | 2026-10-27 (`+ 7`) | 0,9000 | 90 000 |
| `I2` | `PROBABLE` | 500 000 | 2026-10-21 | 0,9000 | 450 000 |

**C10 · le non-alloué couvre tout** : facture de 300 000, 400 000 non alloués → **aucune ligne prévisionnelle** (réserve de 300 000).

### 4.10 Limites de la V1

Pas de saisonnalité, pas de corrélation entre clients, pas de dépenses (uniquement les encaissements attendus), pas de devises multiples. La précision se mesure a posteriori (§8).

---

## 5. Faits ajoutés ou précisés dans le Rule Engine (RP8, appliqué)

| Fait | Définition |
|---|---|
| `customer.settled_invoice_count_12m` | nombre de factures soldées (`settled_on`) sur les 12 derniers mois |
| `customer.avg_days_to_pay_12m` | somme `S` de `settled_on − due_date` sur `n` factures ; valeur = `⌊(2 × S + n) / (2 × n)⌋` (demi vers le haut, valeurs négatives permises) ; inconnue si `n < 3` |
| `customer.late_payment_rate_12m` | **entier en pour-mille** : `⌊1 000 × (factures soldées en retard) / n⌋` ; inconnu si `n < 3` |
| `customer.reversed_payments_12m` | nombre de paiements annulés sur 12 mois (`payment_reversals.reversed_at`) |
| `customer.delay_trend_90d` | délai moyen (formule ci-dessus) des factures soldées sur les 90 derniers jours moins celui des 90 jours précédents ; inconnu s'il y a moins de 2 factures dans l'une des fenêtres |
| `customer.unallocated_payment_minor` (RP19) | `Σ (amount_minor − allocated_minor)` des paiements `RECEIVED` ou `PARTIALLY_ALLOCATED` du client |
| `invoice.days_since_last_action` | jours depuis la dernière action `DONE` de la facture dans le cycle courant ; absent s'il n'y en a pas (le modèle de priorité prend alors `Dd`) |

---

## 6. Contrats d'interface (précisions d'EC-14)

| Contrat | Entrée | Sortie | Erreurs | Idempotence | Transaction |
|---|---|---|---|---|---|
| `RecomputeRisk` | client, `as_of`, déclencheur | `{computed_at, level, changed, snapshot_id?}` | `RISK_MODEL_UNKNOWN`, `CONCURRENT_MODIFICATION` | `input_hash` (niveau précédent inclus) | une par client ; instantané stable ; verrou consultatif `(risk, client)` |
| `RecomputePriority` | facture, ou client (portée `CUSTOMER`) + curseur | idem, par facture ; continuation éventuelle | `PRIORITY_MODEL_UNKNOWN`, `CONCURRENT_MODIFICATION` | `input_hash` | **une par lot de 200 factures** (RP21) ; verrou `(priority, client)` |
| `RunCashflow` | organisation, horizon, scénario, `as_of` | `{run_id, status, is_current}` ou `REPLAY` | `CASHFLOW_MODEL_UNKNOWN`, `CASHFLOW_HORIZON_INVALID`, `CASHFLOW_SCENARIO_INVALID`, `CASHFLOW_RUN_CONFLICT`, `CASHFLOW_INPUT_INCONSISTENT` | `input_hash` ; au plus un `RUNNING` **et un `is_current`** par triplet ; promotion monotone (§4.7) | lignes et promotion dans une transaction ; verrou consultatif `(organisation, horizon, scénario)` |
| `RebuildProjection` | périmètre, `as_of` | nombre de projections recalculées | `INSUFFICIENT_ROLE` | recalcul idempotent | par tranches |

---

## 7. Testable

Chaîne : **modèle de référence → cas d'or → tests de propriétés → implémentation SQL → tests différentiels.**

| Famille | Contenu |
|---|---|
| **Cas d'or** | `golden_cases.json` : 5 cas de risque, 7 de priorité, 10 de trésorerie ; le modèle doit **reproduire le fichier à l'identique** |
| **Propriétés (Risk)** | score dans [0, 100], maximum = 100 ; monotonie de chaque facteur ; historique insuffisant ⇒ 0 ; **hash stable dans une tranche, distinct entre tranches, sensible au niveau précédent** ; **contenu du snapshot inchangé pour deux valeurs brutes d'une même tranche** (RP14) |
| **Propriétés (Priority)** | score dans [0, 95] ; plafonds appliqués après stabilisation ; un plafond ne relève jamais un niveau ; le niveau publié est la référence suivante ; le hash inclut niveau précédent et plafonds Le signal de rapprochement ne change **ni score ni niveau ni plafond**, mais change le hash. |
| **Propriétés (Cashflow)** | conservation par facture **et par client** (CF4) ; réserve ≤ non-alloué et ≤ restants dus ; **aucune ligne si le non-alloué couvre tout** ; jamais de ligne `REALIZED` dans une prévision ; probabilités dans [0, 1] ; `pondéré` = arrondi décimal demi-haut (20 000 cas) ; déterminisme ; dates dans la fenêtre |
| **Promotion d'un run** | monotone : un run retardataire ne remplace pas un plus récent ; un seul courant par triplet |
| **Hystérésis** | séquences oscillant autour d'un seuil : jamais plus de changements qu'en l'absence d'hystérésis (200 séquences aléatoires) |
| **SQL (à venir)** | chaque fait SQL et chaque score comparés au modèle de référence sur données aléatoires (test différentiel) |
| **Rejeu / reconstruction** | `RebuildProjection` reproduit exactement les projections courantes |
| **Fraîcheur** | événement de rafraîchissement supprimé : le filet de sécurité répare ; SLO mesurés |
| **Cascade** | `RISK_CHANGED` → demande de portée client → lots idempotents ; pas de cycle Risk ↔ Priority |
| **Mise à niveau de modèle** | aperçu du nombre de changements de niveau ; `cause = MODEL_UPGRADE` regroupé |
| **Volumétrie** | 5 000 clients et 50 000 factures ; **un client à 50 000 factures ouvertes** (lots) ; un run de trésorerie |

---

## 8. Observable

| Signal | Contenu |
|---|---|
| **Répartition** | clients par niveau de risque ; éléments par niveau de priorité (le « funnel ») |
| **Activité** | `RISK_CHANGED` et `PRIORITY_CHANGED` par heure ; **taux de recalculs sans effet** (`input_hash` inchangé) |
| **Fraîcheur (SLO)** | âge des projections actives (médiane, p95, p99) ; part des projections actives calculées le jour local courant à 08:00 ; projections actives de plus de 36 h ; runs de trésorerie de plus de 26 h |
| **Qualité de données** | part des profils à `confidence = LOW` ; part de faits inconnus ; part des lignes de trésorerie fondées sur le délai de l'organisation |
| **Conservation** | montant total réservé au titre du non-alloué (CF3) ; nombre de clients avec non-alloué ancien (signale un défaut de rapprochement) |
| **Performance** | durée d'un recalcul ; taille et retard des lots |
| **Précision de la trésorerie** | écart entre l'encaissement prévu sur une période et le réalisé constaté ensuite (à la demande, depuis les runs conservés) |
| **Alertes** | projection périmée ; hausse anormale des changements de niveau ; échec répété d'un recalcul |

---

## 9. Volumétrie et rétention

- `risk_snapshots`, `priority_snapshots` : une ligne par **changement d'entrées normalisées** (pas par jour) ; rétention de 13 mois (contrat §18).
- `cashflow_runs`, `cashflow_lines` : 10 runs par jour et par organisation (environ 5 000 lignes par jour pour 500 factures ouvertes). **RP12** : conservation opérationnelle de 13 mois pour les runs non courants, **sauf le dernier run de chaque mois pour les horizons 30 et 90 jours**, conservé sans limite pour comparer prévu et réalisé. Archive, pas suppression.

---

## 10. Ce que reçoivent les passes suivantes

- **Matrice de tests globale** : les familles du §7, `golden_cases.json` et le modèle de référence comme oracle.
- **Collection Engine V1.2** : la barrière de recouvrement pour le non-alloué (RP23), à partir des faits `invoice.reconciliation_pending` et `invoice.reconciliation_pending_minor` (validée ; le signal de Priority est aligné sur le même fait).
- **Architecture technique** : verrous consultatifs par sujet et par triplet de trésorerie ; jobs `ProjectionDailyRefresh` et `ProjectionSafetyNet` ; recalcul par lots de 200 ; index des faits comportementaux (12 mois glissants) et du non-alloué (index partiel `payments` existant) à vérifier au banc d'essai.
- **UX** : `factors`, `reasons`, `explanation` ; file de travail à ordre total ; funnel ; âge d'une projection ; **file « paiements à affecter »** et son montant.

---

## 11. Limites connues

1. Aucun modèle statistique : les seuils sont des choix métier, à recalibrer avec des données réelles.
2. Le risque ignore les litiges (un litige n'est pas un signal de défaut).
3. La trésorerie ne modélise que les **encaissements** attendus.
4. Aucun paramètre de modèle n'est réglable par l'organisation en V1.
5. **Le non-alloué n'est déduit que dans la trésorerie** (CF3). Le risque, la priorité et le recouvrement calculent sur le restant dû **alloué** : un client qui a payé sans que le paiement soit alloué peut apparaître en retard. La priorité l'**explique** par le signal `RECONCILIATION_PENDING` (§3.4 bis) sans changer son score ; **la barrière de recouvrement correspondante est à définir dans Collection Engine V1.2** (RP23).

---

## 12. Décisions

### Statut de RP1 à RP13

| # | Verdict de la revue | Traitement |
|---|---|---|
| RP1 | acceptée | — |
| RP2 | acceptée | — |
| RP3 | acceptée, correction mineure du hash | RP14 |
| RP4 | acceptée avec clarification (plafond, hystérésis) | RP15, RP16 |
| RP5 | **à corriger** (conservation, non-alloué) | RP17 à RP20 |
| RP6 | **correction nécessaire** (hash et valeurs affichées) | RP14 |
| RP7 | acceptée | **appliquée** au Rule Engine §2.3 |
| RP8 | acceptée | **appliquée** au Rule Engine §2.2 |
| RP9 | acceptée | précisée par RP22 |
| RP10 | acceptée | — |
| RP11 | acceptée après correction du modèle de trésorerie | RP17 à RP20 |
| RP12 | acceptée après correction du contrat de snapshot | RP14 (structure de `factors`) |
| RP13 | acceptée | — |

### Amendements RP14 à RP22 : **VALIDÉS** ; RP23 : **amendée et transférée**

| # | Verdict | Objet |
|---|---|---|
| **RP14** | ✅ validé | Un snapshot identifié par `input_hash` ne contient que des sorties dérivées des entrées normalisées ; `factors.input` devient `normalized_input` ; `meta` ne garde que `confidence` ; aucune valeur brute stockée (§1.2, §2.4, §3.5). **Portée normative** : la règle vaut pour Risk et Priority ; Cashflow hache des entrées **brutes** (§1.2) |
| **RP15** | ✅ validé | Priority : hystérésis sur le niveau **publié** ; plafonds après stabilisation ; le niveau publié devient la référence suivante (§1.3, §3.4) |
| **RP16** | ✅ validé | `prio-1.0` : domaine 0–95, `CRITICAL` 80–95 ; borne de stockage du contrat 100 (§3.3) |
| **RP17** | ✅ validé | Un seul run `CURRENT` par `(organisation, horizon, scénario)` : index unique **déjà au contrat**, promotion atomique sous verrou, monotone (§4.7, §6) |
| **RP18** | ✅ validé | `REALIZED` = encaissements reçus, jamais prévisionnel ; les autres catégories = prévisions (§4.2, CF5) |
| **RP19** | ✅ validé | Non-alloué réservé en FIFO, jamais reprévu ; fait `customer.unallocated_payment_minor` (§4.2, §5) |
| **RP20** | ✅ validé | Divisions et arrondis de Cashflow définis ; équivalence avec la colonne générée du contrat (§4.5) |
| **RP21** | ✅ validé | `RISK_CHANGED` → demande de portée client → lots idempotents reprenables (§3.5, §6) |
| **RP22** | ✅ validé | `ProjectionDailyRefresh` et `ProjectionSafetyNet` avec cadence et SLO mesurables (§1.5, §8) |
| **RP23** | ✏️ **amendée** | *Voir ci-dessous.* Le plafond `WATCH` proposé initialement est **abandonné** ; la barrière de recouvrement est **transférée à Collection Engine V1.2** |

**RP23 amendée.** Un paiement non alloué ne modifie ni le score de risque ni le `rank_score`, et ne signifie pas que la facture est réglée. Cashflow continue d'appliquer CF3 (réserve FIFO). Priority expose un **signal de rapprochement** (`RECONCILIATION_PENDING`) sans plafond ni effet sur le score (§3.4 bis). Collection Engine V1.2 définit la barrière de décision qui empêche une relance inappropriée lorsqu'un paiement potentiellement applicable reste non alloué : c'est une décision de **recouvrement** (« a-t-on le droit de contacter ce client dans cette situation ? »), pas de scoring.

### Amendements appliqués aux documents figés

| Document | Amendement | État |
|---|---|---|
| Rule Engine §2.2, §2.3 | faits ajoutés ; listes `refresh_events` définitives (avec `PAYMENT_CREATED` pour le signal de rapprochement) | ✅ appliqué |
| Contrat §7.1, §7.3 | `factors` en objet `{factors[], meta}` avec `normalized_input` ; `reasons` normalisé ; définition et portée de `input_hash` | ✅ appliqué |
| Contrat §9.1, §9.2 | note sur `weighted_minor` (demi-haut) ; un seul run courant et promotion monotone | ✅ appliqué |
| Contrat §18 | rétention des runs de trésorerie (RP12) | ✅ appliqué |
| Engine Contracts EC-03, EC-14 | jobs `ProjectionDailyRefresh` et `ProjectionSafetyNet` ; `RunCashflow` ; `RecomputePriority` par lots ; invariant X17 (portée du hash) | ✅ appliqué |
| Collection Engine V1.2 | barrière de recouvrement pour le non-alloué (RP23) | ⏳ à concevoir |
