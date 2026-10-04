# R-12 — Création dédupliquée → `REPLAY` : conception Application / coureur

Statut : **DÉCIDÉ (A+C) · IMPLÉMENTÉ · VALIDÉ SUR POSTGRESQL RÉEL (PG-11) — NON CLOS.** Fermeture subordonnée à une revue de fermeture et à **R12-O1 (OUVERT)**. Date : 2026-10-04.
Portée : `application_runner/` et une expérience PostgreSQL séparée. **Aucun** document métier gelé modifié, **aucune** primitive ni aucun Domain modifié, **ni A1 ni A4 construits**, matrice non touchée (A10 compris).

> **A est un fast path ; C est le mécanisme de correction concurrente.** La contrainte d'unicité de la base reste l'**autorité** de la concurrence : A n'est qu'une économie (ne pas appeler le Domain quand l'objet existe déjà) ; sans A, C suffit à garantir le résultat ; sans C, A ne garantit rien sous concurrence. **Ne jamais supprimer C au motif que A existe.**

## 1. Sources

| Réf. | Contenu | Nature |
|---|---|---|
| ENGINE_CONTRACTS §5 | « Création d'action \| dedup_key … \| REPLAY » ; « Notification \| dedup_key \| REPLAY » | EXPLICITE |
| ENGINE_CONTRACTS §0.3 | `REPLAY` = « déjà fait ; l'objet existant est renvoyé » | EXPLICITE |
| DATA_CONTRACT §6.1 (`collection_actions`) | UQ partiel `(organization_id, dedup_key) WHERE status NOT IN ('CANCELLED','SUPPRESSED')` ; `DONE` / `FAILED` bloquent | EXPLICITE |
| DATA_CONTRACT §6.2 | `dedup_key` = `{invoice_id}:{type}:L{level}:C{cycle}:R{occurrence}` ; manuelle : `manual:{idempotency_key}` | EXPLICITE |
| DATA_CONTRACT (purges) | `idempotency_keys` purgées après `expires_at` (« proposition à confirmer ») | EXPLICITE (statut : proposition) |
| TECHNICAL_ARCHITECTURE TD16 | chaque contrainte reçoit un **nom stable** (`uq_…`) ; le nom rend la traduction possible (TD19) | EXPLICITE |
| TECHNICAL_ARCHITECTURE TD19 | traduction par **SQLSTATE et nom de contrainte** : « violation d'unicité de `dedup_key` → `REPLAY` » ; une violation non arrêtée par le Domain est un défaut → `INTERNAL` | EXPLICITE |
| TECHNICAL_ARCHITECTURE TA-08 | « chaque contrainte nommée produit le code attendu, y compris les erreurs levées au COMMIT » | EXPLICITE |
| TECHNICAL_ARCHITECTURE TD32 | la clé d'idempotence est la première écriture de l'unité | EXPLICITE |
| Application Contract (specs générées) | A1 `idempotency='dedup_key'`, A4 `idempotency='manual:{clé}'` ; issues `OK, REPLAY, SKIPPED, DEFERRED` ; portée de clé `ORGANIZATION` ; aucune des deux ne liste `CONCURRENT_MODIFICATION` | EXPLICITE |
| P4, AP-12 | `REPLAY` appartient au coureur ; aucun Domain ne le propose | EXPLICITE |
| PG-07 (TA-12) | un `INSERT` sur une clé insérée par une transaction non validée attend ; après validation, violation d'unicité | PROUVÉ (PostgreSQL réel) |
| **PG-11** (ce document, §5) | la course A+C complète sur PostgreSQL 16.2 réel | PROUVÉ / CONSTATÉ (PostgreSQL réel) |

## 2. Les sept questions

### Q1 — Quelle contrainte exacte ?
L'index unique partiel de DATA_CONTRACT §6.1 — **EXPLICITE**. Son **nom** n'est écrit dans aucun document gelé ; TD16 n'impose qu'un nom stable préfixé `uq_`. `uq_collection_actions_dedup_key` est une **PROPOSITION DÉRIVÉE, pas un contrat** (R12-O3) : la migration le fixera, TA-04 / TA-08 le vérifieront. Le coureur **ne contient aucun nom de contrainte** : le cas d'usage déclare la contrainte attendue (`DedupPolicy.constraint`), l'infrastructure rend SQLSTATE + nom, la politique compare.
L'index doit rester **immédiat** (non `DEFERRABLE`) — DÉRIVÉ (DATA_CONTRACT ne le déclare pas différable). S'il l'était, la violation surgirait au `COMMIT` ; C la couvrirait aussi, l'interception entourant toute l'unité, `COMMIT` compris (TA-08).

### Q2 — Distinguer cette violation des autres erreurs d'intégrité
L'adaptateur lève `UniqueViolation(constraint)` pour SQLSTATE `23505`, en recopiant `diag.constraint_name` (TD19). Le coureur ne traduit en `REPLAY` **que** la contrainte **exactement** déclarée ; toute autre violation d'unicité, toute autre erreur d'intégrité remonte **inchangée** (TD19 : défaut → `INTERNAL`) ; sans déclaration, rien n'est traduit.
**PROUVÉ (PG-11a, PG-11e)** : l'`INSERT` bloqué reçoit `23505` avec le nom de l'index partiel ; une autre contrainte d'unicité (clé primaire) donne **le même SQLSTATE** avec **son propre nom** — le nom seul distingue la déduplication.

### Q3 — Identifier l'action existante
Par la **contrainte elle-même** : l'occupant de l'index pour `(organisation liée, dedup_key)`, prédicat partiel compris ; l'index garantit **au plus une** ligne. Le prédicat appartient à l'**infrastructure** (ni le coureur ni le Domain ne le recopient). La clé est fournie par la déclaration, donnée ou calculée de `(état lu en P7, commande)` (pour A1, `cycle` et `occurrence` sont des faits lus).
**PROUVÉ (PG-11f)** : `CANCELLED` et `SUPPRESSED` ne bloquent pas ; `DONE` et `FAILED` bloquent.

### Q4 — Quelle représentation renvoie `REPLAY` ?
« L'objet existant est renvoyé » (EC §0.3) — **EXPLICITE**. La forme est **DÉRIVÉE** : `DedupPolicy.replay(ligne)` construit une valeur de **même forme** que le résultat `OK`, à partir de la ligne existante (identifiant, statut **courant**). Cette valeur est stockée dans la clé de requête : un rejeu de la **même** requête rend le même objet.

### Q5 — Quelle transaction, quelle isolation ?
- La violation **défait l'unité entière** : écritures, événements, audit, clé de requête en attente, reçu (P10).
- **Une** unité de reprise s'ouvre ensuite : même contexte, même portée, même isolation, même séquence de verrous (K, verrous, P7). Elle **n'appelle jamais le Domain** et n'écrit aucune donnée métier (donc bornée à une : elle ne peut pas violer la contrainte à son tour).
- **PROUVÉ (PG-11a, PG-11d)** : la transaction de reprise voit le gagnant. **CONSTATÉ (PG-11a-*, PG-11g-*)** sur PostgreSQL 16.2 : en `READ COMMITTED`, `REPEATABLE READ` et `SERIALIZABLE`, avec ou sans lecture préalable de la clé par A, l'`INSERT` bloqué reçoit `23505` nommé, pas `40001`. C'est un constat de version, non une affirmation : si une version rendait `40001`, TD30 (rejeu borné) s'appliquerait et A trouverait alors le gagnant.

### Q6 — Et si l'action concurrente n'est pas encore visible ?
- **PROUVÉ (PG-11a, PG-11b, toutes isolations)** : l'`INSERT` concurrent **attend** la fin de la transaction gagnante ; si elle **valide**, l'`INSERT` bloqué reçoit `23505` ; si elle **annule**, l'`INSERT` **réussit** sans violation. Un `23505` n'est donc **jamais** dû à une ligne non validée.
- **PROUVÉ (PG-11d)** : sans transition concurrente hors de l'index entre la violation et la relecture, le gagnant est **toujours** relu.
- Le seul cas où la relecture échoue est traité séparément (§3) : il exige une **troisième** transaction qui fait sortir le gagnant de l'index.

### Q7 — A1 et A4 se comportent-ils de la même façon ?
**Un seul mécanisme**, sans nom de cas d'usage dans le coureur.

| Affirmation | Nature |
|---|---|
| La `dedup_key` d'A4 est `manual:{idempotency_key}` | EXPLICITE (DATA_CONTRACT §6.2 ; spécification générée `manual:{clé}`) |
| P4 s'exécute avant A et C | EXPLICITE (TD32) ; vérifié par l'ordre du coureur (K puis verrous puis P7) |
| Pas de faux `REPLAY` au titre de la contrainte : même clé + même charge → vrai rejeu P4 ; même clé + autre charge → `IDEMPOTENCY_KEY_REUSED` avant le Domain ; une clé A1 (`{invoice_id}:…`) ne commence jamais par `manual:` | DÉRIVÉ |
| C n'est qu'un filet défensif pour A4 | **DÉRIVÉ, FAUX après purge** : une fois la clé de requête purgée (`expires_at`), une requête qui réutilise la clé passe P4 ; c'est alors A ou C qui retrouve l'action manuelle et rend `REPLAY`. **P4** (idempotence de requête), **`dedup_key`** (unicité métier de l'action) et **C** (garde concurrente de cette unicité) ne sont pas redondants. |

## 3. Cas non résolu — « gagnant introuvable » (R12-O1, OUVERT)

**Situation.** La contrainte déclarée a refusé l'écriture (le doublon est établi), mais la relecture de reprise ne trouve **aucun** occupant vivant.

**Atteignable : oui — CONSTATÉ (PG-11c).** T1 valide ; l'`INSERT` de T2 reçoit `23505` ; une **troisième** transaction fait sortir le gagnant de l'index (annulation, suppression) **avant** la reprise ; la reprise ne lit rien. Ce n'est donc pas un état impossible : il exige une transition concurrente hors de l'index dans cette fenêtre. Hors ce cas, le gagnant est toujours relu (PG-11d) : un échec de relecture **sans** une telle transition serait un défaut d'invariant du mécanisme, non une issue métier.

**Ce que le contrat dit : rien.** Aucune source gelée ne définit l'issue d'A1/A4 dans cette situation ; `CONCURRENT_MODIFICATION` n'est pas dans leurs erreurs (seule la classe `CONFLICT` l'est).

**Ce que fait le coureur : il ne traduit pas.** La `UniqueViolation` d'**origine** remonte inchangée (journal : `dedup_unresolved`) ; rien n'est écrit ; la clé de requête n'est pas consommée ; le Domain n'est pas rappelé. **Ce n'est pas une sémantique décidée** : c'est l'absence de traduction tant qu'aucune n'est contractée — le traitement par défaut de TD19 pour toute violation non traduite.

**Ce qui n'est PAS fait, volontairement.** Ni `CONCURRENT_MODIFICATION` (extension normative du contrat d'A1/A4), ni un nouveau code (`DEDUP_CONFLICT_UNRESOLVED`…), ni un second appel du Domain (qui transformerait une récupération de déduplication en seconde décision métier, non démontrée sûre).

