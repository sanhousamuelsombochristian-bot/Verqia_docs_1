# VERQIA — Priority Domain V1 (`prio-1.0`) — PROPOSITION, non gelée

Transcrit depuis `RISK_PRIORITY_CASHFLOW_V1.md` §0, §1, §3 (frozen) et `reference_model/verqia_models.py`
(`prio_points`/`prio_score`/`prio_publish`/`prio_evaluate`, déjà exécutables et testés — `TestPriority`,
`golden_cases.json['priority']`, cas P1 à P7). Même méthode que `RISK_DOMAIN_V1.md` : RDx devient PDx, DV2 devient DV3.
Aucune formule n'est réinventée ; ce document ne fait que déterminer la FRONTIÈRE Domain/Application et raccorder le
modèle gelé au Domain V1 (invoices, gelé) et au Risk Domain (gelé).

---

## PD1 — Frontière du Domain (RD1.1, reprise à l'identique)

### PD1.1 Ce que le Domain ne connaît JAMAIS

Liste fermée, identique en nature à celle de Risk (RD1.1) : `input_hash` comme mécanisme de persistance,
PostgreSQL, les verrous, le planificateur, la catégorie d'événement `REQUEST`, `PRIORITY_CHANGED` comme effet
technique, le rejeu, le cache, `computed_at`, `priority_snapshots` comme table, `InvoiceRepository`,
`CustomerRepository`, `CollectionRepository`. Le Domain ne connaît que des faits, des paramètres, l'état publié
précédent et `as_of`.

---

## PD2 — Entrées reçues par le Domain

### PD2.1 Rappel du modèle gelé (§3.2, RISK_PRIORITY_CASHFLOW_V1.md)

| Symbole | Donnée | Fait source (Rule Engine, déjà nommé) |
|---|---|---|
| `A` | montant restant dû | `invoice.outstanding_minor` |
| `C` | montant critique | `org_settings.critical_amount_minor` |
| `Dd` | jours de retard (0 si non échue) | `invoice.days_overdue` |
| `Dj` | jours avant l'échéance (négatif si échue) | `invoice.days_to_due` |
| — | niveau de risque du client | `customer.risk_level` (`UNKNOWN` si absent) |
| `S` | jours depuis la dernière action `DONE` sur la facture dans le cycle courant ; sans action, `S = Dd` | `invoice.days_since_last_action` |
| — | promesse applicable | `invoice.active_promise` |
| — | hold en vigueur | `invoice.hold_active` |
| — | montant recouvrable | `invoice.collectible_minor` |
| — | signal de rapprochement | `invoice.reconciliation_pending` (RP23 amendée, Collection Engine V1.2 §2.2) |

### PD2.2 Correspondance avec ce qui est déjà gelé (PD-clé de cette spécification)

