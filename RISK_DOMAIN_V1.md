# VERQIA — Risk Domain V1 (spécification)

Statut : **SPÉCIFICATION VALIDÉE le 2026-09-22 — DV2-1 à DV2-9 tous arbitrés et confirmés.** Contrôle ciblé de clôture effectué (recherche de `table`/`repository`/`ORM`/`risk_snapshots`/`input_hash`/`transaction`/`verrou` dans tout le texte côté Domain) : aucune fuite résiduelle. **La spécification n'est pas le gel du Domain** : suit la même suite que la tranche 1 — référence indépendante (`risk_ref.py`), code, tests, mutations, porte de fermeture, coureur, empreinte, gel — présentée en fin de document (§ « Prochaines étapes »). Aucun code écrit à ce stade.
Méthode : identique à Domain V1 tranche 1 — sources gelées → décisions RDx → contradictions signalées (`DV2-x`) → validation → seulement ensuite référence indépendante, code.
Ce document couvre uniquement le **Risk Engine** (`risk-1.0`). Priority et Cashflow restent hors périmètre ; ils consommeront `RiskLevel` (RD1) sans le recalculer.

Sources gelées relues : `RISK_PRIORITY_CASHFLOW_V1.md` §0, §1, §2, §5 à §12 ; `INVARIANTS_V1.md` §8 ; `DATA_CONTRACT_V1.md` §7.1, §7.2 ; `ENGINE_CONTRACTS_V1.md` EC-14 ; `RULE_ENGINE_V1.md` (faits `customer.*`, `org.*`) ; `TECHNICAL_ARCHITECTURE_V1.md` (TD12 fournisseurs de faits, TD23 temps) ; `Application Contract V1` (`UseCaseSpec` de `risk`, gelé, amendements B1 à B4) ; contrats générés (`risk/contracts/*`, `organizations/contracts/queries.py`) ; `reference_model/verqia_models.py` (§ Risk, déjà exécutable) et `golden_cases.json['risk']` (5 cas G1–G5) ; le Domain V1 tranche 1 gelé (`invoices.contracts.facts.InvoiceFacts`, `payments.contracts.facts.PaymentFacts`).

---

## RD1 — Frontière (Boundary)

```
facts (déjà calculés par leurs Domains propriétaires) + paramètres du modèle (dans le code) + niveau publié précédent + as_of
                                            │
                                            ▼
                                      Risk Domain
                                            │
                                            ▼
                                        Decision
```

Même contrat que tranche 1 (P8) : `decide(state, command, as_of) -> Decision`, pure, sans E/S, sans horloge, sans port. **Interdit** (RP-A à RP-H, DR1) : Django, PostgreSQL, Redis, HTTP, planificateur, horloge système, apprentissage automatique, lecture ou écriture externe, mutation d'état.

**Le Risk Domain n'est PAS le Risk Engine complet.** Restent hors de lui, dans Application / Infrastructure / Rule Engine :
- le verrou consultatif `(risk, client)` et la transaction (P5, P6) ;
- la lecture des sources et leur normalisation en `InvoiceFacts` / `PaymentFacts` — **déjà faite par les Domains propriétaires** (`invoices`, `payments`) ; le Risk Domain ne relit jamais une facture ou un paiement lui-même (DR2, RD2) ;
- `RequestRiskRecalc` (déduplication des `refresh_events` en une demande par cible) et `RequestDailyRiskRefresh` (cadence) : deux **autres** cas d'usage du même module, hors de cette spécification (ils ne calculent rien) ;
- la convergence entre projections, les événements `REQUEST`, les tentatives (`RETRYING`/`DEAD`), `ProjectionSafetyNet` ;
- la lecture de `customer.risk_level` par le Rule Engine (fournisseur de faits, TD12) : ce n'est pas le Risk Domain qui répond aux conditions d'automatisation, c'est `risk_profiles` via son `FactReader`.

**Un seul cas d'usage dans cette spécification : `RecomputeRisk`** (`risk.profile` en écriture, `RISK_CHANGED` en émission, idempotence `input_hash`, une transaction par client). `RequestRiskRecalc` et `RequestDailyRiskRefresh` ne produisent aucune décision de risque ; ils sont mentionnés seulement pour la frontière.

**Sortie publiée (RiskLevel, consommée par Priority/Cashflow, RP-E).** Le Risk Domain ne lit ni Priority ni Cashflow ; ce sens unique n'est pas à démontrer ici, il est déjà structurel (aucune dépendance inverse dans le registre).

### RD1.1 — Ce que le Domain ne connaît JAMAIS (verrouillé par l'arbitrage du 2026-09-22)

Liste fermée, reprise du verdict : `input_hash` comme **mécanisme de persistance** (le calcul du SHA-256 et la comparaison qui en décide n'appartiennent pas au Domain, § DV2-8) ; PostgreSQL ; verrous (`locks`) ; planificateur ; `REQUEST` (catégorie d'événement) ; `RISK_CHANGED` comme **effet technique** (l'émission d'un objet événement est une décision du Domain, sa publication dans l'outbox n'en est pas une) ; nouvelle tentative (`retry`) ; cache ; `computed_at` ; `risk_snapshots` comme **table** dont la création ou non relève d'une décision de stockage ; `InvoiceRepository` ; `PaymentRepository`. Le Domain connaît seulement **les faits, les paramètres, l'ancien état publié et `as_of`**.

---

## RD2 — Entrées

### RD2.1 Table (transcrite de RISK_PRIORITY_CASHFLOW_V1.md §2.2, aucune reformulation)

| Symbole | Donnée | Fait |
|---|---|---|
| `D` | plus grand nombre de jours de retard parmi les factures ouvertes | `customer.max_days_overdue` |
| `n` | nombre de factures soldées sur les 12 derniers mois | `customer.settled_invoice_count_12m` |
| `L` | part des factures soldées en retard, en pour-mille entier | `customer.late_payment_rate_12m` |
| `M` | délai moyen de paiement en jours, plafonné entre 0 et 30 | `customer.avg_days_to_pay_12m` |
| `B` | promesses `BROKEN` sur 12 mois | `customer.broken_promises_12m` |
| `Eo` / `C` | exposition en retard / montant critique | `customer.overdue_exposure_minor`, `org_settings.critical_amount_minor` |
| `R` | paiements annulés sur 12 mois | `customer.reversed_payments_12m` |
| `T` | tendance du délai (jours) ; inconnue si moins de 2 factures dans l'une des deux fenêtres de 90 jours | `customer.delay_trend_90d` |

Fenêtres : « 12 mois » = 12 mois calendaires précédant `as_of`, dans le **fuseau de l'organisation** ; « 90 jours » = 90 jours calendaires. Échantillon minimal `n ≥ 3` (sinon `L`, `M` inconnus, RP-G).

### RD2.2 Correspondance avec le Domain V1 gelé (RD-clé de cette spécification)

Le point central : **`D` et `Eo` sont des agrégats de `InvoiceFacts` gelé, pas de nouvelles règles.**

| Entrée | Calcul à partir des facts existants | Source |
|---|---|---|
| `D` | `max(f.days_late for f in invoices if f.is_open and f.is_late, default=0)` | `InvoiceFacts.is_open`, `.is_late`, `.days_late` (Domain V1 §1.4) |
| `Eo` | `sum(f.outstanding_minor for f in invoices if f.is_open and f.is_late)` | `InvoiceFacts.is_open`, `.is_late`, `.outstanding_minor` |
| `n`, `L`, `M`, `T` | agrégats sur les factures **soldées** (`settlement_state == PAID`) dans les fenêtres, à partir de `f.settled_on` et `f.settlement_delay_days` | `InvoiceFacts.settlement_state`, `.settled_on`, `.settlement_delay_days` |
| `B` | `len(promise_facts)` (RD2.3) — agrégat sur des `PromiseRiskFacts`, type **nouveau**, propriété du module `promises` mais dont l'implémentation peut être un fournisseur STUB documenté tant que le Domain `promises` n'existe pas (§ DV2-5, arbitré) | fait fourni tel quel, jamais recalculé par Risk |
| `R` | `len(reversed_payments)` (RD2.3) — agrégat sur des `RiskPaymentFacts`, type **nouveau et séparé** de `payments.contracts.facts.PaymentFacts` (gelé, intact) | § DV2-4, arbitré : aucun amendement de la tranche 1 |
| `C` | `risk_parameters.critical_amount_minor` | § DV2-3, arbitré : lecture organisationnelle dédiée, jamais `CalendarReader` |

