# R12-O1 — Revue de fermeture contractuelle : le « gagnant introuvable »

Statut : **ANALYSE CLOSE — direction retenue : B** (E et C′ rejetées ; 2026-10-04). Spécification : [R12_O1_FICHE_B.md](R12_O1_FICHE_B.md). Aucun code modifié. Note : la formule « le gagnant existe toujours » (§6) est retirée, voir la fiche §0. Date : 2026-10-04. Rattachement : [R12_DEDUP_REPLAY_V1.md](R12_DEDUP_REPLAY_V1.md) §3.
Partie technique de R-12 : close (A+C validé, PG-11 sur PostgreSQL 16.2 réel). Partie contractuelle : **OUVERTE**, objet de ce document.

## 0. La question, exactement

> Lorsqu'une violation de la contrainte de déduplication est reçue, mais que l'action gagnante a quitté l'ensemble couvert par l'index avant la lecture de récupération, quelle sémantique A1/A4 est contractuellement attendue ?

Faits établis (PG-11) : le cas est **atteignable** (PG-11c), uniquement si une **troisième** transaction fait sortir le gagnant de l'index (annulation, suppression) entre la violation et la relecture ; sinon le gagnant est toujours relu (PG-11d). Le gagnant était **vivant et validé** au moment où l'écriture de T2 a été refusée (PG-11a, PG-11b).

## 1. Contrats d'erreurs exacts d'A1 / A4 (point 1 de la revue)

| | A1 `CreateCollectionAction` | A4 `CreateManualAction` | Nature |
|---|---|---|---|
| Erreurs nommées | `SUBJECT_NOT_FOUND`, `ACTION_LEVEL_INVALID`, `ACTION_LEVEL_BELOW_MINIMUM` | les mêmes + `OVERRIDE_NOT_ALLOWED`, `OVERRIDE_ROLE_INSUFFICIENT`, `OVERRIDE_REASON_REQUIRED`, `OVERRIDE_ORIGIN_NOT_MANUAL` | EXPLICITE (spécifications générées) |
| Classes d'erreurs | `VALIDATION`, `NOT_FOUND`, `FORBIDDEN`, `CONFLICT`, `BUSINESS_RULE`, `TRANSIENT` | idem | EXPLICITE |
| Issues | `OK`, `REPLAY`, `SKIPPED`, `DEFERRED` | idem | EXPLICITE |
| Nouvelle tentative | « TD30 : rejeu borné (3) sur 40001 / 40P01, avant tout effet externe ; **sinon erreur retryable pour le client** » | idem | EXPLICITE |

Aucune des deux ne nomme d'erreur pour le cas étudié. **La classe `INTERNAL` n'est pas dans leurs classes déclarées.**

## 2. `UniqueViolation` peut-elle être exposée ? (point 2)

**Non, pas telle quelle.** TI13 (EXPLICITE) : « Toute erreur de base atteignant l'API est traduite ; une violation d'invariant qui l'atteint est un défaut. » Une `UniqueViolation` brute ne peut donc jamais atteindre l'appelant. Le seul code prévu pour une violation non traduite est `DB_INVARIANT_VIOLATED` (catalogue : `INTERNAL`, 500, non retryable, source ARCH ; rattaché à TD19 / TI13 par TA-08) — **EXPLICITE**.

Conséquence : l'« Option A » de la revue, sous sa forme conforme à TI13, n'est pas « exposer `UniqueViolation` » mais **« `DB_INVARIANT_VIOLATED` + alerte »**. Or PG-11c montre que **aucun invariant n'est violé** et **aucun défaut n'existe** : la base a fait respecter l'unicité, puis une transition légitime a eu lieu. Classer ce cas en défaut serait une **qualification fausse** au regard du texte même de TI13. Aujourd'hui, en l'absence d'adaptateur, le transport ne traduit rien : l'état provisoire actuel du coureur ne survit pas à l'implémentation de TI13 sans que ce choix soit fait.

## 3. Une erreur existante couvre-t-elle déjà le cas ? (point 3)