**Revue de fermeture :** [R12_O1_REVUE_FERMETURE.md](R12_O1_REVUE_FERMETURE.md) (options A à E, aucune choisie). Attention : sous TI13, une `UniqueViolation` brute ne peut pas atteindre l'API ; l'état provisoire du coureur devra être tranché avant l'adaptateur.

**Question à trancher (arbitrage métier) :** quelle issue A1/A4 doivent-ils produire quand le doublon a été établi par l'index mais que l'objet n'est plus éligible au moment de la relecture ?

## 4. Ce qui est implémenté (coureur générique)

| Élément | Fichier | Rôle |
|---|---|---|
| `UniqueViolation(constraint)` | `application_runner/errors.py` | signal d'infrastructure typé (23505 + nom) ; **reste dans le coureur** (R12-O2 clos) |
| `DedupPolicy(constraint, key, replay)` ; `UseCaseImpl.dedup` ; `PhasePlan.dedup` | `decision.py`, `runner.py` | déclaration par cas d'usage (porte `handle` et première unité d'une composition) |
| `Runner.check_dedup` | `runner.py` | refus **avant toute transaction** : spécification sans `dedup_key`, sans issue `REPLAY`, unité non première, contrainte sans nom |
| chemin rapide A | `runner.py` `_unit` | après K, verrous et P7, **avant P8** : occupant présent → `REPLAY`, Domain non appelé, clé complétée |
| correction C | `runner.py` `_run_unit` | violation de la contrainte déclarée → unité défaite → **une** reprise → `REPLAY` ; occupant introuvable → violation d'origine non traduite (§3) |
| `UniqueIndex`, `find_unique`, contrôle immédiat | `doubles/store.py` | double de l'index partiel nommé, par organisation, sur les deux chemins d'écriture |