`invoice.days_overdue` du Rule Engine (`max(0, org.today − due_date)` si `is_overdue`, sinon 0) et `invoice.is_overdue` (`is_open et due_date < org.today`) sont **exactement** `InvoiceFacts.days_late` et `InvoiceFacts.is_open and InvoiceFacts.is_late` : c'est la preuve que la tranche 1 a bien produit des faits **réutilisables**, pas seulement suffisants pour elle-même (RD-preuve, à vérifier par test différentiel, RD17).

`avg_days_to_pay_12m` et `late_payment_rate_12m` se calculent sur `S = Σ settlement_delay_days` des factures soldées dans la fenêtre ; `settlement_delay_days` existe déjà dans `InvoiceFacts` (`(settled_on − due_date).days`), calculé par `invoices.decide_apply_settlement` (DD11/V7). Le Risk Domain ne réévalue jamais `settled_on` : il le lit.

### RD2.3 Forme reçue par le Domain (révisée le 2026-09-22, arbitrage DV2-1 à DV2-5)

```
RiskInput = {
  risk_parameters: RiskParameters,                        # { critical_amount_minor, timezone } — § DV2-3/RD2.4, assemblé par l'Application depuis DEUX lectures
  has_ever_issued: bool,                                   # RD3 — au moins une facture qui n'est ni DRAFT ni CANCELLED, sans borne de fenêtre
  open_invoices:        tuple[InvoiceFacts, ...],          # factures ouvertes du client, quel que soit leur retard
  settled_invoices_12m: tuple[InvoiceFacts, ...],          # factures soldées dans les 12 derniers mois calendaires (fenêtre résolue par l'Application, § RD2.4)
  reversed_payments:    tuple[RiskPaymentFacts, ...],      # paiements annulés du client, bornés à une fenêtre large par l'Application — § DV2-4
  promise_facts:        tuple[PromiseRiskFacts, ...],      # promesses rompues du client, bornées de même — § DV2-5, fournisseur potentiellement STUB (jamais dans le Domain lui-même)
  previous: PublishedRisk | None,                          # § RD2.5 — PAS de champ « input_hash »
  as_of: datetime,
}
```

Le Risk Domain **agrège** `open_invoices` et `settled_invoices_12m` (RD2.2) ; il ne reçoit ni `n` ni `L` ni `M` ni `T` déjà calculés — ce sont des sorties de son propre calcul, pas des entrées (sinon la règle « historique insuffisant » de RP-G serait dupliquée entre l'Application et le Domain). Il agrège de la même façon `reversed_payments` (→ `R`) et `promise_facts` (→ `B`). `has_ever_issued` n'est PAS dérivé des deux listes ci-dessus (RD3 explique pourquoi) : c'est un signal distinct, résolu séparément par l'Application.

### RD2.4 — Bornage temporel : qui fait quoi (décision de conception, pas un DV2)

**L'Application borne** les listes à une fenêtre suffisamment large (12 mois calendaires, dans le fuseau de l'organisation). **Le Domain calcule** lui-même, à partir de `as_of` et de `risk_parameters.timezone`, la date locale du jour et les deux sous-fenêtres de 90 jours nécessaires à `T` (`delay_trend_90d`), par simple filtrage de `settled_invoices_12m` sur `f.settled_on`. Cette utilisation de `timezone` par le Domain n'est **pas** une connaissance de PostgreSQL ou d'un calendrier applicatif : c'est la réutilisation de `kernel.calendar.business_date` (K20, TD23), déjà utilisée par le Domain gelé de la tranche 1 (`invoices.decide_issue_invoice`, `decide_lifecycle_scan`) pour la même raison — une fonction pure, sans horloge système, sur une donnée qu'il reçoit. Une seule fenêtre demandée à l'Application (12 mois) plutôt que trois (12 mois, 90 jours, 90 jours précédents) : la seconde est un sur-ensemble strict des deux autres, aucune information n'est perdue.

