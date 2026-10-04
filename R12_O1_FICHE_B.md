# R12-O1 — Fiche de spécification minimale de l'option B

Statut : **B ACCEPTÉE COMME DIRECTION — NON IMPLÉMENTÉE.** Aucun code, aucun document gelé modifié par cette fiche. Date : 2026-10-04.
Rattachement : [R12_O1_REVUE_FERMETURE.md](R12_O1_REVUE_FERMETURE.md) (options A à E ; **E et C′ rejetées**, B retenue) · [R12_DEDUP_REPLAY_V1.md](R12_DEDUP_REPLAY_V1.md) §3.
Les choix marqués **[À VALIDER]** sont des propositions ; rien n'est décidé tant que la fiche n'est pas validée.

## 0. Rectification de formulation

La revue précédente disait « le gagnant existe toujours ». Formulation **retirée**. Ce que PG-11 établit :
- dans le conflit normal, **l'objet occupant qui a provoqué le 23505 est récupérable** (PG-11a, PG-11d) ;
- une troisième transaction peut le rendre **inéligible** avant la relecture (PG-11c).

Donc : **le gagnant logique du conflit a existé**, mais **l'objet récupérable au moment de la résolution peut ne plus être disponible**. Le système ne garantit aucune identité historique qui permettrait de le retrouver hors de l'index (raison du rejet de E).

## 1. Sémantique

> **Conflit de déduplication établi par la contrainte, mais l'objet nécessaire à la résolution `REPLAY` n'est plus récupérable.**

C'est un **échec de résolution du protocole de déduplication, au niveau Application**. Ce n'est **ni** une erreur métier de Collection, **ni** une transition d'état, **ni** `CONCURRENT_MODIFICATION` (concurrence optimiste), **ni** `SERIALIZATION_FAILURE` (40001 / 40P01), **ni** une nouvelle exécution du Domain, **ni** un défaut (`DB_INVARIANT_VIOLATED`, aucun invariant n'étant violé).

Condition de production, **unique et fermée** : dans l'unité de reprise de C, la contrainte **déclarée** a été violée **et** la lecture de son occupant vivant ne rend rien. Jamais ailleurs, jamais par le Domain.

## 2. Nom **[À VALIDER]**

Proposé : **`DEDUP_REPLAY_UNAVAILABLE`** — décrit le fait (le `REPLAY` dû n'a pas d'objet), pas une cause supposée.
Alternatives : `DEDUP_OCCUPANT_UNAVAILABLE` (décrit l'index plutôt que l'issue) ; `DEDUP_RESOLUTION_FAILED` (plus vague).

## 3. Classe et HTTP **[À VALIDER]**

Proposé : **`CONFLICT`, 409.**
- C'est un conflit avec un état concurrent, comme les autres codes `CONFLICT` du catalogue.
- `CONFLICT` est **déjà** dans les classes déclarées d'A1 et d'A4 : aucune classe n'est à ajouter à leurs contrats.
- Écartées : `INTERNAL` (même faute que l'option A : ce n'est pas un défaut) ; `TRANSIENT` (rien d'infrastructurel n'est indisponible).

## 4. Retryable **[À VALIDER]**

Proposé : **oui.** Raisonnement, à partir des sources :

| Fait | Source | Nature |
|---|---|---|
| L'unité perdante est entièrement défaite ; la clé de requête **n'est pas consommée** | R-12 C ; PG-11 | PROUVÉ (doubles + PostgreSQL) |
| Une nouvelle tentative exécute donc la requête **pour la première fois** sur l'état courant : ce n'est pas le rejeu d'un effet déjà réalisé | EC P2 (`REPLAY` = effet déjà réalisé) | DÉRIVÉ |
| Sur l'état courant, le contrat **décide déjà** : action annulée ou supprimée → ne bloque pas une création équivalente ; `APPROVAL_REJECTED` → pas de nouvelle proposition dans le cycle (`SKIP`) ; suppression toujours valable → `SUPPRESSED` | DATA_CONTRACT §6.1 ; COLLECTION_ENGINE §4 étapes 3–4 (C8) | EXPLICITE |
| Côté A1, un échec **non** retryable rend l'étape d'automatisation `FAILED` (terminale, alerte) pour une course bénigne ; un échec transitoire est retenté (1 min, 5 min, 30 min) | AUTOMATION_ENGINE (étapes ; reprise d'un échec) | EXPLICITE (mécanisme) ; DÉRIVÉ (application à ce code) |

Ce qu'implique « oui », sans l'éluder : la nouvelle tentative **peut créer** une action — exactement celle que le contrat aurait créée si la requête était arrivée après l'annulation. Ce n'est pas l'option D : le coureur ne rappelle **jamais** le Domain lui-même ; c'est l'appelant qui choisit de retenter, comme pour tout `CONFLICT` retryable.
Ce qu'impliquerait « non » : aucune création possible sans intervention, mais exécution `FAILED` + alerte pour un cas sans défaut, et une action manuelle (A4) refusée sans règle métier.

**Compatibilité A1/A4 : à confirmer explicitement** — c'est la seule question métier restante de cette fiche.

## 5. Contrat A1 (`CreateCollectionAction`)

- Erreurs : `SUBJECT_NOT_FOUND`, `ACTION_LEVEL_INVALID`, `ACTION_LEVEL_BELOW_MINIMUM`, **+ `DEDUP_REPLAY_UNAVAILABLE`**.
- Classes : inchangées (`CONFLICT` déjà déclarée).
- Issues : inchangées (`OK`, `REPLAY`, `SKIPPED`, `DEFERRED`) — une erreur n'est pas une issue (EC §0.3).
- Idempotence EC-11 : « `dedup_key` → `REPLAY` » ; précision : « occupant introuvable à la reprise → `DEDUP_REPLAY_UNAVAILABLE` ».

## 6. Contrat A4 (`CreateManualAction`)

Identique à A1 (même mécanisme, même code). Seul lieu d'occurrence réaliste : une clé de requête **réutilisée après purge** (`idempotency_keys` après `expires_at`, purge « proposition à confirmer ») ; avant purge, P4 capte la collision en amont.

## 7. Comportement du coureur

Dans l'unité de reprise de C uniquement :
```
violation de la contrainte déclarée → unité défaite → reprise (même contexte, isolation, verrous)
    occupant vivant trouvé    → REPLAY (inchangé)
    occupant introuvable      → DomainError(DEDUP_REPLAY_UNAVAILABLE, détails : {constraint}), journal `dedup_unresolved`
```
Remplace l'actuelle remontée de la `UniqueViolation` d'origine. Inchangé : Domain jamais rappelé ; rien d'écrit ; clé de requête non consommée ; toute autre violation et toute contrainte non déclarée remontent non traduites (TD19 → `DB_INVARIANT_VIOLATED` à la frontière).
Le code d'erreur est un nom du catalogue, pas un nom de cas d'usage, de verrou ou de contrainte : compatible avec `verify_runner` R2 / R4 — **à vérifier** au moment de l'implémentation.

## 8. Comportement du transport

Aucun traitement particulier : c'est une `DomainError` du catalogue, rendue comme les autres (409, `retryable: true`, `code`, détails sans donnée personnelle — EC §0.4). Les détails exposent au plus le nom de la contrainte, jamais la `dedup_key` (qui contient l'identifiant de facture).