Composition : un `REPLAY` de la première unité arrête les phases suivantes ; l'avancement d'une action existante reste l'affaire du balayage de reprise. Une unité impérative (sans P7) fournit une clé **donnée** (`dedup_key_needs_state` sinon).

## 5. Preuves

| Preuve | Portée | Résultat |
|---|---|---|
| `application_runner/tests/test_r12_dedup.py` | coureur sur doubles | 22 tests verts |
| mutations du mécanisme | coureur + double | **16/16 tuées**, dont trois sur le « gagnant introuvable » (rappel du Domain, erreur inventée, garde supprimée) |
| `verify_runner` R1–R5 | aucun nom de contrainte, de verrou, de cas d'usage dans le coureur | 0 erreur |
| `architecture_registry/r12_pg_experiments.py` + `test_r12_pg.py` (**PG-11**) | **PostgreSQL 16.2 réel**, transactions concurrentes | affirmations PG-11a, b (×3 isolations), d, e, f : **confirmées** ; constats PG-11a-RR/SER, PG-11c, PG-11g (×3) : observés |

PG-11 est **séparé** de `pg_experiments.py` (TA-12) : il n'alimente ni `pg_results.json` ni le registre gelé. Le nom `uq_r12_probe_dedup_key` y est un nom de **sonde**. Le double ne simule qu'une transaction concurrente **déjà validée** ; c'est PG-11 qui établit l'attente, l'annulation et la visibilité.