| Code | Défini pour (source) | Dans A1/A4 ? | Retryable | Adéquation |
|---|---|---|---|---|
| `DB_INVARIANT_VIOLATED` | violation non arrêtée par le Domain = défaut (TD19, TI13, TA-08) | non (classe `INTERNAL` non déclarée) | non | **inexacte** : il n'y a pas de défaut (§2) |
| `CONCURRENT_MODIFICATION` | version périmée (TD19) ; « concurrence optimiste : `version` comparée ; sinon `CONCURRENT_MODIFICATION` » (TECHNICAL_ARCHITECTURE, tableau des régimes de concurrence) | non (classe `CONFLICT` déclarée) | oui | **étendue** : aucune version n'est en jeu |
| `SERIALIZATION_FAILURE` | `40001` / `40P01` après TD30 épuisé (TD19, TD30, EC10) | **annoncée par le champ « nouvelle tentative » d'A1/A4** (« erreur retryable pour le client ») ; classe `CONFLICT` déclarée | oui | **étendue** : déclencheur différent (23505 non résolu, pas 40001) ; sens proche (« conflit rejouable », EC10) |
| `IDEMPOTENCY_KEY_REUSED` | même clé, autre charge (P4) | transversal | non | **sans rapport** |

Aucune erreur existante n'est **définie** pour ce cas. `SERIALIZATION_FAILURE` est la seule qu'A1/A4 annoncent déjà pouvoir rendre ; l'utiliser ici élargirait son déclencheur.

## 4. Effets de `CANCELLED` / `SUPPRESSED`, du rejeu et de la purge (point 4)

Sources EXPLICITES :
- DATA_CONTRACT §6.1 : « une action annulée ou supprimée **ne bloque pas** la création d'une action équivalente ».
- DATA_CONTRACT §6.2 : « un événement rejoué **ne crée rien** ».
- COLLECTION_ENGINE §4 étape 4 (C8) : une action de même clé `CANCELLED` avec `APPROVAL_REJECTED` → **pas de nouvelle proposition** dans le cycle (`SKIP`, `APPROVAL_PREVIOUSLY_REJECTED`) ; les autres annulations (`USER_CANCELLED`, `APPROVAL_EXPIRED`) n'empêchent pas une nouvelle proposition.
- COLLECTION_ENGINE §11 (l. 270, 286) : deux **étapes différentes** (S5, S6) peuvent calculer la **même** `dedup_key` ; la seconde « ne crée rien (**REPLAY**) ». Le perdant T2 n'est donc **pas forcément un rejeu** : il peut être une autre étape légitime.
- Suppression (`SUPPRESSED`) : le Rule Engine `SUPPRESS` crée une action `SUPPRESSED` « pour l'explicabilité » (§4 étape 3).

Conséquences :
- Les issues acceptables sont celles qui correspondent à **un ordre sériel** possible des trois transactions :
  - **T2 avant l'annulation** → T2 aurait trouvé le gagnant vivant → **`REPLAY` du gagnant** ;
  - **T2 après l'annulation** → T2 serait une création ordinaire → **la décision du Domain sur l'état courant** (création, `SKIP` C8 si `APPROVAL_REJECTED`, `SUPPRESSED` si la suppression tient toujours) ;
  - **échec de T2** sans effet → toujours sûr, mais reporte la décision sur l'appelant.
- L'ordre **observé** est le premier : PG-11a prouve que le gagnant était vivant et validé quand l'écriture de T2 a été refusée.
- Une erreur **retryable** conduit l'appelant à rejouer ; l'index étant libre, le rejeu suit le second ordre (décision du Domain). Une erreur **non retryable** fait échouer une étape d'automatisation légitime (cas S5/S6) sans qu'aucune règle métier ne l'ait refusée.
- **Purge** (`idempotency_keys` après `expires_at`, « proposition à confirmer ») : ne touche qu'A4 (`manual:{clé}`). Après purge, une clé réutilisée passe P4 ; A ou C décident. Le cas R12-O1 s'y applique à l'identique. Pour A1, la purge ne joue pas (sa `dedup_key` ne dépend d'aucune clé de requête).

## 5. Options (point 5) — aucune n'est choisie ici