| Entrée | Vient de | Statut |
|---|---|---|
| `A`, `Dd` (`is_late`+`days_late`), `Dj` (`days_to_due`), `collectible_minor`, `has_open_dispute` | `invoices.InvoiceFacts` (Domain V1 tranche 1, **gelé**) | déjà disponible, aucune nouvelle règle |
| niveau de risque | `risk.RiskLevel` (Risk Domain V1, **gelé**) — la requête **existe déjà**, générée (`verqia/risk/contracts/queries.py`), consommateurs à élargir | déjà disponible, réutilisation pure (RP-E : Risk → Priority, jamais l'inverse) |
| `active_promise` | `promises` (structure existante, Domain non encore écrit — même statut que `PromiseRiskFacts` pour Risk, § DV2-5) | fournisseur potentiellement STUB, § DV3-1 |
| `hold_active`, `S` (`days_since_last_action`) | `collection_holds`, `collection_actions` (module `collection`, **pas encore construit** — tranche suivante dans l'ordre déjà arrêté) | aucun fournisseur possible avant Collection, § DV3-2/DV3-3 |
| `reconciliation_pending` | `invoice.reconciliation_pending` (Collection Engine V1.2 §2.2, dépend de la logique de qualification des paiements Q1-Q5 — tranche **Réconciliation**, encore après Collection) | aucun fournisseur possible avant Réconciliation, § DV3-4 |

Le Risk Domain n'a jamais eu ce problème : ses cinq lectures client/facture existaient toutes déjà (tranche 1) ou
appartenaient à un module immédiatement adjacent (`promises`). Priority est la **première** tranche à dépendre d'un
module qui n'existe pas encore et n'existera pas avant plusieurs tranches (`collection`, puis `reconciliation`).
C'est le point d'arbitrage central de cette spécification (§ DV3).

### PD2.3 Forme reçue par le Domain (arbitrée — corrections A/B/C appliquées)

```
PriorityInput = {
  priority_parameters: PriorityParameters,          # { critical_amount_minor } — même origine qu'en Risk (organizations.OrgSettings)
  invoice: InvoiceFacts,                              # gelé, tranche 1 : outstanding_minor, days_late, is_late, days_to_due, collectible_minor, has_open_dispute, is_open
  risk_level: str | None,                             # 'LOW'|'MEDIUM'|'HIGH'|'CRITICAL'|None ('UNKNOWN' côté Rule Engine == None ici)
  days_since_last_action: int | None,                 # None ⇒ le Domain applique S = Dd lui-même (§3.2, littéral)
  active_promise: bool,                               # provenance : voir note ci-dessous
  hold_active: bool,                                  # provenance : voir note ci-dessous, § DV3-2
  reconciliation_pending: bool,                       # provenance : voir note ci-dessous, § DV3-4
  previous: PublishedPriority | None,                 # § PD2.5
  as_of: datetime,
}
```

**Correction A (arbitrée)** : `is_open` retiré de `PriorityInput` comme champ séparé. `InvoiceFacts` porte déjà
`is_open` (gelé, tranche 1) ; garder les deux aurait ouvert la possibilité de deux vérités contradictoires
(`is_open=True` reçu séparément pendant que `invoice.is_open=False`). Le Domain lit `invoice.is_open` directement
(PD3).

**Correction B (arbitrée)** : pas de type dédié `RiskLevel` pour la VALEUR du niveau — vérifié : `RiskLevel` n'existe
aujourd'hui que comme nom de la classe `Query` (`verqia/risk/contracts/queries.py`), pas comme type de valeur ; et le
Domain Risk lui-même représente ses niveaux en `str` nu (`verqia/risk/domain/model.py : LEVELS = ('LOW', 'MEDIUM',
'HIGH', 'CRITICAL')`, `NormalizedRiskInputs.previous_level: str | None`). Créer un type `RiskLevel` dédié pour
Priority introduirait une incohérence avec le précédent déjà gelé, en plus d'une collision de nom avec la classe
`Query`. `risk_level: str | None` est conservé, avec une garde défensive explicite à l'écriture du Domain : toute
valeur reçue qui n'est ni l'une des quatre chaînes connues ni `None` est un `PreconditionViolated` (l'Application
construit l'état, comme pour toutes les autres entrées du Domain V1).

**Correction C (arbitrée)** : `active_promise`, `hold_active`, `reconciliation_pending` restent des `bool` nus dans
`PriorityInput` (le Domain ne doit jamais savoir de quel module vient une valeur — RD1.1), mais leur **provenance
Application** est documentée normativement, pas laissée implicite : chacun est construit par un **adaptateur de
provenance explicitement nommé** (§ DV3-1/DV3-2/DV3-4), jamais par une valeur en dur anonyme qui ressemblerait à une
vraie réponse métier.

`priority_parameters` ne porte que `critical_amount_minor` — pas de `timezone` : contrairement à Risk (`T`,
tendance sur 90 jours, calculée par le Domain), Priority ne calcule aucune fenêtre temporelle lui-même ; `Dd`/`Dj`
sont déjà résolus par `InvoiceFacts` (tranche 1, qui connaît déjà `business_date`/le fuseau). Pas de raison
d'anticiper un besoin que le barème §3.3 ne montre nulle part (même principe que RD2.6 pour Risk).

### PD2.4 Bornage et assemblage : qui fait quoi

Comme pour Risk (RD2.4), l'Application résout tout ce qui est temporel ou multi-lecture AVANT d'appeler le Domain :
`Dd`/`Dj` viennent déjà résolus d'`InvoiceFacts` ; `risk_level` d'une lecture `risk.RiskLevel` ; `active_promise`,
`hold_active`, `reconciliation_pending` de lectures booléennes déjà bornées par construction (« au moins une ligne
qualifiante en ce moment », pas une liste à agréger). Le Domain n'agrège **aucune** liste ici, à la différence de
Risk (RD2.2) : chaque entrée de PD2.3 est déjà une valeur ponctuelle. La seule dérivation que le Domain fait
lui-même est `S = Dd` quand `days_since_last_action` est absent (§3.2, littéral).

### PD2.5 `PublishedPriority` — l'ancien état publié

```
PublishedPriority = {
  level: str,                                # niveau publié précédent (PD6, PD7)
  normalized_inputs: PriorityNormalizedInputs,  # PD9 — PAS un input_hash
}
```

### PD2.6 Types nouveaux introduits par cette tranche

```
PriorityParameters = { critical_amount_minor: int }                       # module organizations — sous-ensemble de RiskParameters (RD2.6)
```

Aucun autre type de fait nouveau n'est requis pour les entrées déjà gelées (PD2.2) : `risk_level` vient d'une
requête existante rendant une valeur scalaire (pas de type dédié, même raisonnement que RD2.3 pour
`EverIssuedOfCustomer` côté Risk). Les trois entrées sans fournisseur possible (`active_promise`, `hold_active`,
`reconciliation_pending`, `days_since_last_action`) restent des `bool`/`int | None` nus : leur **type de fait
publié** (par `promises`, `collection`, `reconciliation`) sera défini au moment où CES tranches seront spécifiées,
pas ici — Priority ne fait qu'en déclarer la **forme attendue** (§ DV3).

---

## PD3 — Éligibilité (§3.1, littéral)

- `invoice.is_open` → un élément de priorité existe.
- Facture non ouverte (soldée, annulée, void) → un élément existe **quand même**, niveau `NONE`, score 0, motif
  `CLOSED` (à la différence de Risk où l'absence d'éligibilité = absence de ligne).
- Facture `DRAFT` → aucun élément (elle n'existe pas encore pour Priority).

**Différence structurelle avec Risk (RD3), à noter explicitement** : Risk a deux états — profil ou pas de profil.
Priority en a **trois** — élément actif, élément `NONE`/`CLOSED`, ou absence totale (`DRAFT`). Le Domain doit donc
distinguer « facture non ouverte » (écrit `NONE`/`CLOSED`) de « facture `DRAFT` » (n'écrit rien) — ce n'est **pas**
la même condition que l'éligibilité de Risk (`has_ever_issued`).

---

## PD4 — Barème (§3.3, littéral, transcrit de `prio_points`)

| Facteur | Points | Règle |
|---|---:|---|
| Montant | 0–30 | si `C > 0` : `min(30, ⌊A × 30 / C⌋)` ; sinon 0 |
| Retard | 0–30 | facture en retard (`Dd` via `is_late`) : `1–7→8 · 8–15→16 · 16–30→24 · ≥31→30` ; sinon 0 |
| Risque du client | 0–25 | `LOW=0 · MEDIUM=8 · HIGH=17 · CRITICAL=25 · inconnu=5` |
| Échéance imminente | 0–5 | facture **non** en retard : `Dj` `0–3→5 · 4–7→2` ; sinon 0 |
| Attention requise | 0–10 | facture en retard : `S≥10→10 · 5–9→5` ; sinon 0 |

« Retard » et « échéance imminente » s'excluent (une facture est en retard ou ne l'est pas, jamais les deux).

---

## PD5 — Score (§3.3, littéral)

`rank_score = amount_pts + delay_pts + risk_pts + due_pts + attention_pts`, domaine **[0, 95]** (30+30+25+5+10=100
en théorie, mais « retard » et « échéance imminente » s'excluent : le maximum réel est `30+30+25+0+10=95`). La
colonne de stockage `rank_score` tolère `[0,100]` (marge pour un futur modèle), le Domain `prio-1.0` ne produit
jamais plus de 95.

---

## PD6 — Niveaux (§3.3)

`NONE 0–19 · WATCH 20–39 · ACTION 40–59 · PRIORITY 60–79 · CRITICAL 80–95`, chaîne normative §1.3.

---

## PD7 — Hystérésis et plafonds (§1.3 + §3.4, littéral)

Chaîne complète, **différente de Risk** : Risk s'arrête à l'hystérésis (RD8, pas de plafond) ; Priority a une étape
de plus.

```
score → niveau brut (PD6) → hystérésis sur le niveau PUBLIÉ précédent (même règle que RD7) → PLAFOND → niveau publié
```

| Situation | Plafond |
|---|---|
| promesse applicable **ou** hold en vigueur | `WATCH` (index 1) |
| litige rendant le recouvrable nul (`collectible_minor = 0` avec `has_open_dispute`) | `ACTION` (index 2) |

Le plafond ne modifie jamais le score, seulement le niveau ; deux plafonds actifs prennent le **plus bas**
(`min`, transcrit de `prio_publish`). Le niveau **publié** (donc plafonné) devient le niveau précédent du calcul
suivant — jamais un niveau « avant plafond » non persisté (même raisonnement que RD7/RD8, § « pourquoi le niveau
publié »). Un plafond ne relève jamais un niveau. Un plafond qui disparaît permet une remontée **immédiate** au
niveau brut (montée immédiate, RD7).

**Condition exacte du plafond « dispute » (arbitrée, § DV3-5, CLOSED)** :

```
dispute_no_collectible = invoice.has_open_dispute AND invoice.collectible_minor == 0
```

Ce n'est **pas** un nouveau fait persistant ni un champ de `PriorityInput` : c'est une **dérivation du Domain**,
calculée à partir des deux champs déjà présents dans `InvoiceFacts` (gelé, tranche 1). Aucun amendement de contrat
nécessaire, aucune lecture supplémentaire.

---

## PD8 — Version du modèle

`model_version = 'prio-1.0'` (constante, RP-D), même principe que RD9.

---

## PD9 — Signal de rapprochement (§3.4 bis, littéral)

`reconciliation_pending` fait partie des **entrées normalisées** (donc du hash et de `reasons`) sous forme d'un
booléen ; il **ne modifie ni le score, ni le niveau, ni les plafonds** — un simple signal explicatif. Le montant non
alloué (`reconciliation_pending_minor`) est une valeur BRUTE, jamais lue par le Domain, jamais dans le snapshot
(l'interface le lit dans les faits courants, comme `D`/`Eo` pour Risk, RD10.2).

---

## PD10 — Entrées normalisées et `input_hash` (même principe que RD10, § DV2-8 étendu à Priority)

### PD10.1 `PriorityNormalizedInputs` — ce que le Domain calcule et compare (par valeur)

```
PriorityNormalizedInputs = {
  amount_pts, delay_pts, risk_pts, due_pts, attention_pts: int,
  previous_level: str | None,
  cap_promise_or_hold: bool,
  cap_dispute: bool,
  reconciliation_pending: bool,
}
```

Neuf champs (contre sept + confidence/previous_level pour Risk) : Priority n'a pas de notion de `confidence`
(aucun échantillon minimal, RP-G ne s'applique pas ici), mais porte DEUX indicateurs de plafond en plus, parce que
RP14 exige que le hash change quand un plafond apparaît ou disparaît, même à score identique (exactement le rôle de
`previous_level` pour Risk, RP14).

### PD10.2 `input_hash` : Application seulement (transcription directe de DV2-8, aucune ré-arbitrage nécessaire)

Même principe, mêmes garanties, même formule (`SHA256` du JSON canonique de `{model, org, subject, inputs}`),
calculé par l'Application APRÈS la `Decision`, jamais lu ni écrit par le Domain. Ce point a déjà été tranché pour
Risk (DV2-8) ; il n'y a rien de nouveau à arbitrer ici, seulement à l'appliquer.

`reasons` stocké : `{"factors": [{factor, normalized_input, points} × 5], "caps": [...], "signals": [...]}`, dérivé
de `PriorityNormalizedInputs` par le Domain (mise en forme de sa propre sortie, comme `factors` pour Risk).

---

## PD11 — Decision

### PD11.1 Cas « `PriorityNormalizedInputs` égal à `previous.normalized_inputs` »

`Decision(writes=(), events=())`, `outcome=PROCESSED`. Même règle que RD11.1.

### PD11.2 Cas « différent »

- `StateWrite('priority.item', invoice_id, RowChange(expect=..., set={level, rank_score, model_version, reasons}))`.
  Le Domain s'arrête là (même choix que DV2-9 option (b) pour Risk : il ne nomme jamais `priority_snapshots`,
  l'Application duplique en LOG en constatant l'écriture).
- `EventOut(PriorityChanged(from_level, to_level, rank_score), invoice_id)` **seulement si** le niveau **publié**
  change ET qu'un `previous` existait (même raisonnement que RD11.2/DV2-7 : à la création, aucun événement).
- `outcome = PROCESSED`.

### PD11.3 Cas « facture non ouverte » (PD3)

`StateWrite('priority.item', invoice_id, RowChange(..., set={level: 'NONE', rank_score: 0, ...}))` — **à la
différence de Risk**, ceci EST une écriture (Priority a toujours un élément pour une facture non-`DRAFT`, PD3), pas
une absence de décision. `outcome = PROCESSED`.

### PD11.4 Cas « facture `DRAFT` »

Aucune écriture, aucun événement — équivalent exact de RD11.3.

### PD11.5 Recalcul en masse (§3.5, RP21) — hors Domain (arbitrée, § DV3-9, amendement de contrat requis)

`RISK_CHANGED` ne déclenche PAS un recalcul de toutes les factures d'un client dans une transaction : son handler
émet **une seule** `PriorityRecalculationRequested(scope=CUSTOMER)` ; le traitement par lots (200/transaction,
curseur, reprise) est une responsabilité de l'**Application/coureur**, pas du Domain — le Domain ne voit jamais
qu'**une seule facture** à la fois (même frontière que RD11.4 pour Risk : le Domain ne décide jamais s'il doit
s'exécuter, ni sur quel périmètre, ni sur quel lot).

**Décision (arbitrée)** : le contrat déjà généré `PriorityRecalculationRequested{invoice_id, reason}` (par facture)
est **amendé** — pas contourné en émettant N événements par facture à la place, ce qui aurait déplacé la
responsabilité du lot vers l'émetteur et se serait éloigné de RP21. Le contrat devient :

```
PriorityRecalculationRequested = {
  scope: 'CUSTOMER' | 'INVOICE',
  customer_id: CustomerId | None,
  invoice_id: InvoiceId | None,
  reason: str,
}
```

Invariant d'exclusivité (à vérifier structurellement, P3) :
```
scope == 'CUSTOMER'  ⇒  customer_id is not None  AND  invoice_id is None
scope == 'INVOICE'   ⇒  invoice_id is not None    AND  customer_id is None
```

Ceci **n'est pas** une réouverture d'un contrat gelé : `priority/contracts/events.py` est un fichier **généré**,
jamais passé par aucun mécanisme de gel (ni `domain_freeze.json`, ni un futur `priority_domain_freeze.json` qui
n'existe pas encore) — c'est exactement le même statut que `RecomputeRisk.reads=()` avant l'amendement B5 pour Risk.
L'amendement se fera à l'étape « Registry/Contracts » (comme B5), pas avant, mais sa FORME est fixée ici pour ne pas
la découvrir a posteriori.

**Frontière de décision, à inscrire explicitement dans le Domain (nouveau, demandé par l'arbitrage)** :

```
Priority Domain V1 — Decision Boundary

Le Domain reçoit exactement UN PriorityInput pour UNE facture.

Le Domain ne connaît JAMAIS :
  - le scope du recalcul (CUSTOMER vs INVOICE),
  - le client comme périmètre de recalcul,
  - les lots (200/transaction),
  - les curseurs,
  - les reprises,
  - le planificateur.

RISK_CHANGED
    ↓
PriorityRecalculationRequested(scope=CUSTOMER, customer_id)     — UNE seule, émise par le handler risk.RiskChanged
    ↓
Application : invoices.OpenInvoicesOfCustomer                    — résolution du périmètre, hors Domain
    ↓
lot ≤ 200, curseur                                                — orchestration Application/coureur, hors Domain
    ↓
decide_recompute_priority(PriorityInput)                          — UNE facture à la fois, c'est tout ce que voit le Domain
    ↓
curseur suivant / reprise
```

---

## PD12 — Événements

Un seul type : `PRIORITY_CHANGED` (`PriorityChanged{from_level, to_level, rank_score}`, contrat à générer — § DV3-6).
Aucun effet extérieur.

---

## PD13 — Cas nominaux (transcrits de §3.6, cas d'or P1-P7)

| # | Cas | Attendu |
|---|---|---|
| PN1 | P1 : 1 200 000, 20j retard, `HIGH`, dernière action il y a 12j | score 81, `CRITICAL` |
| PN2 | P2 : 50 000, échéance dans 2j, `LOW` | score 6, `NONE` |
| PN3 | P3 : 400 000, 5j retard, `MEDIUM`, action il y a 2j | score 28, `WATCH` |
| PN4 | P4 : 700 000, 40j retard, risque inconnu, aucune action (`S=Dd=40`) | score 66, `PRIORITY` |
| PN5 | P5 : comme P1, précédent `CRITICAL`, promesse active | score 81, publié `WATCH` (plafond) |
| PN6 | P6 : comme P1, précédent `CRITICAL`, litige sans recouvrable | score 81, publié `ACTION` (plafond) |
| PN7 | P7 : comme P1, paiement non alloué du client | score 81, `CRITICAL` inchangé ; signal `RECONCILIATION_PENDING` dans `reasons`, hash différent |
| PN8 | premier calcul : `previous = None` (**pas** `previous.level = 'NONE'` — absence d'état publié antérieur, distincte d'un état publié dont le niveau vaudrait `NONE`, même distinction que pour Risk) | création, aucun `PRIORITY_CHANGED` |
| PN9 | facture non ouverte | `NONE`/`CLOSED`, écriture sans événement (sauf si niveau change depuis un état antérieur) |
| PN10 | facture `DRAFT` | aucune écriture |
| PN11 | plafond qui disparaît | remontée immédiate au niveau brut (comme RN9 pour Risk) |

---

## PD14 — Contre-exemples

| # | Cas | Attendu |
|---|---|---|
| PC1 | facture `DRAFT` | aucune écriture, `outcome=PROCESSED` |
| PC2 | `as_of` naïf | `PreconditionViolated` |
| PC3 | `C ≤ 0` | facteur montant = 0, pas une erreur (comme RC4) |
| PC4 | garde d'état violée en écriture | `CONCURRENT_MODIFICATION`, infrastructure, pas le Domain |
| PC5 | une entrée porte un flottant | rejet structurel (frontière Application/transport, P3 — pas une nouvelle règle du Domain : les contrats Application imposent déjà l'entier) |

---

## PD15 — Cas limites

| # | Cas | Attendu |
|---|---|---|
| PL1 | `Dd` et `Dj` tous deux « actifs » | impossible par construction (`overdue` est un booléen exclusif, §3.3) — à vérifier au typage (§ DV3-7) |
| PL2 | deux plafonds actifs en même temps | le plus bas l'emporte (`min`) |
| PL3 | `S` absent (`None`) | Domain calcule `S = Dd` lui-même |
| PL4 | score = 95 exactement | `CRITICAL`, jamais > 95 |
| PL5 | hystérésis à la limite (`score+3 == seuil`) | reste au niveau publié (même correction que RL10 pour Risk — **à vérifier dès l'écriture**, ne pas reproduire l'erreur de glose initiale) |

---

## PD16 — Invariants (à transcrire en catalogue `priority_catalogue.py` une fois le Domain codé)

Même famille que RI1-RI17 pour Risk, adaptée : bornes du score (0-95), monotonie par facteur, plafond jamais
relevant un niveau, `PRIORITY_CHANGED` ssi changement de niveau publié ET previous existant, déterminisme/pureté,
conservation de l'éligibilité à trois états (PD3). Liste précise à figer après codage (comme RD16 → RI1-17).

---

## PD17 — Correspondance avec le modèle de référence

`reference_model/verqia_models.py` contient déjà `prio_points`, `prio_score`, `prio_publish`, `prio_evaluate`,
exécutables et testés (`TestPriority`, `golden_cases.json['priority']`, P1-P7). **Ce que le Domain V1 (Priority) doit
reproduire exactement** : `prio_evaluate(organization_id, invoice_id, previous_published, A, C, Dd, Dj, risk_level,
since_action, overdue, promise_or_hold, dispute_no_collectible, reconciliation_pending) -> {rank_score, level,
level_index, caps, signals, reasons, input_hash}` — `input_hash` restant une affaire d'Application (PD10.2).

Comme pour Risk, une référence **indépendante** (`reference_model/priority_ref.py`) devra être écrite avant le code
du Domain — mais ici il n'y a **pas d'agrégation nouvelle à démontrer** (à la différence de Risk, RD17/RD2.2) : les
entrées de Priority sont déjà toutes ponctuelles (PD2.4). `priority_ref.py` aura donc surtout à couvrir
l'éligibilité à trois états (PD3) et la chaîne de décision (PD11), pas une nouvelle logique d'agrégation.

---

## PD18 — Plan de tests (après validation, avant code)

| Famille | Contenu |
|---|---|
| DT-A tables | seuils de niveaux, tranches de points, bornes de chaque facteur |
| DT-C nominaux | PN1-PN11 |
| DT-D refus | PC1-PC4 |
| DT-E limites | PL1-PL5 |
| DT-F propriétés | monotonie, plafond ne relève jamais, déterminisme |
| DT-G pureté | AR-01, AR-02, entrée en lecture seule, instant naïf refusé |
| DT-H raccord | écritures ⊂ `priority.item` ; événements ⊂ `(PRIORITY_CHANGED,)` |
| DT-R référentiel | contre `prio_evaluate` (score/plafond) et `priority_ref.py` (éligibilité à trois états, chaîne de décision) |
| DT-RUN | coureur réel, RP21 (recalcul par lots) simulé côté harnais, pas côté Domain |

---

## Validation : contradictions et gaps trouvés (DV3)

Aucun n'est corrigé dans le Domain lui-même.

### DV3-1 — `active_promise` : fournisseur potentiellement STUB, comme `PromiseRiskFacts` (DV2-5) — **CLOSED**

| | |
|---|---|
| **Constat** | `invoice.active_promise` (Rule Engine, déjà nommé) dépend de `promises`, module structurellement présent mais sans Domain écrit (même état qu'au moment de DV2-5 pour Risk). |
| **Décision** | Même traitement que DV2-5, avec la même exigence de nommage que DV3-2/DV3-4 : le Domain Priority consomme un port de faits explicite (`active_promise: bool`) ; tant que `promises` n'a pas de Domain réel, un fournisseur **explicitement nommé** (ex. `PrePromisesActiveReader`, documentant `supports_priority_promise = False`) est acceptable — mais **uniquement dans le harnais de test/développement**, jamais promu en implémentation de production déguisée. `test stub = OK · production stub = interdit`, même règle verrouillée que DV2-5. |

### DV3-2 — `hold_active` : aucun fournisseur possible avant la tranche Collection — **CLOSED**

| | |
|---|---|
| **Constat** | `invoice.hold_active` dépend de `collection_holds` (module `collection`, pas encore spécifié ni codé — tranche **suivante**, après Priority). Contrairement à `promises` (DV3-1), il n'existe **aucune** structure de module partielle à réutiliser même en stub minimal. |
| **Décision** | Le champ `hold_active: bool` est **conservé** dans `PriorityInput` (le retirer reviendrait à modifier `prio_publish`, gelé). Mais **pas de `False` en dur anonyme** : `False` signifie « aucun hold actif », un FAIT métier — pas « aucun fournisseur pour l'instant », une LIMITATION d'implémentation. Ce sont deux états distincts qu'un simple booléen en dur confondrait silencieusement. L'Application doit construire cette valeur via un **adaptateur de provenance explicitement nommé** (ex. `PreCollectionHoldReader`), qui documente noir sur blanc `supports_priority_hold = False` et ne peut jamais être confondu avec, ni promu en, un fournisseur de production. Le contrat `PriorityInput`/le Domain ne changent pas ; seule la provenance de la valeur est tracée. |

### DV3-3 — `days_since_last_action` : même situation que DV3-2, mais différente — **CLOSED**

| | |
|---|---|
| **Constat** | Dépend de `collection_actions` (module `collection`, pas construit). |
| **Décision** | Aucun adaptateur de provenance nécessaire ici, à la différence de DV3-2/DV3-4 : le modèle gelé résout déjà ce cas nativement (« sans aucune action, `S = Dd` », §3.2, littéral). Tant que Collection n'existe pas, AUCUNE action n'a jamais été exécutée sur aucune facture — `days_since_last_action = None` est donc la valeur **structurellement vraie**, pas un bouchon : `None` signifie exactement « aucune action connue », qui est la réalité tant que Collection n'existe pas. Le Domain applique sa propre règle de repli (déjà dans PD2.3/PL3) sans que l'Application ait besoin de construire quoi que ce soit de spécial. |

### DV3-4 — `reconciliation_pending` : aucun fournisseur avant la tranche Réconciliation — **CLOSED**

| | |
|---|---|
| **Constat** | Dépend de la logique de qualification des paiements Q1-Q5 (`COLLECTION_ENGINE_V1_2.md` §2.2), rattachée à une tranche **Réconciliation**, postérieure à Collection. |
| **Décision** | Même traitement que DV3-2 : le champ `reconciliation_pending: bool` est conservé dès maintenant dans `PriorityInput` — d'autant plus sûr ici que ce signal **ne modifie ni le score ni le niveau ni les plafonds** (PD9), donc une valeur de provenance temporaire ne peut fausser aucune décision publiée, seulement laisser `reasons.signals` vide plus longtemps que nécessaire. Un adaptateur de provenance explicitement nommé (ex. `PreReconciliationSignalReader`, documentant `supports_reconciliation_signal = False`) est requis pour la même raison que DV3-2 : ne jamais confondre « signal absent en réalité » et « fournisseur pas encore construit ». Point important pour plus tard : le remplacement par le vrai fournisseur (tranche Réconciliation) pourra changer `normalized_inputs`/`input_hash`/`reasons` sans jamais changer rétroactivement un score déjà publié. |

### DV3-5 — dérivation exacte de `dispute_no_collectible` — **CLOSED**

| | |
|---|---|
| **Constat** | `verqia_models.prio_evaluate` prend ce paramètre nu ; `RISK_PRIORITY_CASHFLOW_V1.md` §3.4 dit seulement « litige rendant le montant recouvrable nul ». |
| **Décision** | `dispute_no_collectible = invoice.has_open_dispute AND invoice.collectible_minor == 0` — une **dérivation du Domain** à partir de deux champs déjà présents dans `InvoiceFacts` (gelé), jamais un nouveau fait persistant ni un champ de `PriorityInput`. Aucun amendement de contrat, aucune nouvelle lecture. Voir PD7. |

### DV3-6 — contrat d'événement `PriorityChanged` : déjà généré, conforme — **CLOSED**

| | |
|---|---|
| **Constat (vérifié)** | `verqia/priority/contracts/events.py` existe déjà et contient exactement `PriorityChanged{from_level: str, to_level: str, rank_score: int}` (`CATEGORY=RESULT`), ainsi que `priority.RecomputePriority` (`subscribes=(PriorityRecalculationRequested,)`, `writes=('priority.item',)`, `lock='ProjectionRecompute'` — même opération de verrou que `RecomputeRisk`) et `priority.RequestPriorityRecalc` (`subscribes=` la liste §1.4 des `refresh_events`, déjà alignée). |
| **Décision** | aucune contradiction : conforme à PD11.2/PD12. Pas de DV à arbitrer ici. |

### DV3-9 — `PriorityRecalculationRequested` est PAR FACTURE, pas par client (contredit RP21/§3.5) — **BLOQUANT, RÉSOLU**

| | |
|---|---|
| **Source contradictoire** | §3.5/RP21 (frozen, `RISK_PRIORITY_CASHFLOW_V1.md`) décrit UNE demande par CLIENT après un `RISK_CHANGED`. Le type déjà généré (`verqia/priority/contracts/events.py`) est `PriorityRecalculationRequested{invoice_id: InvoiceId, reason: str}` — **par FACTURE**, sans `scope` ni `customer_id`, et sans notion de lot. |
| **Décision** | **Option (a), amendement du contrat, forme précisée** — voir PD11.5. Rejeté : l'option (b) (émettre N demandes par facture depuis le handler `RISK_CHANGED`) aurait déplacé la responsabilité du lot vers l'émetteur, contredisant RP21 qui la place explicitement dans le TRAITEMENT de la demande (« le Priority Engine traite... par lots reprenables »), pas dans sa fabrication. `PriorityRecalculationRequested` devient `{scope: 'CUSTOMER'\|'INVOICE', customer_id: CustomerId\|None, invoice_id: InvoiceId\|None, reason: str}` avec l'invariant d'exclusivité des identifiants. Ce n'est **pas** la réouverture d'un contrat gelé (rien n'est gelé côté `priority` aujourd'hui) : c'est un amendement Registry/Contracts, au même titre que B5 pour Risk, effectué **avant** `priority_ref.py` puisqu'il détermine la forme exacte de la frontière de décision (PD11.5). |

### DV3-7 — exclusivité structurelle de `overdue` (Dd vs Dj) — **CLOSED**

| | |
|---|---|
| **Constat** | Le barème (§3.3) traite « retard » et « échéance imminente » comme mutuellement exclusifs via un seul booléen `overdue`. `InvoiceFacts` porte déjà `is_late` (gelé). |
| **Décision** | `overdue = invoice.is_late`, directement — **aucun nouveau booléen dérivé**. Réutiliser la définition déjà gelée plutôt que reconstruire une notion parallèle à partir de `Dd`/`Dj` (ce qui créerait deux sources de vérité sur la même question). `Dd` et `Dj` servent aux FACTEURS (montants de points), mais n'interviennent pas dans la décision d'exclusivité elle-même : `if invoice.is_late: delay_pts(...) else: due_pts(...)`. |

### DV3-8 — état actuel du registre (`modules.py`) pour `priority`, à corriger comme B5 l'a fait pour `risk`

| | |
|---|---|
| **Constat** | `priority.deps` contient actuellement `['kernel','organizations','customers','invoices','payments','promises','risk','collection','rules']` — une esquisse large, du même type que celle de `risk` avant B5 (qui incluait `customers` à tort). `READS['priority']` liste 7 entrées provisoires, dont `customers.CustomerFacts` (probablement à retirer, comme pour Risk) et `collection.CollectionFacts`/`payments.PaymentFacts` (à préciser ou retirer selon PD2.2). |
| **Décision** | pas un DV3 à proprement parler — sera traité mécaniquement à l'étape « Registry/Contracts », comme B5 pour Risk. PD2.2 est validé et DV3-1 à DV3-7, DV3-9 sont maintenant tranchés : plus rien ne bloque cette étape mécanique, hormis l'amendement de contrat DV3-9 lui-même, à faire en premier. |

---

## Prochaines étapes

| Étape | État |
|---|---|
| Spécification (PD1-PD18) | **arbitrée, corrections A/B/C appliquées** |
| Arbitrage DV3-1 à DV3-9 | **fait** — DV3-1 à DV3-7 et DV3-9 CLOSED ; DV3-8 volontairement différé (mécanique, après Registry/Contracts) |
| Amendement du contrat `PriorityRecalculationRequested` (DV3-9) | à faire — avant `priority_ref.py`, car il fixe la forme de PD11.5 |
| Référence indépendante `reference_model/priority_ref.py` + cas d'or | à faire, **après** l'amendement DV3-9 |
| Amendements Registry/Contracts (DV3-8, style B5) | à faire |
| Types niveau C (`PriorityParameters` uniquement, confirmé — aucun autre type nouveau, DV3-5 est une dérivation, pas un fait) | à faire |
| Code du Domain (`verqia/priority/domain/`) | à faire |
| Tests Domain (DT-A à DT-H, RD18-équivalent) + tests différentiels | à faire |
| Porte de fermeture (invariants, mutations) | à faire |
| Coureur | à faire |
| Intégration (Risk → Priority, isolation tenant, convergence, atomicité) | à faire |
| Empreinte de gel, puis gel | à faire |

Aucune formule de `prio-1.0` n'est réinventée : les seules décisions de ce document sont la frontière Domain (PD1),
la forme de `PriorityInput`/`PublishedPriority` (PD2/PD10, corrigée A/B/C), le traitement des quatre dépendances
externes non encore constructibles (DV3-1, DV3-2, DV3-3, DV3-4 — DV3-3 sans adaptateur nécessaire, les trois autres
avec un adaptateur de provenance explicitement nommé) et l'amendement de `PriorityRecalculationRequested` (DV3-9) —
exactement le même type de travail que RD1/RD2/DV2-1 à DV2-9 pour Risk.