## 6. Points ouverts et réserves

| Id | Point | Statut |
|---|---|---|
| R12-O1 | Issue d'A1/A4 pour un « gagnant introuvable » (§3) | **OUVERT** — arbitrage métier ; bloque la fermeture |
| R12-O2 | Emplacement de `UniqueViolation` | **CLOS** — reste dans `application_runner`, aucun amendement du registre |
| R12-O3 | Nom définitif de la contrainte (`uq_collection_actions_dedup_key` proposé) | DÉRIVÉ — figé par la migration, vérifié par TA-04 / TA-08 |
| R12-PG | Comportement 23505 / attente / visibilité / annulation sur PostgreSQL réel | **PROUVÉ** par PG-11 (PostgreSQL 16.2) ; constats d'isolation propres à cette version |
| R12-O4 | Une décision créant **deux** lignes vivantes de même clé dans la même unité : la reprise trouverait l'occupant committé s'il existe, sinon la violation remonte non traduite | limite connue ; hors cas A1/A4 (une action par commande) |
| R12-O5 | `notifications.CreateNotification` (service, issues vides) et `NotifyApprovers` (handler, sans `REPLAY`) refusés par `check_dedup` | hors périmètre |
| TRACE-A10 | Matrice ligne 278 (A10, « probablement REPLAY », DERIVED) | **non touchée** — réserve de traçabilité, correction sur autorisation séparée |

**R-12 ne sera dit CLOS qu'après la revue de fermeture et l'arbitrage de R12-O1. A1 et A4 restent bloqués jusque-là.**