**`RiskParameters` est assemblé par l'Application à partir de DEUX lectures distinctes, pas d'une seule** (précision apportée en seconde lecture — la première version de ce document laissait croire, à tort, que `timezone` venait aussi d'`OrgSettings`) :
- `timezone` vient d'`organizations.CalendarReader`, la dépendance que `risk` a **déjà** (registre gelé) — un lecteur de calendrier doit au minimum exposer le fuseau pour que « aujourd'hui » ait un sens ; c'est cette même lecture qui borne les fenêtres de 12 mois côté Application.
- `critical_amount_minor` vient d'`organizations.OrgSettings`, **nouvellement** consommé par `risk` (§ DV2-3).

`RiskParameters` ne porte **que** ces deux champs — pas `due_soon_days` (le barème `risk-1.0` ne l'utilise nulle part, à la différence de Priority, dont la spécification est hors périmètre de ce document). Éviter d'anticiper les besoins d'une tranche non encore spécifiée, pour ne pas reconstituer, à un autre niveau, le « conteneur artificiel » que DV2-3 refuse pour `CalendarReader`. Le Domain reçoit la structure déjà assemblée : il ne sait pas que ses deux champs viennent de deux requêtes différentes, ni même que `CalendarReader`/`OrgSettings` existent — c'est un détail d'assemblage de l'Application.

### RD2.5 — `PublishedRisk` : ce que « l'ancien état publié » contient

```
PublishedRisk = {
  level: str,                                # niveau publié précédent (RD7, RD8)
  normalized_inputs: NormalizedRiskInputs,    # RD10 — PAS un input_hash
}
```

`NormalizedRiskInputs` est le même septuplet que RD10 (les points par facteur, `confidence`, `previous_level`). Le Domain compare **ses propres valeurs**, nouvellement calculées, à `previous.normalized_inputs` **par égalité de valeur** (aucun hachage) pour décider s'il y a un changement à publier (RD11).

### RD2.6 — Types nouveaux introduits par cette tranche (aucun n'appartient à la tranche 1 gelée)

```
RiskPaymentFacts   = { reversed_at: date }                       # module payments — § DV2-4 ; minimal, seul ce que risk-1.0 consomme (R = un compte)
PromiseRiskFacts   = { broken_at: date }                          # module promises — § DV2-5 ; minimal, de même (B = un compte)
RiskParameters     = { critical_amount_minor: int, timezone: str } # module organizations — § DV2-3
```

Un champ n'est ajouté à l'un de ces types que le jour où un facteur du barème l'exige explicitement (aucune anticipation, même principe que RD2.4 pour `due_soon_days`).

---

## RD3 — Éligibilité

> Transcrit de §2.1 : « Un profil de risque existe si le client a au moins une facture **émise** (ni `DRAFT`, ni `CANCELLED`). Sinon, aucun profil. »

`is_eligible(open_invoices, settled_invoices_12m) = bool(open_invoices) or bool(settled_invoices_12m)` **n'est pas** la bonne traduction : une facture émise mais déjà soldée et hors fenêtre de 12 mois resterait « émise » sans figurer dans aucune des deux listes fournies. L'éligibilité ne se décide donc **pas** sur les deux listes de RD2.3 seules : elle exige de savoir si le client a **au moins une facture qui n'est plus `DRAFT` ni `CANCELLED`**, sans borne de fenêtre. C'est un signal supplémentaire, distinct de `open_invoices`/`settled_invoices_12m` — proposé : `has_ever_issued: bool`, fourni par l'Application (lecture bornée à l'existence, pas au contenu).

**Cas limite important** : un client dont toutes les factures ont été émises puis `VOID`ées reste éligible (`VOID` ≠ `DRAFT`/`CANCELLED`) ; son score sera 0 sur tous les facteurs si aucune n'est ouverte ni soldée dans la fenêtre — **LOW**, pas « pas de profil ».

**Sans profil** : `RecomputeRisk` ne produit aucune écriture (pas de ligne à supprimer non plus : « pas de profil » = absence de ligne, jamais une ligne à `level=UNKNOWN` — `UNKNOWN` n'existe que côté Rule Engine, en l'absence de ligne). `outcome = PROCESSED` (rien à faire n'est pas une erreur ; ce n'est pas `SKIPPED` non plus, cette issue étant réservée, par attribution la plus cohérente, à `RequestRiskRecalc`, RD1).

---

## RD4 — Normalisation des facts

Transcrit de §2.3, sans modification. Toutes les divisions sont `floor` (`⌊⌋`), déjà nommées dans le contrat.

| Facteur | Points | Règle |
|---|---:|---|
| Retard actuel | 0–30 | `D=0→0 · 1–7→5 · 8–15→12 · 16–30→20 · 31–60→26 · ≥61→30` |
| Historique de retard | 0–25 | si `n≥3` : `⌊L×15/1000⌋ + ⌊min(max(M,0),30)×10/30⌋` ; sinon 0 |
| Promesses rompues | 0–15 | `min(15, 5×B)` |
| Exposition en retard | 0–15 | si `C>0` : `min(15, ⌊Eo×15/C⌋)` ; sinon 0 |
| Paiements annulés | 0–10 | `min(10, 5×R)` |
| Tendance | 0–5 | si `T>0` : `min(5, ⌊T×5/10⌋)` ; sinon 0 |

`confidence = 'LOW' if n < 3 else 'HIGH'` (RP-G : historique insuffisant ⇒ contribution 0, jamais une valeur devinée).

---

## RD5 — Calcul du score

`score = delay_pts + history_late_pts + history_delay_pts + broken_pts + exposure_pts + reversed_pts + trend_pts`, domaine `[0, 100]`, maximum atteignable **exactement 100** (30+15+10+15+15+10+5 = 100 ; `history` = `⌊15⌋+⌊10⌋` max = 25 quand `L=1000, M≥30`). Transcrit de `verqia_models.risk_points`/`risk_score`, aucune reformulation.

---

## RD6 — Niveaux

`LOW 0–24 · MEDIUM 25–49 · HIGH 50–74 · CRITICAL 75–100` (§2.3). `level_index(score, RISK_THRESHOLDS)` : le plus grand indice `i` tel que `score ≥ seuil[i]`.

---

## RD7 — Hystérésis

Transcrit de §1.3 :
```
P = niveau PUBLIÉ précédent (ou absent, premier calcul)
si niveau(score) ≥ P :  stabilisé = niveau(score)
sinon                :  stabilisé = max( niveau(score), niveau(score + 3) )
```
Montée immédiate, descente seulement si `score + 3` reste sous le seuil courant. **Risk n'a aucun plafond** (à la différence de Priority, §3.4) : `niveau publié = niveau stabilisé`, directement (RD8).

---

## RD8 — Stabilisation (chaîne complète, RP15)

```
score → niveau brut (RD6) → hystérésis sur le niveau PUBLIÉ précédent (RD7) → niveau publié
```

Pas de plafond métier pour Risk. Le **niveau publié** (celui qui vient d'être décidé, pas un « avant plafond » puisqu'il n'y en a pas) devient le niveau précédent du calcul suivant — cohérent avec RD10 (il fait partie des entrées normalisées du hash).

---

## RD9 — Version du modèle

`model_version = 'risk-1.0'` (constante du code, RP-D). Aucun paramètre réglable par l'organisation en V1, à l'exception de `critical_amount_minor` qui est une **donnée**, pas un paramètre du modèle. Une mise à niveau de version (RP10) est un amendement de ce document, pas une variante silencieuse.

---

## RD10 — Entrées normalisées et `input_hash` (révisé : `input_hash` n'est PLUS une notion du Domain, § DV2-8)

### RD10.1 `NormalizedRiskInputs` — ce que le Domain calcule et compare (par valeur)

```
NormalizedRiskInputs = {
  delay_pts, history_late_pts, history_delay_pts, broken_pts, exposure_pts, reversed_pts, trend_pts: int,
  confidence: 'LOW' | 'HIGH',
  previous_level: str | None,
}
```

C'est le **même** septuplet que celui que §1.2/§2.4 nomment « entrées normalisées du hash » — mais ici, il n'est **jamais haché par le Domain**. Le Domain compare deux valeurs de ce type par **égalité structurelle** (`==`, aucune cryptographie, aucun JSON canonique, aucun encodage) : la sienne (nouvellement calculée) contre `previous.normalized_inputs` (RD2.5). Cette égalité de valeur est, par construction, **strictement équivalente** à l'égalité de `input_hash` telle que définie par RP14 (le hash n'est qu'une fonction pure de ce même septuplet, plus `model`/`org`/`subject` qui ne varient pas d'un recalcul à l'autre pour un même client) : rien n'est perdu à ne pas le calculer dans le Domain.

### RD10.2 `input_hash` : un artefact de PERSISTANCE, calculé par l'Application, jamais lu ni écrit par le Domain

Transcrit de §1.2, mais **relocalisé** (§ DV2-8) : `input_hash = SHA256(JSON canonique de {model, org, subject, inputs: NormalizedRiskInputs})`, clés triées, aucun espace, entiers/chaînes seulement. C'est **l'Application** qui le calcule, **après** avoir reçu la `Decision` du Domain, à partir des `NormalizedRiskInputs` que celle-ci contient — uniquement pour servir de clé d'unicité à `risk_snapshots` (`UQ(customer_id, model_version, input_hash)`) et d'identifiant compact côté API. Il ne conditionne **aucune** branche du Domain : la branche (rien / snapshot sans événement / snapshot avec événement) est décidée en RD11 par l'égalité de `NormalizedRiskInputs`, avant même qu'un hash existe.

- **Hors contenu déterminant** (métadonnées de provenance, jamais dans `NormalizedRiskInputs` ni dans le hash) : `computed_at`, `trigger_event_id` — l'Application les pose, toujours, indépendamment de ce que le Domain a décidé (RD11.4).
- **Jamais dans `factors` ni dans `NormalizedRiskInputs`** : valeurs brutes (`D`, `Eo`, `n`…) ; l'interface les relit dans les faits courants (RP14).
- **Propriété vérifiée** (§2.7) : deux valeurs brutes dans la **même tranche de points** donnent le **même** `NormalizedRiskInputs` (donc le même `factors`, donc le même `input_hash` une fois calculé côté Application) ; deux tranches différentes diffèrent partout.

`factors` stocké : `{"factors": [{"factor", "normalized_input", "points", "max"} × 6], "meta": {"confidence"}}`, dérivé de `NormalizedRiskInputs` par le Domain (c'est une mise en forme de sa propre sortie, pas une lecture de persistance).

---

## RD11 — Decision (révisée, § DV2-8 : la branche est décidée par égalité de valeur, jamais par un hash)

Le Domain calcule **toujours** `score`, `level`, `NormalizedRiskInputs` et `factors` (RD5 à RD10.1), que quelque chose ait changé ou non — c'est une fonction totale, sans branche cachée sur « est-ce que je dois recalculer ». Ce qu'il décide, c'est **ce qu'il propose d'écrire et d'émettre**, par comparaison de valeur avec `previous` (RD2.5) :

### RD11.1 Cas « `NormalizedRiskInputs` égal à `previous.normalized_inputs` »

`Decision(writes=(), events=())`, `outcome = PROCESSED`. Aucune ligne à créer, aucun `Append`. **`computed_at` n'est pas dans cette `Decision`** : c'est l'Application qui le pose, **toujours**, sur *chaque* invocation de `RecomputeRisk`, qu'il y ait ou non une `Decision` non vide (RD11.4) — c'est une opération de fraîcheur, orthogonale à ce que le Domain a décidé.

`PROCESSED` — **pas** `REPLAY`, terme réservé aux commandes à clé d'idempotence dans le contrat Application gelé (§ DV2-6, arbitré : Invariants §8 sera corrigé pour employer le vocabulaire contractuel exact).

### RD11.2 Cas « `NormalizedRiskInputs` différent »

- `StateWrite('risk.profile', customer_id, RowChange(expect=..., set={score, level, model_version, factors}))` — le Domain **ne pose pas** `input_hash` ni `computed_at` dans ce `set` : ce sont des colonnes que l'Application complète en appliquant la `Decision` (comme `aggregate_version` en tranche 1, DD15). La garde d'état `expect` se dérive entièrement de `previous` (RD2.5) : `{'score': somme(previous.normalized_inputs), 'level': previous.level}` — aucune donnée supplémentaire à ajouter à `RiskInput` pour cela. `None` pour une création.
- **Le Domain s'arrête là (DV2-9, option (b), arbitrée).** Il ne décide pas, et ne nomme jamais, l'ajout d'une ligne d'historique. C'est l'Application qui, en constatant que ce `StateWrite` porte des valeurs différentes de celles déjà persistées, duplique la ligne courante dans la table LOG correspondante (`risk_snapshots`, Data Contract §7.2) — exactement comme elle duplique déjà `invoice_state_history` à partir du champ `history` d'un `RowChange` en tranche 1, mais ici sans passer par ce champ (`HistoryRow` ne suffit pas à porter `score`/`factors`, § DV2-9). Le nom de la table, sa nature LOG, sa contrainte d'unicité : rien de tout cela n'est une notion du Domain.
- `EventOut(RiskChanged(from_level, to_level, score), customer_id)` **seulement si** `level` change par rapport à `previous.level` — **et seulement si `previous` existe** : le contrat gelé (`risk/contracts/events.py`) donne à `RiskChanged.from_level` le type `str`, non optionnel. Sur la première décision d'un client (`previous = None`), **aucun événement** n'est émis ; seul le profil est écrit (le premier historique en découle côté Application, comme ci-dessus) (§ DV2-7, arbitré).
- Aucun audit (`RecomputeRisk` est un handler, pas une commande d'utilisateur ; C13 — cohérent avec `audit = NONE` déjà déclaré).
- `outcome = PROCESSED`.

### RD11.3 Cas « pas de profil possible » (RD3)

Aucune écriture, aucun événement, `outcome = PROCESSED`.

### RD11.4 Ce que le Domain NE FAIT JAMAIS (RD1.1, verrouillé)

Il ne pose ni `computed_at` ni `trigger_event_id` ni `input_hash` (métadonnées de provenance et de persistance, ajoutées par l'Application, comme `aggregate_version` en tranche 1, DD15) ; il ne calcule aucun hachage ; il ne calcule pas `causation_depth` ; il ne décide pas s'il doit s'exécuter (verrou, staleness de l'événement déclencheur) — ce n'est pas un fait qu'il reçoit dans `RiskInput` (RD2.3), c'est une décision de **l'Application**, avant même d'appeler `decide`. **`computed_at` est toujours écrit par l'Application**, y compris quand `Decision.writes` est vide (RD11.1) : la fraîcheur d'un profil n'est jamais une information que le Domain porte.

---

## RD12 — Événements et effets

Un seul type d'événement : `RISK_CHANGED` (`RiskChanged{from_level, to_level, score}`, déjà défini dans `risk/contracts/events.py` généré). Aucun effet extérieur (`ExternalEffect`) : le Risk Domain n'envoie rien, ne publie rien hors de l'outbox.

---

## RD13 — Cas nominaux

Repris de §2.7 (`golden_cases.json['risk']`, déjà exécutable dans `reference_model`), plus les cas de chaîne (hystérésis, snapshot vs événement) propres au Domain :

| # | Cas | Attendu |
|---|---|---|
| RN1 | G1 : nouveau client, `D=3, n=0, Eo=100000, C=1000000` | score 6, `LOW`, `confidence=LOW` (n<3) |
| RN2 | G2 : mauvais payeur chronique | score 53, `HIGH` |
| RN3 | G3 : situation critique | score 98, `CRITICAL` |
| RN4 | G4 : bon payeur | score 2, `LOW` |
| RN5 | G5 : historique insuffisant, gros retard | score 41, `MEDIUM`, `confidence=LOW` |
| RN6 | premier calcul (aucun profil antérieur) | création : `StateWrite(expect=None, set={score, level, model_version, factors})` — le Domain s'arrête là (RD11.2, option (b) DV2-9) ; **aucun** `RISK_CHANGED` (§ DV2-7 : `from_level` est un `str` non optionnel dans le contrat gelé, rien à y mettre à la création) |
| RN7 | recalcul, `NormalizedRiskInputs` identique à `previous.normalized_inputs` (donc `input_hash` identique une fois calculé côté Application) | `Decision` vide (RD11.1) ; l'Application écrit seule `computed_at`, aucune duplication en historique, aucun événement |
| RN8 | recalcul, `NormalizedRiskInputs` différent, même niveau publié | `StateWrite` non vide (RD11.2) ; l'Application, en le constatant, duplique en historique (DV2-9) ; aucun événement |
| RN9 | recalcul, niveau publié change (`MEDIUM→HIGH`) | `StateWrite` non vide + `RISK_CHANGED(MEDIUM, HIGH, score)` ; l'Application duplique en historique de la même façon |
| RN10 | séquence `44,46,49,51,48,47,49,50,46,45,44` (exemple du §1.3, seuil `HIGH=50`) | motif `MMMHHHHHMMM` : exactement 2 changements de niveau publié (2 `RISK_CHANGED`) |
| RN11 | client sans facture ouverte mais avec historique | `D=0, Eo=0` ; score reflète uniquement l'historique |
| RN12 | client dont les factures sont toutes `VOID` | éligible (RD3), score 0 partout, `LOW` |

---

## RD14 — Contre-exemples

| # | Cas | Attendu |
|---|---|---|
| RC1 | client sans aucune facture émise (`has_ever_issued=False`) | pas de profil, aucune écriture, `outcome=PROCESSED` |
| RC2 | modèle demandé différent de `risk-1.0` | `RISK_MODEL_UNKNOWN` — **structurel** (l'Application ne doit jamais présenter un autre modèle au Domain V1, RD-note : ce code n'existe que si un jour plusieurs versions coexistent ; en V1, `PreconditionViolated`, pas `DomainError`, comme les autres défauts d'appelant) |
| RC3 | `as_of` naïf | `PreconditionViolated` (TD23) |
| RC4 | `C ≤ 0` | facteur exposition = 0 (pas une erreur, RD4 le couvre déjà) |
| RC5 | garde d'état violée en écriture (profil modifié entre la lecture et l'écriture) | `CONCURRENT_MODIFICATION`, rejouable — géré par l'infrastructure (`row_writer`), pas par le Domain lui-même (comme en tranche 1) |

---

## RD15 — Cas limites

| # | Cas | Attendu |
|---|---|---|
| RL1 | `n` exactement 3 | `L`, `M` utilisés (pas la branche « historique insuffisant ») |
| RL2 | `n` = 2 | historique = 0, `confidence=LOW` |
| RL3 | `D` = 60 puis 61 | 26 puis 30 (bornes de tranche) |
| RL4 | `D` = 17 puis 18 (même tranche, 16–30) | même `NormalizedRiskInputs`, mêmes `factors` (§2.7, propriété vérifiée) ; même `input_hash` une fois calculé côté Application |
| RL5 | `D` = 15 puis 16 (tranches différentes) | `NormalizedRiskInputs` distincts (donc `input_hash` distincts côté Application) |
| RL6 | `T` inconnu (moins de 2 factures dans l'une des fenêtres de 90 jours) | facteur tendance = 0, **sans** `confidence=LOW` (RP-G ne s'applique qu'à `n<3` pour `L`/`M` ; `T` a sa propre condition d'ignorance, indépendante) |
| RL7 | `M` négatif (paiement en avance) | `max(M,0)` avant plafonnement à 30 : contribution 0 si `M<0` |
| RL8 | `M` = 35 | plafonné à 30 avant division |
| RL9 | score = 100 exactement (bornes maximales de tous les facteurs) | `CRITICAL`, jamais > 100 |
| RL10 | séquence à la limite de l'hystérésis (`score+3` égal exactement au seuil) | **corrigé (trouvé en codant, aucun impact sur le code) : reste au niveau publié**, ne descend pas. `niveau()` (RD6) compare par `≥` ; « rester sous le seuil » (RD7) est donc l'inverse strict — `score+3 < seuil` fait descendre, `score+3 ≥ seuil` (dont l'égalité) fait rester. Confirmé contre `verqia_models.stabilise` (gelé, antérieur à cette tranche) : `stabilise(47, HIGH)=HIGH` (47+3=50=seuil, reste), `stabilise(46, HIGH)=MEDIUM` (46+3=49<50, descend). La formulation précédente de cette ligne (« égal descend ») était une erreur de glose introduite lors de la rédaction de ce document, jamais présente dans le code ni dans `risk_ref.py`. |
| RL11 | deux recalculs consécutifs avec le même `as_of` (rejeu) | même décision (IN1, déterminisme) |
| RL12 | client avec une seule facture, ouverte ET en retard ET soldée dans les 12 mois (cas impossible en pratique : une facture soldée n'est plus « ouverte » sauf `PARTIALLY_PAID`) | à vérifier : une facture `PARTIALLY_PAID` reste ouverte (`is_open`) ET peut ne pas être « soldée » (`settled_on` est `None` tant que `settlement_state≠PAID`) — **pas de double-comptage possible** entre `open_invoices` et `settled_invoices_12m`, une facture n'est jamais dans les deux (`is_open` implique `settlement_state≠PAID` implique `settled_on=None`, IF3) |

---

## RD16 — Invariants (registre à prouver, comme `DOMAIN_INVARIANTS` de la tranche 1)

| # | Invariant | Nature | Source |
|---|---|---|---|
| RI1 | `0 ≤ score ≤ 100`, maximum atteignable | E | §2.7 |
| RI2 | chaque facteur dans ses bornes déclarées (RD4) | E | §2.3 |
| RI3 | `score` monotone croissant en chacune de ses six composantes | D | §7 (testable) |
| RI4 | `n < 3` ⇒ `history_late_pts = history_delay_pts = 0` et `confidence = LOW` | E | RP-G |
| RI5 | (Domain) `NormalizedRiskInputs` égal ⇔ toutes les entrées normalisées égales par valeur, RD11.1 déclenché — **sans hachage** | D | RP14, § DV2-8 |
| RI5bis | (Application, hors Domain) `input_hash` égal ⇔ `NormalizedRiskInputs` égal — propriété de la fonction de hachage, pas du Domain | X | RP14, § DV2-8 |
| RI6 | `NormalizedRiskInputs` (donc `input_hash` une fois calculé) stable à l'intérieur d'une tranche de points, distinct entre tranches, sensible au niveau publié précédent | D | §2.7, §7 |
| RI7 | `factors` ne contient jamais de valeur brute ni de taille d'échantillon | E | RP14 |
| RI8 | niveau publié = fonction pure de `(score, niveau publié précédent)`, jamais du score seul | T | RD7/RD8 |
| RI9 | pas de plafond en Risk (à la différence de Priority) : niveau publié = niveau stabilisé | T | §3.4 vs §1.3 |
| RI10 | `RISK_CHANGED` émis **si et seulement si** le niveau publié change **et** qu'un niveau précédent existait (§ DV2-7) | T | Invariants §8 |
| RI11 | (Domain) `Decision.writes` non vide **si et seulement si** `NormalizedRiskInputs` diffère de `previous.normalized_inputs` | T | Invariants §8, § DV2-8 |
| RI12 | (Domain) `NormalizedRiskInputs` inchangé ⇒ `Decision` totalement vide (`writes=(), events=()`) ; `computed_at` n'apparaît dans AUCUNE `Decision`, il est de la seule responsabilité de l'Application (RD11.4) | T | Invariants §8, § DV2-8 |
| RI13 | déterminisme (IN1), non-mutation de l'entrée (IN2), indépendance de l'horloge système (IN3) | D | Domain V1 §5.3 (repris tel quel) |
| RI14 | conservation de l'éligibilité : un client `has_ever_issued=False` n'a jamais de profil, un client `True` peut avoir score 0 | E | RD3 |

---

## RD17 — Correspondance avec le modèle de référence

`reference_model/verqia_models.py` contient déjà `risk_points`, `risk_score`, `stabilise`, `level_index`, `risk_evaluate`, `input_hash` : **exécutables et testés** (25 tests dans `test_models.py`, dont `TestRisk` : bornes, monotonie, historique insuffisant, hystérésis, exemple documenté, stabilité du hash par tranche, contenu du snapshot). `golden_cases.json['risk']` contient G1–G5 avec `factors`, `input_hash`, `inputs` bruts.

**Ce que le Domain V1 (Risk) doit reproduire exactement** : `risk_evaluate(organization_id, customer_id, previous_level, D, n, L, M, B, Eo, C, R, T) -> {score, level, level_index, factors, input_hash}` — étant entendu que, côté Domain, ce qui correspond à `factors`/`input_hash` s'arrête à `NormalizedRiskInputs`/`factors` (RD10.1), `input_hash` restant une affaire d'Application (RD10.2, § DV2-8). Le Domain reçoit `RiskInput` (RD2.3), en dérive lui-même `(D, n, L, M, B, Eo, C, R, T)` par agrégation (RD2.2), puis applique la **même** fonction. Les tests différentiels (comme en tranche 1, DT-R) comparent :
1. le Domain contre `risk_evaluate` directement (mêmes `D…T` en entrée) — prouve que la fonction pure est fidèle ;
2. l'agrégation `open_invoices`/`settled_invoices_12m` → `(D, Eo, n, L, M)` contre une fonction naïve indépendante écrite dans une **nouvelle** référence (`reference_model/risk_ref.py`, dans l'esprit de `finance_ref.py`, V8) — prouve que l'agrégation du Domain est correcte, pas seulement que la formule de score l'est.

`golden_cases.json` reste la référence du **score** ; `risk_ref.py` (à écrire si validé) devient la référence de l'**agrégation** — c'est la partie **nouvelle** de cette tranche, absente de `reference_model` aujourd'hui (le modèle existant part déjà de `D, n, L, M…`, jamais d'une liste de factures).

---

## RD18 — Plan de tests (après validation, avant code)

| Famille | Contenu | Ordre de grandeur |
|---|---|---|
| DT-A tables | seuils de niveaux, tranches de points, bornes de chaque facteur | 15 |
| DT-B agrégation | `D`, `Eo`, `n`, `L`, `M`, `T` à partir de listes d'`InvoiceFacts` construites à la main (RD2.2) ; cas limites RL1, RL2, RL12 | 20 |
| DT-C nominaux | RN1 à RN12 | 20 |
| DT-D refus | RC1 à RC5 | 10 |
| DT-E limites | RL1 à RL12 | 15 |
| DT-F propriétés | séquences aléatoires de recalculs (score, niveau, hash, snapshot/événement) ; 200 séquences pour l'hystérésis (comme `test_hysteresis_reduces_level_changes` existant) | 8 propriétés |
| DT-G pureté | AR-01, AR-02, aucun flottant, entrée en lecture seule, instant naïf refusé (repris de `test_dt_purity_contracts.py`) | 8 |
| DT-H raccord | écritures ⊂ `risk.profile` ; événements ⊂ `('RISK_CHANGED',)` ; codes ⊂ catalogue | 6 |
| DT-R référentiel | contre `risk_evaluate` (score) et `risk_ref.py` (agrégation, si créé) ; les 5 cas d'or reproduits à l'identique | 10 |
| DT-RUN | le vrai coureur (services C12 non nécessaires ici : Risk n'a pas de C12) — un cas nominal de bout en bout, versions, idempotence sur `input_hash` | 10 |

---

## Validation : contradictions et gaps trouvés (DV2)

Aucun n'est corrigé dans le Domain lui-même. **DV2-1 à DV2-9 arbitrés et confirmés le 2026-09-22** (tableau ci-dessous) ; leurs résolutions sont reflétées dans RD1 à RD16. Deux imprécisions supplémentaires (sans rang DV2, aucune ne touchant un contrat gelé) ont été corrigées silencieusement : `has_ever_issued` manquait de la structure `RiskInput` alors que RD3 le requiert ; `timezone` était attribué par erreur à `OrgSettings` alors qu'il vient de `CalendarReader` (déjà consommé par `risk`).

| Point | Décision | Statut |
|---|---|---|
| DV2-1 | `RecomputeRisk` doit déclarer explicitement ses lectures, une fois DV2-2 à DV2-5 fixés | **AMENDEMENT** (au code, pas à ce document) |
| DV2-2 | Le Domain reçoit des collections de faits déjà bornées par l'Application | **VALIDÉ** — RD2.3, RD2.4 |
| DV2-3 | `critical_amount_minor` ne vient pas de `CalendarReader` | **CORRIGÉ** — `RiskParameters` dédié, RD2.3/RD2.4 |
| DV2-4 | Nouveau type `RiskPaymentFacts`, séparé de `PaymentFacts` gelé | **VALIDÉ** — aucun amendement de la tranche 1 |
| DV2-5 | `PromiseRiskFacts` avec fournisseur potentiellement stub, jamais de zéro silencieux en production | **VALIDÉ sous condition** — § ci-dessous |
| DV2-6 | `PROCESSED`, jamais `REPLAY`, pour un handler | **VALIDÉ** — RD11.1 ; Invariants §8 à corriger (hors Domain) |
| DV2-7 | Aucun `RISK_CHANGED` à la première publication | **VALIDÉ** — RD11.2 |
| DV2-8 | `input_hash` ne doit être ni lu ni calculé par le Domain | **CONFIRMÉ le 2026-09-22** |
| DV2-9 | `Append('risk_snapshots', ...)` nomme une table LOG, ce que RD1.1 interdit ; la tranche 1 traite déjà les tables LOG autrement | **ARBITRÉ le 2026-09-22, option (b)** — RD11.2 |

### DV2-1 — `RecomputeRisk` (et `RequestRiskRecalc`, `RequestDailyRiskRefresh`) ne déclarent aucune lecture

| | |
|---|---|
| **Source contradictoire** | Le registre gelé (`commands.py`) donne `reads=()` à `RecomputeRisk`, alors que RD2 exige au moins cinq lectures (organisation, factures ouvertes, factures soldées 12 mois, promesses, paiements). Même motif que V2/B3-b en tranche 1. |
| **Comportement observé** | Le coureur refuserait tout `call()` non déclaré (`call_not_declared`). |
| **Impact** | Bloque l'exécution réelle du cas d'usage. Aucun impact sur la fonction pure. |
| **Décision (2026-09-22)** | **Amendement fait : B5** (`architecture_registry/application_freeze.py`, 2026-09-22), dérivé exactement de la signature de `reference_model/risk_ref.py::evaluate_risk` — ni plus ni moins que ce que la référence indépendante consomme. Sept lectures déclarées pour `RecomputeRisk` : `organizations.CalendarReader` (fuseau, RD2.4), `organizations.OrgSettings` (`critical_amount_minor`, DV2-3), `invoices.OpenInvoicesOfCustomer` (`D`, `Eo`, premier consommateur), `invoices.SettledInvoicesOfCustomer` (`n`, `L`, `M`, `T` — nouvelle requête), `invoices.EverIssuedOfCustomer` (`has_ever_issued`, RD3 — nouvelle requête), `payments.ReversedPaymentsOfCustomer` (`R`, via `RiskPaymentFacts`, DV2-4 — nouvelle requête), `promises.BrokenPromisesOfCustomer` (`B`, via `PromiseRiskFacts`, DV2-5 — nouvelle requête). **`customers.CustomerFacts` explicitement exclu** : `risk-1.0` ne lit aucun fait client (correction d'une hypothèse antérieure trop large). `risk` perd sa dépendance déclarée à `customers`. Reste à faire (hors B5) : les types niveau C `RiskParameters`/`RiskPaymentFacts`/`PromiseRiskFacts` n'existent aujourd'hui que comme classes `Query` générées ; leurs formes de données concrètes (DV2-6/RD2.6) seront écrites à la main au moment du code Domain, pas du registre. |

### DV2-2 — les dépendances déclarées sont des lectures par entité, pas des lectures agrégées et bornées dans le temps

| | |
|---|---|
| **Source contradictoire** | Le registre déclare `risk → invoices.InvoiceFacts, payments.PaymentFacts` (requêtes par entité, celles que la tranche 1 a construites pour une facture ou un paiement précis). RD2 exige des lectures **par client**, **bornées à une fenêtre de temps** (factures ouvertes ; factures soldées dans les 12 derniers mois). `invoices.OpenInvoicesOfCustomer` existe, déclarée, mais **sans consommateur** (`CONSUMERS: ClassVar[tuple[str, ...]] = ()`) et ne couvre que les factures ouvertes, pas l'historique soldé. |
| **Comportement observé** | Aucune requête gelée ne rend directement `RiskInput.open_invoices` ni `RiskInput.settled_invoices_12m`. |
| **Impact** | Bloque l'implémentation de la lecture (P7), pas le Domain. |
| **Décision (2026-09-22)** | **Validé, option (a).** Le Domain reste un agrégateur pur sur des listes fournies par l'Application, via `invoices.OpenInvoicesOfCustomer` (réutilisée, premier consommateur) et une lecture bornée dans le temps équivalente pour les factures soldées (RD2.3, RD2.4). Aucune requête n'agrège `D`/`Eo`/`n`/`L`/`M` en dehors du Domain. |

### DV2-3 — le contenu de `organizations.CalendarReader` n'est écrit nulle part, mais trois modules en dépendent pour des données non calendaires

| | |
|---|---|
| **Source contradictoire** | `risk`, `priority`, `cashflow` et `collection` dépendent tous **uniquement** de `organizations.CalendarReader`, jamais de `organizations.OrgSettings` (dont le seul consommateur déclaré est `notifications`). Or `critical_amount_minor` (Risk `C`, Priority, Collection Engine règle de niveau 5) et `due_soon_days` sont des colonnes d'`org_settings`, pas du calendrier. |
| **Comportement observé** | Aucun document ne fixe la forme niveau C de `CalendarReader` ; l'hypothèse la plus cohérente avec les quatre dépendances observées est que `CalendarReader` est en réalité « les faits de référence de l'organisation pour les moteurs » (fuseau, jours ouvrés, jours fériés, `due_soon_days`, `critical_amount_minor`), pas seulement un calendrier. |
| **Décision (2026-09-22)** | **Corrigé : `CalendarReader` ne porte PAS `critical_amount_minor`** (refus explicite du « conteneur artificiel »/God Port). `risk` gagne une dépendance déclarée `organizations.OrgSettings`, dont `critical_amount_minor` fait déjà partie (Data Contract §1.4) : il suffit d'élargir `OrgSettings.CONSUMERS` (aujourd'hui `('notifications',)`) pour y ajouter `'risk'`. **Rien n'est inventé** : la requête existe déjà, seul son cercle de consommateurs s'élargit. `CalendarReader`, que `risk` consomme **déjà** (fuseau, jours ouvrés, jours fériés — nécessaire à RD2.4), garde ce rôle strictement calendaire et reste la source de `timezone`. Le Domain reçoit les deux valeurs déjà résolues et assemblées, sous la forme dédiée `RiskParameters` (RD2.3, RD2.4) — jamais un objet `OrgSettings` ou `CalendarReader` générique passé tel quel (ce qui recréerait, côté Domain cette fois, le même risque de conteneur fourre-tout). `priority`, `cashflow`, `collection` devront faire la même demande explicite quand vient leur tour, pas par anticipation. |

### DV2-4 — `R` (paiements annulés) exige une donnée absente de `PaymentFacts`, gelé en tranche 1

| | |
|---|---|
| **Source contradictoire** | `customer.reversed_payments_12m` vient de `payment_reversals.reversed_at`. `payments.contracts.facts.PaymentFacts` (notre construction, **gelée** dans `domain_freeze.json` de la tranche 1) ne porte pas `reversed_at` ; elle est de plus **par paiement**, pas agrégée par client. |
| **Comportement observé** | Aucun moyen de lire `R` sans toucher à une surface déjà gelée. |
| **Impact** | Seule modification qui aurait pu **rouvrir** un gel existant (celui de la tranche 1) si mal traitée. |
| **Décision (2026-09-22)** | **Validé, option (b) confirmée : `PaymentFacts` (gelé) reste intact, aucun amendement de la tranche 1.** Un type séparé, `RiskPaymentFacts` (module `payments`, nouveau contrat, hors du gel de la tranche 1 puisqu'il n'en fait pas partie), porte exactement ce que `risk-1.0` consomme : `reversed_at` (la date, pour le bornage temporel fait par l'Application). Le barème lui-même n'utilise que le **compte** (`R = len(reversed_payments)`) ; le Domain ne lit ni `amount_minor` ni `currency` sur ce type (RD2.3) — inutile de les y porter tant qu'aucun facteur ne les consomme. |

### DV2-5 — `B` (promesses rompues) dépend d'un Domain qui n'existe pas encore

| | |
|---|---|
| **Constat** | Le Risk Engine (RP, gelé) exige `customer.broken_promises_12m`, donc des données de `promises`. L'ordre de tranches donné (Risk → Priority → Action → Réconciliation → Cashflow) ne mentionne pas Promises. |
| **Décision (2026-09-22)** | **Validé sous condition.** Le Risk Domain consomme un **port de faits** explicite, `promises.PromiseRiskFacts` (RD2.6), sans connaître son fournisseur. Tant que le Domain `promises` n'existe pas, l'implémentation de ce port peut être un **fournisseur STUB**, mais à deux conditions verrouillées : (1) le stub vit **uniquement** dans le harnais de test/référence (`domain_tests`, jamais dans le code de production branché sur l'infrastructure réelle) ; (2) aucun code de production ne doit pouvoir tourner avec ce stub sans qu'il soit **visible et documenté comme tel** — pas un `return 0` silencieux dans un chemin qui ressemble à une implémentation réelle. Concrètement : `RecomputeRisk` n'est pas mis en service tant que `payments.RiskPaymentFacts` (DV2-4) **et** un fournisseur réel (pas stub) de `promises.PromiseRiskFacts` n'existent pas tous les deux — ce qui reporte la **mise en production** du Risk Engine, pas nécessairement son **code et ses tests** (qui peuvent avancer contre le stub, avec cette limite écrite noir sur blanc). Promises n'est **pas** inséré avant Risk dans l'ordre des tranches sur cette seule base ; la question est reportée au moment de brancher réellement `RecomputeRisk` sur l'infrastructure. |

### DV2-7 — `RiskChanged.from_level` est un `str` non optionnel : la première décision d'un client ne peut pas produire cet événement

| | |
|---|---|
| **Source contradictoire** | `risk/contracts/events.py` (généré, gelé) : `RiskChanged(from_level: str, to_level: str, score: int)`, sans `None` possible. RP15/§1.3 fondent la chaîne de calcul sur « niveau publié précédent, **ou absent, premier calcul** » — donc un premier calcul est prévu et légitime, mais son résultat ne peut pas remplir `from_level`. |
| **Comportement observé** | Aucun, tant que le code ne tente pas de construire `RiskChanged(from_level=None, ...)` (lèverait une erreur de type, ou pire, un `str` invalide comme `"None"` si construit sans y penser). |
| **Impact** | Si non tranché, un premier calcul soit plante à la construction de l'événement, soit invente une valeur de `from_level` non spécifiée (ex. `"NONE"` ou `"UNKNOWN"`), ce qui serait une décision métier nouvelle et non documentée. |
| **Décision (2026-09-22)** | **Validé, option (a) : aucun événement à la création.** Seul le profil est écrit par le Domain (RD11.2) ; le premier historique en découle côté Application (DV2-9). Un `RISK_CHANGED(from_level=LOW, to_level=MEDIUM, ...)` ne peut survenir qu'à partir d'un **second** calcul, quand `previous` existe réellement. Aucun amendement de `risk/contracts/events.py`. |

### DV2-6 — Invariants §8 nomme « REPLAY » une issue de handler, alors que ce mot est réservé aux commandes

| | |
|---|---|
| **Source contradictoire** | `INVARIANTS_V1.md` §8 : « Issues non fautives (C11) : SKIPPED pour un événement plus ancien que l'état courant ; **REPLAY** pour une entrée identique (`input_hash`). » Le contrat Application gelé donne aux handlers exactement `(PROCESSED, SKIPPED, RETRYING, DEAD)` — pas `REPLAY`, réservé aux commandes à clé d'idempotence (établi en tranche 1 : « REPLAY appartient au coureur »). |
| **Comportement observé** | Aucun, tant que personne ne code littéralement `outcome='REPLAY'` pour un handler (le coureur le refuserait, `outcome_runner_owned`, comme en tranche 1). |
| **Décision (2026-09-22)** | **Validé : `PROCESSED`, jamais `REPLAY`** (RD11.1). `SKIPPED` reste attribué à `RequestRiskRecalc` (déduplication des `refresh_events`), pas à `RecomputeRisk`. Correction demandée, **hors Domain** : `INVARIANTS_V1.md` §8 sera reformulé pour employer le vocabulaire contractuel exact (« entrée normalisée inchangée ⇒ `PROCESSED`, `computed_at` seul mis à jour »), au moment de l'amendement de code (DV2-1), pas dans ce document de spécification. |

---

### DV2-8 — `input_hash` avait fui dans le Domain comme mécanisme de décision (trouvé en seconde lecture)

| | |
|---|---|
| **Source du problème** | La première version de ce document (avant l'arbitrage) faisait dépendre le comportement du Domain (RD11.1/RD11.2 d'origine) de la comparaison de deux `input_hash`, et laissait le Domain calculer ce hash (RD10 d'origine : « `input_hash = SHA256(...)` », sans préciser qui l'exécute). C'est exactement le type de fuite que l'arbitrage demandait de traquer : le Domain « apprenait » un **mécanisme de persistance** (hachage, clé d'unicité `risk_snapshots`) pour décider d'une branche pourtant purement métier (« est-ce que quelque chose a changé ? »). |
| **Pourquoi c'est un problème** | Cela violerait directement la liste RD1.1 (« `input_hash` comme mécanisme de persistance », « `risk_snapshots` comme table ») que l'arbitrage vient de verrouiller, et romprait la couche définie dans le schéma « Application / Risk Engine » vs « RISK DOMAIN » du verdict. |
| **Correction appliquée dans cette révision** | Le Domain compare des **valeurs** (`NormalizedRiskInputs`, RD10.1), jamais un hash. `input_hash` devient un artefact **dérivé**, calculé par l'Application **après** la `Decision`, uniquement pour la clé d'unicité de stockage (RD10.2). L'égalité de valeur est, par construction, strictement équivalente à l'égalité de hash (RI5bis) : aucune information n'est perdue, aucune règle n'est dupliquée. `computed_at` et `trigger_event_id` deviennent explicitement des responsabilités de l'Application, **toujours** exécutées, y compris quand `Decision` est vide (RD11.1, RD11.4). |
| **Ce qui reste à confirmer** | *(confirmé par vous le 2026-09-22.)* |

---

### DV2-9 — `risk_snapshots` (LOG) : `Append` nomme littéralement une table, ce que RD1.1 vient d'interdire ; la tranche 1 traite déjà les LOG autrement (trouvé en seconde lecture complète)

| | |
|---|---|
| **Source du problème** | RD1.1 (verrouillé par votre arbitrage) interdit au Domain de connaître « `risk_snapshots` comme table ». Pourtant RD11.2 (jusqu'à cette section) fait produire par le Domain un `Append('risk_snapshots', {...})`, qui nomme cette table en toutes lettres — contradiction directe et littérale à l'intérieur du même document. |
| **Ce que dit le précédent de la tranche 1 (gelé)** | `kernel/decision.py` distingue déjà deux mécanismes, et ce n'est pas un hasard : `Append(table, row)` sert à « une ligne ajoutée à une table append-only **ou enfant** (lignes de facture, allocations, reversals de paiement) » — des faits métier **indépendants**, pas la trace d'un autre changement. `HistoryRow(dimension, from_state, to_state, reason)`, porté par `RowChange.history`, sert explicitly à « `invoice_state_history` » — une table d'historique qui ne fait que **mirer** une transition déjà écrite ailleurs. Le Data Contract classe `risk_snapshots` **Nature : LOG**, exactement comme `invoice_state_history` (§7.2 : « mêmes colonnes métier que 7.1 [risk_profiles] » — un miroir, pas un fait indépendant). `risk_snapshots` est donc, par nature, du côté de `HistoryRow`, pas du côté de `Append`. |
| **Pourquoi je ne tranche pas seul** | `HistoryRow` ne porte que `dimension/from_state/to_state/reason` — un couple d'état, pas un score ni des `factors`. Le réutiliser tel quel ne suffit pas pour `risk_snapshots`. Deux voies s'ouvrent, et l'une d'elles touche `kernel/decision.py`, **gelé** au titre de la tranche 1 (`domain_freeze.json`) : exactement le type de décision que DV2-4 a refusé de prendre sans vous pour `PaymentFacts`. |
| **Options** | **(a)** généraliser `HistoryRow` (ou ajouter un type frère, ex. `SnapshotRow`, à `kernel/decision.py`) pour porter ce qu'un LOG « miroir » a besoin de conserver au-delà d'un couple d'état — amendement du noyau de la tranche 1, donc un nouveau tour de `domain_freeze.py AMENDMENTS`, comme B3/B4 l'ont fait pour le registre d'architecture, mais cette fois pour le Domain lui-même. **(b)** Le Domain ne décide pas explicitement d'« ajouter une ligne de log » : il expose seulement le nouvel état complet (`score`, `level`, `factors`, `NormalizedRiskInputs`) dans son `Decision.result` ou dans le `set` du `StateWrite('risk.profile', ...)`, et c'est l'Application — jamais le Domain — qui, en observant que `NormalizedRiskInputs` a changé, décide de dupliquer la ligne courante dans `risk_snapshots`. Le Domain ne nomme alors JAMAIS `risk_snapshots`, dans aucun sens du terme. **(c)** Accepter que `risk_snapshots`, malgré sa nature LOG au Data Contract, soit traité comme `payment_allocations` (via `Append`), en resserrant la lecture de RD1.1 à « le Domain ne décide pas des colonnes techniques d'unicité/partitionnement de la table », pas de son nom — ce qui n'exige aucun amendement, mais s'écarte du précédent déjà établi pour les LOG sans justification autre que la commodité. |
| **Recommandation** | **(b)**. Elle ne touche ni le registre ni `kernel/decision.py`, respecte RD1.1 à la lettre, et déplace la seule décision technique restante (« dupliquer en LOG ») là où RD1.1 la met déjà : l'Application. Le prix : le Domain ne « décide » plus explicitement d'écrire dans `risk_snapshots` — il décide seulement que l'état a changé, ce qui est suffisant, puisque §1.1 du contrat gelé dit qu'un nouveau snapshot est créé **précisément quand** les entrées normalisées changent, une condition que le Domain établit déjà (RD11.2) sans avoir besoin de nommer la table qui en résulte. |
| **Décision (2026-09-22)** | **Validé, option (b).** Aucun amendement de `kernel/decision.py`, aucune réouverture du gel de la tranche 1. Le Domain expose son nouvel état (`score`, `level`, `factors`, dans le `set` du `StateWrite('risk.profile', ...)`) ; l'Application, en constatant le changement, écrit le profil, duplique en LOG (`risk_snapshots`), publie l'événement le cas échéant, puis l'audit si requis — dans cet ordre, entièrement de son ressort. RD11.2, RD13 (RN6 à RN9) et DV2-7 sont mis à jour en conséquence dans ce document. |

---

## Contrôle de clôture (demandé avec l'arbitrage de DV2-9)

Recherche systématique, dans tout le document, des mentions de `table`, `repository`/`Repository`, `ORM`, `risk_snapshots`, `input_hash`, `transaction`, `verrou`/`lock`, restreinte au texte qui décrit ce que le **Domain** fait ou reçoit (RD1 à RD16 ; RD17/RD18 et la section Validation en sont exclus, puisqu'ils parlent légitimement de l'Application, des tests et de la persistance) :

| Occurrence trouvée | Verdict |
|---|---|
| RD1, ligne « le verrou consultatif… et la transaction (P5, P6) » | Correctement scopée : c'est la liste de ce qui reste **hors** du Domain, pas une connaissance du Domain. |
| RD1.1 | La liste d'interdiction elle-même ; elle NOMME ces notions pour les exclure, ne les utilise pas comme mécanisme. |
| RD2.4, « PostgreSQL ou un calendrier applicatif » | Négation explicite (« n'est **pas** »). |
| RD10.1/RD10.2 | `input_hash` y est traité explicitement comme **hors Domain** (§ DV2-8) ; aucune formule n'est exécutée par le Domain. |
| RD11.1 « aucun `Append` » | Confirme l'absence, ne l'emploie pas. |
| RD11.2 (révisée) | Ne nomme plus `risk_snapshots` ; s'arrête à `StateWrite('risk.profile', ...)` (§ DV2-9). |
| RD11.4 | Liste de ce que le Domain ne pose jamais — négation, pas usage. |
| RD13 (RN6 à RN9, révisées) | Ne mentionnent plus `Append('risk_snapshots', ...)` ; décrivent la conséquence côté Application séparément. |

**Aucune fuite résiduelle.** La frontière Domain/Application est cohérente de bout en bout.

---

## Prochaines étapes (même suite que la tranche 1)

La spécification est validée ; ce n'est pas le gel du Domain. Restent, dans l'ordre déjà éprouvé :

| Étape | État |
|---|---|
| Spécification (RD1–RD18), arbitrages DV2-1 à DV2-9 | **faite** |
| Référence indépendante `reference_model/risk_ref.py` (agrégation `InvoiceFacts`/`RiskPaymentFacts`/`PromiseRiskFacts` → `D, n, L, M, T, B, R`, naïve, sans import du Domain ni de `verqia_models`) + cas d'or | **faite** (37 tests, `golden_risk.json`) |
| Amendements Registry/Contracts (B5 : sept lectures de `RecomputeRisk`, DV2-1 ; `OrgSettings.CONSUMERS` élargi, DV2-3 ; quatre nouvelles requêtes `invoices`/`payments`/`promises`) | **faite** |
| Types niveau C écrits à la main (`RiskParameters`, `RiskPaymentFacts`, `PromiseRiskFacts`, DV2-4/DV2-5/DV2-6) | à faire |
| Code du Domain (`verqia/risk/domain/`) | à faire |
| Tests Domain (DT-A à DT-H, RD18) + tests différentiels contre `risk_evaluate` et `risk_ref.py` (DT-R) | à faire |
| Porte de fermeture (`DOMAIN_INVARIANTS` risque, RI1 à RI14, mutations) | à faire |
| Coureur (composition avec `risk.profile`, aucun service C12 pour Risk) | à faire |
| Empreinte de gel de la tranche Risk, puis gel | à faire |

RD1 à RD18 suivent strictement le texte déjà gelé de `RISK_PRIORITY_CASHFLOW_V1.md` : aucune formule n'est réinventée. Les seules additions sont des **types de faits** (RD2.6) et une **frontière explicite** (RD1.1) — jamais une règle de score.