## 9. Invariants (à tester)

| # | Invariant |
|---|---|
| B-1 | Le code n'est produit **que** dans l'unité de reprise de C, après violation de la contrainte **déclarée** et relecture vide. |
| B-2 | Le Domain n'est jamais appelé dans l'unité de reprise ; aucune écriture, aucun événement, aucun audit ne survit. |
| B-3 | La clé de requête n'est pas consommée : une nouvelle tentative avec la même clé s'exécute normalement. |
| B-4 | Une violation d'une autre contrainte, ou sans déclaration, ne produit **jamais** ce code. |
| B-5 | Occupant vivant trouvé → toujours `REPLAY`, jamais ce code. |
| B-6 | Aucun Domain, aucune primitive n'importe ni ne produit ce code. |
| B-7 | Les détails ne contiennent pas la `dedup_key`. |

Tests prévus : adaptation de `test_a_winner_that_left_the_index_is_not_translated` ; un test par invariant ; PG-11c inchangé (le constat reste vrai) ; mutations : code produit hors reprise, code produit sur autre contrainte, retryable inversé, clé consommée, Domain rappelé, `dedup_key` dans les détails.

## 10. Impact exact sur les documents gelés (amendements nécessaires)

| # | Document / fichier | Modification | Mécanisme |
|---|---|---|---|
| 1 | **ENGINE_CONTRACTS_V1.md, Annexe A** (gelé) | ajout de la ligne `` `DEDUP_REPLAY_UNAVAILABLE` \| CONFLICT \| 409 \| oui \| ARCH `` | amendement journalisé ; `gen_contracts.py` régénère `verqia/kernel/errors.py` (catalogue 109 → 110 codes) ; les tests qui comptent les codes sont à mettre à jour |
| 2 | **ENGINE_CONTRACTS_V1.md, EC-11** (gelé) | lignes `CreateCollectionAction` et `CreateManualAction` : erreur ajoutée ; précision dans la colonne Idempotence | même amendement |
| 3 | `architecture_registry/gen_application.py` (erreurs A1/A4) | ajout du code aux deux listes | **amendement Application B11** ; régénération `specs.py` et `APPLICATION_CONTRACT_V1.md` ; gel Application réécrit (11 amendements) |
| 4 | **TECHNICAL_ARCHITECTURE_V1.md** (gelé) | **pas** de réécriture de TD19 : une ligne en **§13** (« écarts et amendements ») précisant la traduction « 23505 de la contrainte de déduplication, occupant introuvable → `DEDUP_REPLAY_UNAVAILABLE` » | amendement journalisé en §13 |
| 5 | GLOBAL_TEST_MATRIX (`build_matrix.py`) | une ligne `ERR:DEDUP_REPLAY_UNAVAILABLE` (ENGINE_CONTRACTS l. 417 : chaque code de l'Annexe A est produit par au moins un test) | régénération |
| 6 | `application_runner` | §7 ; tests §9 | code (hors gel) |
| 7 | R12_DEDUP_REPLAY_V1.md, R12_O1_REVUE_FERMETURE.md | R12-O1 fermé par B ; §3 mis à jour | documents R-12 |
| 8 | COLLECTION_DOMAIN_V1.md §17 (R-12) | statut — **seulement à la fermeture** | sur autorisation |
| — | DATA_CONTRACT, INVARIANTS, STATE_MACHINES, RULE_ENGINE, COLLECTION_ENGINE, AUTOMATION_ENGINE | **aucune** modification | — |
| — | Domain Collection, primitives, oracle, matrice (A10 compris) | **aucune** modification | — |

## 11. Décisions demandées avant toute implémentation

1. Nom : `DEDUP_REPLAY_UNAVAILABLE` ?
2. Classe : `CONFLICT` / 409 ?
3. Retryable : oui (avec la conséquence assumée du §4) ?
4. Autorisation d'amender ENGINE_CONTRACTS (Annexe A et EC-11), l'Application (B11) et TECHNICAL_ARCHITECTURE §13, dans cet ordre, avec journalisation.

R12-O1 reste **OUVERT** jusqu'à l'implémentation et aux tests de B ; R-12 n'est pas clos ; A1 et A4 restent bloqués.