| Option | Issue | Base | Ce qu'il faut amender | Risques |
|---|---|---|---|---|
| **A** — non traduite | `DB_INVARIANT_VIOLATED` (TI13) | TD19, TI13 : EXPLICITES pour un **défaut** | classe `INTERNAL` dans A1/A4 (ou constat qu'elle est transversale) | **qualifie un cas légitime de défaut** ; alerte à tort ; étape d'automatisation en échec non retryable |
| **B** — erreur dédiée | nouveau code | aucune | catalogue (Annexe A générée), EC-11, A1/A4 | nouvelle sémantique ; amendement de documents gelés |
| **C** — `CONCURRENT_MODIFICATION` | erreur retryable | aucune pour ce cas | erreurs d'A1/A4 | extension d'un code défini pour la concurrence optimiste |
| **C′** — `SERIALIZATION_FAILURE` | erreur retryable | A1/A4 l'annoncent déjà (TD30) ; EC10 « conflit rejouable » | élargir son déclencheur à « 23505 non résolu » (TD19) | extension de déclencheur, même si le code est déjà promis |
| **D** — réexécuter l'unité (bornée) | décision du Domain sur l'état courant | **précédent EXPLICITE : TD30** réexécute déjà l'unité entière (Domain compris) sur conflit de concurrence, dans ces mêmes cas d'usage ; le résultat est celui qu'imposent C8 et §6.1 pour cet état | préciser TD30 / R-12 : la reprise C peut réexécuter l'unité | issue qui suit l'ordre sériel **non observé** ; peut créer une action alors que T2 était, au moment du conflit, un doublon ; si T2 était un rejeu d'événement, contredit « un événement rejoué ne crée rien » |
| **E** — `REPLAY` du gagnant hors index | `REPLAY`, objet au statut courant (`CANCELLED` / `SUPPRESSED`) | EC §0.3 « l'objet existant est renvoyé » (il existe toujours) ; EC §5 ; COLLECTION_ENGINE l. 270 « ne crée rien (REPLAY) » ; suit l'ordre **observé** (PG-11a) ; ne crée rien | règle DÉRIVÉE d'identification : à défaut d'occupant vivant, la ligne **la plus récente** de cette clé (`created_at` STD, ou UUIDv7 applicatif — DATA_CONTRACT conventions) ; la relecture lit hors prédicat | renvoie un objet inéligible ; règle d'identification à figer ; à vérifier sur PostgreSQL (PG-11c étendu) |

Sur la remarque de la revue (« écarter D ») : D n'est pas sans source — **TD30 fait déjà exactement cela** pour `40001` / `40P01` dans A1/A4. Son vrai défaut est ailleurs : il retient l'ordre sériel que l'observation (PG-11a) contredit, et il peut créer quand T2 était un rejeu.

## 6. Proposition de décision (point 6) — À ARBITRER, non appliquée

**Proposition : Option E**, pour quatre raisons tirées des sources :
1. elle n'invente ni code d'erreur ni amendement du catalogue (B, C exclus) ;
2. elle ne qualifie pas un cas légitime de défaut (A exclu au regard de TI13) ;
3. elle suit l'ordre **réellement observé** : le gagnant était vivant quand la contrainte a refusé T2 ; T2 était donc un doublon, et le contrat dit d'un doublon qu'il « ne crée rien (REPLAY) » et que « l'objet existant est renvoyé » ;
4. elle ne crée jamais rien, donc reste compatible avec « un événement rejoué ne crée rien » quel que soit l'appelant.

Ce qu'elle exigerait avant fermeture : (i) figer la règle d'identification (ligne la plus récente de la clé) comme **règle DÉRIVÉE nouvellement décidée** ; (ii) étendre PG-11c pour prouver que cette ligne est relue ; (iii) un test et des mutations dans le coureur. **Second choix si E est refusée : C′**, qui n'élargit qu'un déclencheur d'un code déjà promis par A1/A4.

Ce document ne modifie rien. R12-O1 reste **OUVERT** ; R-12 n'est **pas** clos ; A1 et A4 restent bloqués.
