# VERQIA — Technical Architecture V1

Références : `ARCHITECTURE_REGISTRY_V1.md` (généré), Data Contract V1.3, Invariants V1.2, State Machines V1, Rule Engine V1.1, Collection Engine V1.1 et V1.2, Automation Engine V1.1, Engine Contracts V1.1, Risk / Priority / Cashflow V1.1, Global Test Matrix V1 (généré), `reference_model/`.
Statut : **V1 — GELÉE le 2026-09-18** (TD1 à TD59, K1 à K23, S1 à S6, TI1 à TI22, AR-01 à AR-20). Conditions du gel remplies : `build_registry.py --check --freeze` (0 erreur, 0 nom provisoire), 37 tests d'injection et PostgreSQL, matrice (215 tests, 726 éléments, 0 sans test), modèle de référence (35 tests). Les points ouverts du §13.3 ne font pas partie du gel. Historique des révisions : Révision 3 (écarts G à M, TA-12 exécuté) : **composition orchestrée** (TD58), **plan de provisioning** (TD59), **trois graphes de dépendances**, C12 réduit à deux opérations nommées, événements sans abonné classés, 20 noms de commandes figés (dont deux renommés en revue : `ProvisionDefaultAutomations`, `ProvisionTrialSubscription`), convention de nommage, 10 expériences sur PostgreSQL réel. Révision 1 : V1 restreinte (§0.3). Révision 2 (revue) : `TD23` (trois temps), `TI7` (publier n'est pas traiter), `TD27` / `TI4` (échelle de verrous dérivée), **propriété des écritures** (TD55), **quatre registres exécutables** (TD56, TD57). Ce document est un document de **contraintes et de frontières**, pas une liste de technologies. Les décisions sont numérotées **TD1 à TD59** ; les questions de la Constitution **K1 à K23** ; les règles de sobriété **S1 à S6** ; les contre-exemples **CX** ; les invariants **TI** ; les tests **TA**. **Aucun document figé n'est modifié** : les écarts découverts et les amendements sont en §13. **Aucun code** : les schémas sont conceptuels.

Objet : faire en sorte que l'architecture technique **ne puisse pas trahir** le moteur métier verrouillé. Elle le fait d'abord en décidant **où chaque décision a le droit de vivre** (§0.2), ensuite en refusant tout mécanisme que ne justifie pas un contre-exemple (§0.3). Le métier est figé ; ce document décide où chaque règle vit, quelle couche garantit quoi, comment les transactions, les événements et les travaux deviennent réels, et comment l'intégration continue empêche l'architecture de se dégrader.

Méthode : **proposition → décisions numérotées → contre-exemples → invariants → tests → validation → gel.**

Hors périmètre de ce document (décidés ailleurs ou ouverts, §13.3) : choix de l'hébergeur et de l'outil de supervision, mécanisme d'authentification, fournisseur d'e-mail, Billing (S7), **seuils de performance chiffrés** (fixés au banc d'essai défini en §12, comme la matrice de tests l'a annoncé).

---

## 0. Fondations : contraintes, constitution, sobriété, structure

### 0.1 Contraintes reçues des documents figés

Ces règles ne sont pas rediscutées ; l'architecture doit les rendre vraies.

| Contrainte | Source | Conséquence pour l'architecture |
|---|---|---|
| Le Domain n'importe ni Django, ni Redis, ni un fournisseur | DR1 | couches, ports, modèles d'ORM hors du Domain (TD2) |
| L'organisation est vérifiée à trois niveaux : filtre applicatif, FK composite, RLS | C2 | répartition explicite des responsabilités (TD17) |
| Écritures inter-agrégats synchrones : liste fermée et nominative de deux familles (`AllocatePayment`, `ReverseAllocation`, `ReversePayment` ; `NormalizeImportBatch`) ; `CreateOrganization` en sort (TD59) | C12, X8, DR3 | tout le reste passe par l'outbox (TA5) |
| Un envoi de message n'a jamais lieu dans une transaction | X13 | réclamer, valider, puis envoyer (TD31) |
| Une action ne passe `EXECUTING` qu'après revalidation complète dans la même transaction | X3 | claim + revalidation atomiques (TD31) |
| Ordre global des verrous `payments → invoices (id croissant) → promises → collection_actions → automation_executions → notifications` | EC5 | échelle de verrous vérifiée à l'exécution (TD27) |
| Livraison au moins une fois ; handlers idempotents, reçus `(event_id, handler_name)`, nouvelles tentatives 10 s / 1 min / 5 min / 30 min / 2 h, puis `DEAD` | EC2, X6, X16 | relais à bail (TD33), reçu par handler (TD35), aucun état de vérité hors de PostgreSQL |
| L'ordre n'est garanti qu'au sein d'un agrégat, jamais entre agrégats | §10.2 Invariants | l'ordre n'est jamais une condition de correction (TD36) |
| `events` et `audit_logs` partitionnées par mois ; pas d'unicité globale | Contrat §12 | recherche d'un événement par identifiant (TD22) |
| Triggers différés T1 à T13, garde de transition T14 générée depuis le Domain | Contrat §14 | erreurs levées **au COMMIT** : traduction obligatoire (TD19) |
| Compatible avec un pooler en mode transaction | Revue de cohérence | aucun état de session (TD21) |
| Aucune date courante lue dans le Domain ; `as_of` injecté | X12, EC3 | trois temps distincts ; `as_of` écrit dans toute colonne temporelle (TD23) |
| `decision_snapshot` immuable ; `OverrideGrant` = preuve, pas autorité | Collection V1.2 §3.3 | revalidation à l'exécution, pas de cache de décision |

### 0.2 Constitution technique : où chaque décision a le droit de vivre

**Règle.** Chaque question de VERQIA a **un seul propriétaire**. Une décision prise ailleurs que chez son propriétaire est un **défaut**, même si elle donne le bon résultat aujourd'hui. Toute décision technique de ce document se rattache à une ligne de cette table ; une question sans ligne est un manque à combler **avant** d'écrire du code.

**Échelle de garanties.** Pour chaque ligne, on retient le niveau **le plus haut possible** : **E1** la base l'empêche (contrainte, trigger, rôle, RLS) · **E2** la structure l'empêche (règle d'import, types, absence de chemin) · **E3** un test l'attrape · **E4** une convention (à éviter : elle ne protège pas).

| # | Question | Propriétaire unique | Ne décide **pas** | Garantie | Vérifié par |
|---|---|---|---|---|---|
| **K1** | Une facture est-elle **payée** ? | `invoices` (état de règlement, dérivé des allocations) ; écrit seulement par `AllocatePayment` (C12) | `collection`, `risk`, API, interface, un handler | E1 | T4, T1, T2, TA-13 |
| **K2** | **Combien** reste-t-il ? | `payments.payment_allocations` (source de vérité) ; `invoices.outstanding_minor` colonne générée | tout cache, toute projection, tout payload d'événement (X1) | E1 | T2, T4 |
| **K3** | Un paiement non alloué suspend-il une relance ? | `rules` (exception n° 13), sur des faits fournis par `payments` | Cashflow, Priority, un job | E3 | RC-03, RC-12 |
| **K4** | **Peut-on contacter** ? | `rules` : fonction pure, 13 exceptions | `collection`, `automation`, `notifications`, API, interface | E2, E3 | AR-06, TA-03 |
| **K5** | Quel **niveau** ? Quelle **action**, quel canal, quel gabarit, quel destinataire ? | niveau : `rules` ; action, canal, gabarit, assignation : `collection` | `automation`, `notifications` | E2 | AR-07 |
| **K6** | À quelle **étape du parcours**, après quel délai ? | `automation` (exécution datée) | `collection` (elle exécute l'action reçue), le planificateur | E2 | AR-07, TA-03 |
| **K7** | **Quand envoyer** physiquement (fenêtre de communication, reprise) ? | `rules` (`DEFER` + `retry_at`), puis `collection` (`scheduled_for`, tentatives) | le coureur, le fournisseur d'envoi | E3 | RE-01, RC-05 |
| **K8** | Quel est le **risque** ? | `risk` | tout moteur d'action | E2 | AR-05 |
| **K9** | Quelle facture **d'abord** ? | `priority` | tout moteur d'action, `risk` | E2 | AR-05 |
| **K10** | Quelle **trésorerie** prévoir ? | `cashflow` | tout moteur d'action | E2 | AR-05 |
| **K11** | **Quand réveiller** un processus ? | le **planificateur** calcule l'échéance ; le **coureur** exécute ; le **moteur** décide quoi faire | les moteurs (aucune horloge, aucune file) | E2, E3 | AR-02, TA-25 |
| **K12** | Un **événement** a-t-il été traité ? | `events` (reçus `(event_id, handler_name)`) ; l'**effet** est protégé par son propriétaire (`dedup_key`, `trigger_key`) | le handler seul, Redis | E1 | TA-19, TA-21 |
| **K13** | Un utilisateur peut-il **contourner** une exception ? | `rules` (contournable ? rôle minimal) ; `AuthorizeOverride` produit le grant ; **revérifié à l'exécution** | l'interface, `automation`, le coureur | E3 | RC-03, TA-17 |
| **K14** | Quelle **organisation** ? | `TransactionManager` + RLS | un paramètre de requête, un filtre oublié | E1 | TA-05, TA-07 |
| **K15** | Quelle **heure** est-il ? | le port `Clock` (`as_of`) ; l'adaptateur de production lit l'horloge de la base (TD23) | le Domain, l'Application, un hôte, un `DEFAULT now()` | E2, E3 | AR-02, TA-02, TA-11 |
| **K16** | Un **message est-il parti** ? | `notifications` (adaptateur, résultat) après un claim validé | toute transaction ouverte | E3 | AR-08, TA-17 |
| **K17** | Ordre des **verrous**, isolation, délais ? | `platform` (`LockManager`, `TransactionManager`) | tout module | E2, E3 | AR-16, TA-12 |
| **K18** | Quel **rôle** a l'utilisateur ? | `identity` ; l'usage du rôle : Application de chaque commande ; le rôle minimal d'un contournement : `rules` | l'interface | E3 | TA-05 |
| **K19** | Qu'est-ce qui est **audité** et **publié** ? | le cas d'usage propriétaire, dans sa transaction (`AuditWriter`, `EventOutbox`) | un handler, un job, un signal Django | E2, E3 | AR-10, TA-18 |
| **K20** | Quel **jour local**, quel jour ouvré ? | `kernel` (calcul pur) sur les données d'`organizations` | tout code qui recalcule un fuseau | E3 | RC-02, TA-02 |
| **K21** | Faut-il une **approbation** ? | `rules` (`requires_approval`) ; cycle de vie : `approvals` | `collection`, l'interface | E2 | AR-03 |
| **K22** | Comment **anonymiser** ? | **chaque module** anonymise ses propres données (`customers`, `identity`, `notifications`, `imports`, `audit`) ; le rôle `verqia_privacy` porte les droits colonne par colonne | le rôle applicatif, un module sur les données d'un autre | E1 | TA-06 |
| **K23** | Qui a le droit d'**écrire** cet état ? | **le module propriétaire**, par un **ensemble fermé de cas d'usage** déclarés (Command Registry) et par la fonction de transition du Domain ; les exceptions C12 sont les seules | tout autre module, un handler, un job, un signal, l'administration | E1 (colonnes générées, T4, T5, T14), E2 (dépôt d'écriture privé), E3 (registre) | AR-19, TA-01 |

Si une décision ne se laisse pas rattacher à une seule ligne, c'est qu'un concept manque au modèle : on le nomme **avant** de coder.

### 0.3 Sobriété : ce qui est requis, simplifié ou différé

Le danger principal de VERQIA n'est plus le manque de sophistication, c'est la **sur-architecture** : un système impressionnant sur le papier, difficile à construire et à maintenir. La première version de ce document proposait sept types de processus, six rôles de base de données, cinq usages de Redis et deux pools de relais. **Cette liste est réduite ici.**

| # | Règle de sobriété |
|---|---|
| **S1** | **Aucun mécanisme sans contre-exemple.** Chaque mécanisme cite le `CX` qu'il empêche ; un `CX` sans test est incomplet. |
| **S2** | **Une seule manière de faire chaque chose** : un chemin d'écriture (le cas d'usage), un chemin de publication (l'outbox), un chemin de verrouillage (`LockManager`), un chemin de planification (l'échéance dans une table et une boucle de sondage), un chemin d'effet externe (réclamer, valider, agir). |
| **S3** | **Le niveau de garantie le plus haut** (E1 avant E2, E2 avant E3) : une contrainte vaut mieux qu'un test, un test vaut mieux qu'une convention. |
| **S4** | **PostgreSQL d'abord.** Aucun courtier, cache ou réplica n'entre dans l'infrastructure sans une mesure qui le justifie. |
| **S5** | **Différé n'est pas supprimé** : chaque différé a un **déclencheur mesurable** et une extension qui ne change aucun contrat. |
| **S6** | **Toute nouveauté se rattache à une ligne de la Constitution** (§0.2) ; sinon, refusée. |

| Mécanisme | Empêche | Statut V1 | Déclencheur d'activation, si différé |
|---|---|---|---|
| Couches, `contracts`, règles d'import | CX1, CX3, CX5 | **Requis** | — |
| Domain riche **seulement** pour les agrégats à règle d'état ou d'argent (TD2) | CX1 | **Simplifié** : les modules sans règle (contacts, réglages, gabarits, utilisateurs) utilisent un service d'application mince | — |
| Isolation en trois couches dont RLS (TD17) | CX9 | **Requis** | — |
| Rôles PostgreSQL (TD18) | CX10 | **Simplifié** : quatre rôles au lieu de six | — |
| Échelle de verrous vérifiée (TD27) | CX15, CX19 | **Requis** (vérifiée en test et en CI ; journalisée en production) | — |
| Verrou de sujet en première instruction (TD29) | CX18 | **Requis** | — |
| Réclamer, valider, agir (TD31) | CX16, CX17 | **Requis** | — |
| Idempotence d'API en une transaction (TD32) | CX20 | **Requis** | — |
| Relais à bail, `events.available_at` (TD33, TD35) | CX21, CX22 | **Requis** | — |
| Reçu par handler avec `RETRYING` (TD35) | CX21, CX26 | **Requis** | — |
| Registres d'architecture, échelle de verrous dérivée, propriété des écritures (TD27, TD55, TD56) | CX19, CX38, CX39 | **Requis** | — |
| Composition orchestrée et plan de provisioning (TD58, TD59) | CX42, CX43 | **Requis** | — |
| Regroupement des `REQUEST` (TD38) | CX25 | **Requis** | — |
| Équité par organisation (TD39) | CX25 | **Simplifié** : un plafond par lot de réclamation | files par organisation |
| Pools de relais séparés par catégorie (TD37) | CX24 | **Simplifié** : deux réserves d'exécution dans un même processus | séparation en processus si le banc montre un retard de diffusion hors objectif pendant un calcul long |
| Indices de réveil Redis, ticks Redis, cache d'affichage | — | **Différé** : le relais sonde chaque seconde | latence de l'outbox hors objectif mesurée au banc |
| Redis : limitation d'API et étranglement d'envoi (TD49) | CX32 | **Requis** (seuls usages en V1) | — |
| Types de processus | — | **Simplifié** : `web` et `worker` (à voies) au lieu de sept | charge d'une voie observée |
| Planificateur | CX28 | **Simplifié** : boucle sans chef dans chaque `worker` | — |
| Réplica de lecture | — | **Différé** | latence des lectures d'affichage hors objectif |
| Module `billing` | — | **Différé** : aucun paquet avant la spécification de S7 | S7 spécifié |
| Trois temps distincts (TD23), `tzdata` figé (TD24) | CX14, CX41 | **Requis** | — |
| Chaos, différentiel, banc (TA-31 à TA-33) | — | **Requis**, mais **nocturnes ou avant version**, jamais bloquants pour une fusion | — |
| Ports : `WakeSignal`, `ReadCache` | — | **Différés** | avec les mécanismes Redis correspondants |

### 0.4 Structure du dépôt : démonstration (TD54)

Deux structures ont été comparées. **Elles ne sont pas choisies parce qu'elles paraissent professionnelles** : chacune est jugée sur les violations qu'elle rend impossibles.

```text
A. Par couche (proposée)                  B. Par module (retenue)
verqia/                                   verqia/
├── domain/{invoices,payments,…}          ├── kernel/            (pur)
├── application/{commands,queries,…}      ├── platform/  events/  audit/
├── infrastructure/{postgres,redis,…}     ├── invoices/
└── interfaces/{api,admin}                │     ├── domain/  application/  infrastructure/  api/
                                          │     └── contracts/         ← seule surface importable
                                          ├── payments/  collection/  rules/  …
                                          └── config/  jobs/            (pilotes, sans règle)
```

| Violation à rendre impossible | A. Par couche | B. Par module |
|---|---|---|
| Un module lit les internes d'un autre (I3) | `domain/collection` peut importer `domain/invoices/…` : le motif de couches ne l'interdit pas ; il faut **en plus** une règle module × module | **une seule règle** : seul `contracts` est importable |
| Un module écrit la table d'un autre (I4) | `infrastructure/postgres` contient les 41 tables : **une seule application Django**, un seul historique de migrations ; la frontière de propriété disparaît | **une application par module**, un historique par module, graphe de schéma vérifiable (TD10) |
| Localité d'un changement | ajouter une colonne à une facture touche quatre répertoires racines, mélangés aux autres modules | un répertoire |
| Le Domain dépend de l'infrastructure (I1) | interdit par la règle de couches | interdit par la **même** règle de couches, dans chaque module |
| Nombre de règles d'import à maintenir | couches × modules | deux règles génériques et la table d'arêtes du §2.3 |
| Un module sans règle (`message_templates`) | doit exister dans quatre couches | n'a que `application` et `infrastructure` minces |
| Vue globale du Domain | naturelle | rapport généré (la liste des `domain/`) : perte négligeable |

**Équité.** A peut être sous-divisée par module partout (`infrastructure/postgres/invoices/`…) : elle devient alors **la structure B transposée**, sans gain. **Retenue : B**, avec deux emprunts à A : (a) `application/` se divise en `commands/` et `queries/` (TD3), et `orchestration/` n'existe que dans `automation` et `jobs` ; (b) `interfaces` devient `api/` et `admin/` **par module**, composés par `config`.

**TD54.** La structure est B. Elle est **démontrée par des tests d'injection de violation** (TA-34) : pour chaque règle `AR-*`, un test **injecte volontairement** la violation dans un module d'essai et vérifie que la porte **échoue**. Une porte qui n'a jamais échoué n'est pas prouvée.

---

## 1. TA1 — Principes architecturaux

### 1.1 Décisions

| # | Décision | Justification | Alternative écartée |
|---|---|---|---|
| **TD1** | **Monolithe modulaire** : un dépôt, une base PostgreSQL, un même code déployé sous **deux types de processus** en V1 (`web`, `worker` : §6.4). Pas de micro-services en V1. | Les écritures synchrones inter-agrégats (C12 : deux familles nominatives) exigent une base et une transaction communes ; découper aujourd'hui imposerait des sagas pour des invariants financiers. Les frontières sont imposées par des tests (§10), pas par le réseau. | Micro-services : outbox distribué, cohérence éventuelle sur l'argent |
| **TD2** | **Quatre couches par module** : `api` → `application` → `domain` ← `infrastructure`. Le Domain est pur (entités, valeurs, tables de transitions, fonctions de décision). L'Application possède les **transactions**, orchestre, appelle les ports. L'Infrastructure implémente les ports. Les **modèles Django sont des modèles de persistance** (infrastructure), pas les entités du Domain ; un dépôt (*repository*) fait la correspondance. **Le Domain n'est requis que pour les agrégats porteurs d'une règle d'état ou d'argent** (factures, paiements, promesses, actions, exécutions, approbations, lots d'import, clients, moteurs). Les modules sans règle (contacts, réglages, gabarits, utilisateurs) n'ont qu'un service d'application mince ; **aucun modèle ne contient de logique**. | DR1 est absolu ; un modèle Django dans le Domain l'enfreint. Le coût de la correspondance est borné à ce qui porte un invariant. | *Active Record* partout : rapide, mais le Domain connaîtrait l'ORM ; *Domain riche* partout : mécanique sans bénéfice |
| **TD3** | **Commandes et requêtes séparées.** Les écritures passent par le Domain. Les lectures d'écran (listes, tableaux de bord, exports) passent par des **services de requête** du module, en lecture seule, sans règle métier, sur **les tables de leur propre module** (DR2). Une **décision** (Rule Engine) ne lit jamais par un service de requête, un cache ni un réplica (X1). | Évite un Domain surchargé de lectures d'affichage, sans ouvrir de contournement des règles. | Tout passer par le Domain : lent et sans bénéfice |
| **TD4** | **Surface publique d'un module = son paquet `contracts`** : ports, commandes, DTO, types d'événements, codes d'erreur. Tout le reste est privé. Un autre module n'importe **que** `contracts`. | Rend DR2 et DR9 vérifiables par un simple test d'import. | Conventions orales |
| **TD5** | **Une racine de composition** (`config`) : seul endroit qui connaît les adaptateurs concrets et assemble ports et adaptateurs. Injection explicite ; pas de localisateur de services global ni de singleton importé. | Le Domain reste testable avec des doubles en mémoire ; un port sans adaptateur de test est refusé (TD51). | Registre global : dépendance cachée |
| **TD6** | **Séparation des moteurs** : `rules` est pur ; les moteurs d'action (`collection`, `automation`) n'écrivent aucune projection ; les moteurs de projection (`risk`, `priority`, `cashflow`) n'écrivent aucune action (X5) ; chaque agrégat n'a qu'**un point d'entrée d'écriture**, dans le module propriétaire (X14). | Un défaut dans un moteur ne peut pas corrompre l'état d'un autre. | Moteurs partageant des écritures |

### 1.2 Interdictions architecturales

Chacune est une règle **exécutable** de la porte d'architecture (§10, `AR-*`).

| # | Interdiction |
|---|---|
| **I1** | Le Domain importe Django, Redis, psycopg, un SDK de fournisseur ou une bibliothèque réseau |
| **I2** | Le Domain ou l'Application lit l'horloge système (`now`, `today`, `time`, `timezone.now`, `now()` SQL hors adaptateur `Clock`) |
| **I3** | Un module importe autre chose que le `contracts` d'un autre module |
| **I4** | Un module lit ou écrit une table d'un autre module (ORM ou SQL) |
| **I5** | Une projection est écrite par un autre module que son moteur |
| **I6** | Un statut d'action de recouvrement change sans passage par `rules.evaluate` (sauf les transitions de résultat d'envoi) |
| **I7** | `automation` crée ou modifie une action autrement que par `collection.contracts` |
| **I8** | Un appel externe (e-mail, HTTP, Redis d'effet) à l'intérieur d'une transaction de base |
| **I9** | Redis ou toute mémoire de processus sert de source de vérité |
| **I10** | Une règle métier dans une vue, un sérialiseur, une migration, un signal Django ou l'administration |
| **I11** | Un signal Django ou un `on_commit` porte un **effet** métier (aucun `on_commit` n'a d'effet métier) |
| **I12** | SQL brut, `select_for_update` ou verrou consultatif hors de l'infrastructure de persistance et du `LockManager` |
| **I13** | L'administration Django écrit une table SOURCE ou LOG (TD14) |

### 1.3 Contre-exemples

| # | Scénario | Ce qui casse sans la décision | Décision |
|---|---|---|---|
| **CX1** | Une vue DRF appelle `invoice.save()` après avoir « vérifié le solde » | la règle est dupliquée dans l'API ; un second point d'entrée écrit sans elle | TD2, I10 |
| **CX2** | Un écran de facture lit les faits via un cache de tableau de bord pour décider d'une relance | une décision prise sur une lecture périmée (X1) | TD3 |
| **CX3** | `collection` lit directement `invoice_disputes` pour aller plus vite | une migration de `invoices` casse `collection` sans qu'aucun test le voie | TD4, I4 |

---

## 2. TA2 — Découpage Django

### 2.1 Modules (TD7)

**TD7.** Le système est découpé en **22 unités** (21 paquets en V1 : `billing` reste un emplacement réservé, TD7 et §0.3). La liste demandée est conservée ; **six unités** y sont ajoutées parce que les documents figés les supposent déjà (`identity`, `billing`, `approvals` : §13.1 ; `kernel`, `platform`, `config` : socle) et `jobs` est précisé comme **exécution**, pas comme domaine.

| Groupe | Module | Nature | Tables propriétaires (Contrat §13) |
|---|---|---|---|
| Socle | `kernel` | bibliothèque **pure** (aucun framework) : `Money`, identifiants, `CallContext`, `DomainError`, calendrier ouvré, base des machines à états, **ports partagés** | — |
| Socle | `platform` | infrastructure liée à Django, partagée : adaptateurs `TransactionManager`, `LockManager`, `Clock`, `IdGenerator`, `TenantContext`, traduction des erreurs SQL, gabarits de migration (RLS, triggers, partitions), métriques | `idempotency_keys` |
| Socle | `events` | outbox, relais, registre des types et des handlers, registre de schémas, `ReplayDeadEvent` | `events`, `event_receipts` |
| Socle | `audit` | écriture d'audit, procédures d'anonymisation | `audit_logs` |
| Identité | `identity` | utilisateurs, appartenances, rôles, authentification | `users`, `memberships` |
| Identité | `organizations` | organisation, réglages, calendrier | `organizations`, `org_settings`, `org_holidays` |
| Sources | `customers` | clients, contacts | `customers`, `customer_contacts` |
| Sources | `invoices` | factures, lignes, litiges, cycle de vie | `invoices`, `invoice_items`, `invoice_disputes`, `invoice_state_history` |
| Sources | `payments` | paiements, allocations, annulations | `payments`, `payment_allocations`, `payment_reversals` |
| Sources | `promises` | promesses de paiement | `promises`, `promise_history` |
| Sources | `imports` | lots d'import, staging | `import_batches`, `import_rows` |
| Décision | `rules` | Rule Engine : fonction pure `évaluer` ; **sans table** ; définit les ports de faits | — |
| Projections | `risk` | risque | `risk_profiles`, `risk_snapshots` |
| Projections | `priority` | priorité | `priority_items`, `priority_snapshots` |
| Projections | `cashflow` | trésorerie | `cashflow_runs`, `cashflow_lines` |
| Action | `approvals` | approbations et revues | `approvals` |
| Action | `collection` | actions, holds, tentatives | `collection_actions`, `collection_holds`, `collection_action_attempts` |
| Action | `notifications` | notifications, gabarits, envoi | `notifications`, `notification_deliveries`, `message_templates` |
| Orchestration | `automation` | définitions, versions, exécutions, étapes | `automations`, `automation_versions`, `automation_executions`, `automation_execution_steps` |
| Commerce | `billing` | **vide en V1** (S7 non spécifié) : emplacement réservé | `plans`, `subscriptions` |
| Pilotage | `jobs` | **exécution** : registre des travaux, planificateur, coureurs ; **aucune règle** | — |
| Pilotage | `config` | racine de composition, réglages, routage HTTP | — |

Nom : le module s'appelle **`collection`** (singulier). Les documents disent `collections` ; un paquet `collections` masquerait la bibliothèque standard de Python. Tout le code vit sous un paquet racine `verqia.*` (TD8).

### 2.2 Décisions structurantes

| # | Décision | Justification |
|---|---|---|
| **TD8** | **Un module = une application Django**, sous l'espace de noms `verqia.<module>` ; structure `domain/ application/ infrastructure/ api/ contracts/`. Les tables gardent les **noms du contrat** (`db_table` explicite), pas les noms générés par Django. | Le contrat est figé ; les noms de tables sont son interface. Un espace de noms évite les collisions avec la bibliothèque standard. |
| **TD9** | **Références inter-modules par identifiant.** Un modèle ne référence jamais le modèle d'un autre module par clé étrangère d'ORM ; il stocke un `UUIDField` (`db_constraint=False`), et la **contrainte est posée en SQL** (`RunSQL`) par la migration du module **référençant** (FK composites `(organization_id, id)`, contrat §0). | Un import de modèle inter-modules enfreindrait I3 ; le DB porte quand même l'intégrité. |
| **TD10** | **Trois graphes distincts, chacun vérifié.** (1) Le graphe des **appels** (contrats synchrones, lectures, ports, fournisseurs de faits) : **sans cycle**. (2) Le graphe des **événements** (qui écoute qui) : une dépendance d'événement n'est **pas** une dépendance d'appel ; un cycle purement événementiel est admis si `contracts.events` est une feuille (types seuls). (3) Le graphe de **schéma** (ordre des migrations) : sans cycle. Les trois peuvent aller en sens opposés : `automation` appelle `collection`, mais `collection_actions.automation_execution_id` fait dépendre le **schéma** de `collection` de celui d'`automation`. | Un cycle de schéma rend les migrations impossibles à ordonner ; un cycle d'appel rend l'import impossible ; les mélanger crée des cycles artificiels. Le registre calcule les trois et échoue sur les deux premiers cas (§5 du registre). |
| **TD11** | **`approvals` devient un module** (écart §13.1-A). Le contrat donne la table `approvals` à `automation`, alors que `collection` crée des approbations pour ses actions (`collection_action_id`) et que DR4 lui interdit d'appeler `automation`. Les deux moteurs appellent `approvals.contracts` ; `approvals` publie `APPROVAL_*` ; il valide sa cible par un port (`ApprovalTargetReader`) implémenté par chacun. | Sans cela, une règle gelée (DR4) et un flux gelé (approbation d'une action) se contredisent. |
| **TD12** | **Faits par inversion de dépendance** (écart §13.1-D). `rules.contracts` **déclare** un fournisseur de faits par famille ; chaque module propriétaire l'**implémente** dans son infrastructure ; `config` les branche dans le `FactReader`. `rules` n'importe donc **aucun** autre module. | Les faits `hold_active`, `highest_level_reached`, `reminders_30d` viennent des tables de `collection` ; `collection` appelle `rules`. Si `rules` lisait `collection`, les deux modules s'importeraient mutuellement (cycle, DR5). |
| **TD13** | **Le registre d'événements est inversé** : chaque module **déclare** ses types d'événements et ses handlers dans son `contracts` ; `events` les **collecte** au démarrage. `events` n'importe aucun producteur. | Sinon `events` dépendrait de tous les modules, et tous de `events` (cycle). |
| **TD14** | **L'administration Django est en lecture seule** sur toute table SOURCE ou LOG en V1 ; aucune écriture n'y contourne un cas d'usage. | Un formulaire d'admin écrit sans règle, sans audit, sans événement (I10, I13). |

### 2.3 Arêtes d'import autorisées (module → `contracts` d'un autre module)

**Le Module Registry fait foi** (`ARCHITECTURE_REGISTRY_V1.md` §1) : ce tableau en est le résumé. Les dépendances y sont **requises** par les appels, les abonnements, les lectures et les ports implémentés ; une dépendance non requise ou non déclarée fait échouer la porte. Le registre a ajouté des arêtes que la première rédaction n'avait pas vues : `promises → payments` (`PAYMENT_ALLOCATED`), `priority → collection` (événements de hold et d'action), `payments → customers`, `automation → risk, priority, imports`, `organizations → rules` (fournisseur de faits) ; et il inverse `identity → organizations` (l'appartenance du propriétaire est un *pas de provisioning* implémenté par `identity`, TD12).

| Module | Peut importer les `contracts` de (Module Registry) |
|---|---|
| `kernel` | rien |
| `platform` | rien |
| `events` | `platform` |
| `audit` | `platform` |
| `identity` | `organizations` |
| `organizations` | `rules` |
| `customers` | `organizations`, `rules` |
| `invoices` | `organizations`, `customers`, `rules` |
| `payments` | `organizations`, `customers`, `invoices`, `rules` |
| `promises` | `organizations`, `customers`, `invoices`, `payments`, `rules` |
| `imports` | `organizations`, `customers`, `invoices`, `payments`, `rules` |
| `rules` | rien |
| `risk` | `organizations`, `customers`, `invoices`, `payments`, `promises`, `rules` |
| `priority` | `organizations`, `customers`, `invoices`, `payments`, `promises`, `risk`, `collection`, `rules` |
| `cashflow` | `organizations`, `customers`, `invoices`, `payments`, `promises`, `risk` |
| `approvals` | rien |
| `collection` | `rules`, `notifications`, `approvals`, `organizations`, `customers`, `invoices`, `promises` |
| `notifications` | `organizations`, `customers`, `identity` |
| `automation` | `rules`, `collection`, `notifications`, `approvals`, `organizations`, `customers`, `invoices`, `payments`, `promises`, `risk`, `priority`, `imports` |
| `billing` | `organizations` |
| `jobs`, `config` | tous (pilotes : ils **n'ont pas de règles**, TD46) |

Les modules qui fournissent des faits (`organizations`, `customers`, `invoices`, `payments`, `promises`, `imports`, `collection`, `risk`, `priority`) **importent** `rules.contracts` pour implémenter leurs fournisseurs : c'est une dépendance d'**interface**, pas un appel d'une source vers un moteur (précision de DR4, §13.2).

### 2.4 Ordre des migrations (dépendances de schéma)

```text
organizations → identity ; organizations → customers → invoices → payments
                       → promises → imports (invoices/customers/payments.import_batch_id : FK vers imports)
automation → collection → approvals
risk, priority, cashflow, notifications (après leurs sources)
events, audit, platform : aucune FK entrante (pas de FK, partitions)
```

`invoices`, `customers` et `payments` référencent `imports` (`import_batch_id`) alors qu'`imports` **appelle** ces modules à l'exécution : c'est le cas typique de graphes opposés (TD10). Les migrations d'`imports` créent donc la table avant celles des sources qui la référencent.

### 2.5 Contre-exemples

| # | Scénario | Ce qui casse | Décision |
|---|---|---|---|
| **CX4** | `collection` crée une approbation en écrivant dans `approvals` (module d'`automation`) | I4 violée, ou DR4 violée si elle appelle `automation` | TD11 |
| **CX5** | `rules` importe `collection.infrastructure` pour lire `collection_holds` ; `collection` importe `rules` | cycle d'import ; le Rule Engine cesse d'être pur | TD12 |
| **CX6** | `events` importe les types d'événements de chaque module | `events` dépend de tout ; l'ajout d'un module modifie `events` | TD13 |
| **CX7** | Un module `collections` masque la bibliothèque standard `collections` | échecs d'import sans rapport avec le métier | TD8 |
| **CX8** | La migration d'`invoices` s'exécute avant celle d'`imports` alors que `invoices.import_batch_id` référence `import_batches` | déploiement impossible sur base vide | TD10 |
| **CX39** | Un handler écrit `invoice.outstanding_minor -= montant` « pour aller plus vite » | l'état est modifié hors de son propriétaire et hors de la fonction de transition : T4 échoue au COMMIT, ou pire, passe | TD55 |
| **CX42** | `collection` écrit la ligne `approvals` dans la transaction de l'action : « c'est atomique » | `collection` écrit un état d'`approvals` : propriété violée, C12 étendu en silence ; approbation et action ne peuvent plus évoluer séparément | TD55, TD58 |

### 2.6 Propriété des écritures et registres (TD55 à TD57)

| # | Décision |
|---|---|
| **TD55** | **Propriété des écritures.** Pas seulement « un module possède ses tables » : **un état métier n'est écrit que par un ensemble fermé de cas d'usage du module propriétaire, par la fonction de transition du Domain.** Les franchissements de module sont les exceptions **C12**, dont la liste est **fermée et nominative** : `AllocatePayment`, `ReverseAllocation`, `ReversePayment` (et son service interne `ApplySettlement`), `NormalizeImportBatch`. **Aucune formule ouverte** (« et opérations similaires ») : le registre porte la liste, et un drapeau C12 hors liste fait échouer la porte. `CreateOrganization` en sort (TD59). Personne d'autre ne peut faire `invoice.outstanding_minor -= montant`. Garanties : **E1** colonnes générées, caches vérifiés en fin de transaction (T4, T5), garde de transition (T14) ; **E2** aucun dépôt d'écriture importable hors du module propriétaire, aucun mutateur libre sur l'agrégat ; **E3** le Command Registry déclare les écrivains de chacun des **32 états**. |
| **TD56** | **Quatre registres exécutables** avant toute structure Django ou schéma : **Module**, **Commande**, **Événement**, **Verrou**. Ils sont la **source** ; les règles `AR-*` en sont **générées** ; `ARCHITECTURE_REGISTRY_V1.md` en est le rendu. La porte `build_registry.py --check` vérifie : tables ↔ contrat ; écrivains ↔ propriétaires ; événements ↔ catalogue (un événement contractuel est au catalogue, ou classé technique, ou en **amendement en attente**) ; **tout événement sans abonné est classé A (volontaire), B (autre passe) ou C (oublié : la porte échoue)** ; listes de rafraîchissement ↔ documents ; **trois graphes** (TD10) ; verrous ↔ EC5 ; **transactions inter-modules** (TD58). `--freeze` échoue tant qu'un nom de commande est provisoire. Ordre : *registres → tests d'architecture → structure Django → schéma PostgreSQL*. `test_registry.py` **injecte** des violations pour prouver que la porte échoue (TA-35). |
| **TD57** | **Un module n'existe pas sans sa fiche**, qui déclare quatre choses obligatoires : ce qu'il **possède** (tables), ce qu'il **écrit** (commandes), ce qu'il **lit** (requêtes publiées), ce qu'il **publie et consomme** (événements). Sans fiche, aucun code n'est accepté dans le module : c'est ce qui empêche les modules de devenir de mini-applications indépendantes. |
| **TD58** | **Composition orchestrée : un service d'enregistrement dépendant ne devient jamais propriétaire.** Quand un cas d'usage a besoin qu'un autre module enregistre quelque chose (approbation, notification, étape de provisioning, exécution), il **demande** à ce module d'exécuter **son propre** cas d'usage, **dans la transaction de ce module** (préfixe `own:` du registre). L'appelant ne détient ni l'état, ni la transition, ni la persistance de l'autre module. Chaque pas est **idempotent** (clé de déduplication) et un **balayage** reprend un processus interrompu (`ResumeProposedActions`, `ResumeProvisioning`). Une action est ainsi créée `PROPOSED` (transaction de `collection`), l'approbation est demandée (transaction de `approvals`), puis l'action passe `PENDING_APPROVAL` (transaction de `collection`) ; l'exécution d'une action est *claim + revalidation* (`collection`), *création de la notification* (`notifications`), *envoi*, *résultat*. **C12 n'est pas étendu.** |
| **TD59** | **Plan de provisioning.** `CreateOrganization` n'écrit que l'organisation et ses réglages, à l'état **`PROVISIONING`** (amendement : State Machines §1 et contrat), puis exécute chaque **étape** du port `organizations.ProvisioningStep`, **chacune dans sa transaction, avec son propriétaire, son idempotence `(organisation, étape)` et son résultat** : appartenance du propriétaire (`identity`), abonnement d'essai (`billing` : contrat minimal, aucune règle d'autorisation avant S7), automatisations par défaut (`automation`). `CompleteProvisioning` passe l'organisation `ACTIVE` et émet `ORGANIZATION_CREATED` quand toutes les étapes sont faites ; `ResumeProvisioning` reprend une organisation restée `PROVISIONING`. Tant qu'elle l'est, aucune commande métier n'y est acceptée (`ORG_NOT_ACTIVE`) et les décisions la traitent comme inactive (`ORG_INACTIVE`). `organizations` ne dépend ni de `billing` ni d'`automation` : ce sont eux qui **implémentent** le port. |

**Convention de nommage des cas d'usage (figée).** Vérifiée par `build_registry.py` : un préfixe a un sens, et la porte échoue s'il est détourné.

| Préfixe | Sens |
|---|---|
| `Provision*` | implémentation d'une `ProvisioningStep` |
| `Create*`, `Add*`, `Update*`, `Change*` | commande métier, verbe **aligné** sur l'événement émis (`CreateCustomer` → `CUSTOMER_CREATED`) |
| `Start*` | démarrage d'un processus |
| `Complete*` | achèvement d'un processus |
| `Resume*` | reprise par balayage |
| `Read*` | service de lecture, implémentation d'un port `*Reader` |
| `Notify*` | handler de notification |

L'unicité d'un nom n'est **pas** un invariant d'architecture : le couple `(module, nom)` identifie le composant (`ReadApprovalTarget` existe dans `collection` et dans `automation`).

**Coût assumé de TD58.** Des états intermédiaires deviennent visibles : `PROPOSED` sans approbation encore, `EXECUTING` sans notification encore. Ce sont déjà des états du contrat, repris par un balayage ou par le `Reaper`. L'expiration d'une approbation dont la cible est résolue ne se fait plus par une écriture de `collection` dans `approvals` : `approvals` interroge la cible par le port `ApprovalTargetReader` (implémenté par `collection` et `automation`), avec un retard borné par la cadence du balayage (5 min) ; `DecideApproval` vérifie la cible au moment de décider.

Exemple de fiche, telle que le registre la génère pour `payments` :

```text
payments
├── possède      payments, payment_allocations, payment_reversals
├── commandes    CreatePayment · AllocatePayment (C12) · ReverseAllocation (C12) · ReversePayment (C12)
├── requêtes     PaymentFacts · UnallocatedPayments
├── événements   produit  PAYMENT_CREATED · PAYMENT_ALLOCATED · PAYMENT_ALLOCATION_REVERSED · PAYMENT_REVERSED
│                consomme aucun
└── dépend de    customers · invoices · organizations · rules
```

**Ce que les registres ont déjà trouvé** (détail : `ARCHITECTURE_REGISTRY_V1.md` §5 et §13.1 ci-dessous) : un ordre de verrous incohérent, des écritures inter-modules non déclarées, des dépendances manquantes, un flux d'automatisation contradictoire avec C12 ; ils ne sont donc pas décoratifs.

---

## 3. TA3 — PostgreSQL

### 3.1 Décisions de schéma

| # | Décision | Justification |
|---|---|---|
| **TD15** | **Une base, un schéma `verqia`** ; `search_path` fixé par rôle ; le schéma `public` est vide et révoqué. Pas de schéma par module en V1. | Un schéma par module ne renforcerait rien tant qu'un seul rôle applicatif accède à tout ; l'isolation entre modules est portée par l'import (TD4) et par le test d'architecture. |
| **TD16** | **Les contraintes du contrat sont créées par migrations SQL versionnées** (`RunSQL` avec inverse) : FK composites, `CHECK`, `EXCLUDE`, index partiels, triggers T1 à T15, RLS, partitions. Chaque contrainte reçoit un **nom stable** (`ck_…`, `uq_…`, `fk_…`, `t07_…`). Un test compare le **catalogue PostgreSQL réel** au contrat (O9). | Le nom stable rend la traduction d'erreurs possible (TD19) ; le test empêche toute dérive silencieuse. |

### 3.2 Isolation des organisations : qui est responsable, et pourquoi (TD17)

**TD17.** Trois mécanismes, **de responsabilités différentes** ; aucun n'est décoratif.

| Couche | Ce qu'elle garantit | Ce qu'elle **ne** garantit **pas** | Défaillance qu'elle rattrape |
|---|---|---|---|
| **A. Application** (`TenantContext` obligatoire ; dépôts et gestionnaires d'ORM **refusent** toute requête sans organisation) | le comportement : un sujet d'une autre organisation est `NOT_FOUND`, jamais `FORBIDDEN` (Engine Contracts §0.4) ; c'est le **chemin normal** | rien contre un développeur qui l'oublie | — |
| **B. Structure** (`organization_id NOT NULL`, FK composites) | **l'intégrité des écritures** : une ligne ne peut référencer le parent d'une autre organisation ; les vérifications de clé étrangère **ne passent pas par RLS** (vérifié : PG-10) | aucune protection **en lecture** : une requête sans filtre lit tout | un `INSERT` ou `UPDATE` mal ciblé |
| **C. RLS** (`app.organization_id` local à la transaction ; échec fermé) | **le filet en lecture et en écriture** : sans organisation posée, **aucune ligne** n'est visible ; une requête sans filtre ne voit que l'organisation courante | ne remplace ni A (pas de `NOT_FOUND` sémantique) ni B | un oubli de filtre en A ; une requête brute ; un rapport ad hoc |

**Pourquoi RLS malgré son coût.** Les FK composites ne protègent pas la **lecture** ; seul le code applicatif ou RLS l'empêchent. La lecture inter-organisations est l'incident de sécurité le plus grave d'un SaaS multi-organisation ; un seul filtre oublié suffit. RLS est ajoutée **pour cette raison précise**, pas par habitude.

**Normatif : RLS est un filet, jamais un chemin.** Le chemin normal est *requête → `TenantContext` → application → domain → repository → PostgreSQL (RLS)*. Jamais *requête → SQL quelconque → « RLS s'en occupe »*. Le dépôt et le gestionnaire d'ORM **refusent** toute requête sans organisation, **même si RLS la filtrerait** : RLS qui filtre en fonctionnement normal masque un défaut (zéro ligne, aucune erreur). Toute ligne masquée par RLS en production est un **signal de défaut** (métrique et alerte). La suite métier doit donner les **mêmes résultats avec RLS désactivée** (TA-07) : c'est ce qui prouve que RLS n'est pas le mécanisme normal.

**Coût assumé.** (1) Chaque transaction pose l'organisation par **un seul point** (le `TransactionManager`, jamais un appel épars). (2) Les traitements **transversaux** (relais, planificateur) ne contournent pas RLS : ils utilisent des **rôles dédiés avec une politique nommée** (TD18), jamais `BYPASSRLS`. (3) Sur les tables partitionnées, les politiques sont sur le **parent**, et l'accès direct aux partitions est refusé aux rôles d'exécution. (4) Un test d'introspection vérifie, pour chaque table portant `organization_id`, que RLS est active, qu'une politique existe et que le rôle d'exécution n'est pas propriétaire (DB-16, G01).

### 3.3 Rôles PostgreSQL (TD18)

**TD18.** Quatre rôles, chacun au **moindre privilège** (la première version en proposait six : `verqia_scheduler` et `verqia_ops` sont supprimés, §0.3). Aucun n'est superutilisateur ni `BYPASSRLS`.

| Rôle | Usage | Privilèges | RLS |
|---|---|---|---|
| `verqia_owner` | **migrations uniquement** ; jamais à l'exécution ; propriétaire des objets et des fonctions `SECURITY DEFINER` | DDL | exempté (propriétaire) |
| `verqia_app` | `web` et `worker` (transactions métier, planificateur, purges techniques) | `SELECT/INSERT/UPDATE` selon la table ; **pas de `DELETE`** sur SOURCE et LOG, **sauf** `event_receipts` et `idempotency_keys` (purges techniques, contrat §18) ; **pas d'`UPDATE`** sur LOG (T8) ; pas de `TRUNCATE` ; pas propriétaire ; `EXECUTE` sur **deux** fonctions `SECURITY DEFINER` : `list_active_organizations()` (identifiant, fuseau, statut : rien d'autre) et `ensure_partitions()` (crée les partitions futures de `events` et `audit_logs` ; aucun autre DDL) | **appliquée**, échec fermé |
| `verqia_relay` | outbox : réclamer les événements et les reçus `RETRYING` | `SELECT` sur `events` ; `UPDATE` **au niveau des colonnes** de publication (`published_at`, `publish_attempts`, `last_error`, `available_at`) ; `SELECT` et `UPDATE` des colonnes `available_at`, `attempts`, `last_error` de `event_receipts` | politiques nommées `TO verqia_relay` : `events` (`USING (true)`), `event_receipts` (`USING (outcome = 'RETRYING')`) |
| `verqia_privacy` | anonymisation | `UPDATE` colonne par colonne (contrat §17) | politique par organisation |

Les fonctions `SECURITY DEFINER` ont un `search_path` fixé, aucun paramètre libre et un corps minimal : c'est **l'unique** lecture inter-organisations du rôle applicatif, et elle ne porte que sur l'énumération des organisations. Le relais lit toutes les organisations parce que ses **deux politiques nommées** l'y autorisent, sur `events` et sur les seuls reçus `RETRYING` : aucune donnée métier. Les gestionnaires d'événements s'exécutent ensuite sous `verqia_app`, **avec l'organisation de l'événement** (TD26).

### 3.4 Migrations (TD19 à TD21)

| # | Décision |
|---|---|
| **TD19** | **Les erreurs de base sont traduites, pas propagées.** Le `TransactionManager` traduit SQLSTATE et **nom de contrainte** en `DomainError` (registre généré) : violation d'unicité de `dedup_key` → `REPLAY` ; `40001` / `40P01` → `SERIALIZATION_FAILURE` ; version périmée → `CONCURRENT_MODIFICATION`. Les triggers différés échouent **au `COMMIT`** : la traduction couvre donc aussi l'erreur de validation. Une violation d'invariant qui atteint la base **sans** avoir été arrêtée par le Domain est un **défaut** : erreur `INTERNAL` et alerte (le Domain doit arrêter avant la base ; la base est la dernière défense). |
| **TD20** | **Migrations : *expand → migrate → contract*.** Le code N doit fonctionner avec les schémas N et N+1. Interdits sans procédure : `ADD COLUMN NOT NULL` avec valeur par défaut coûteuse, `CREATE INDEX` non concurrent, contrainte validée d'un bloc. Obligatoires : `lock_timeout` court, index `CONCURRENTLY` (migration non atomique), contraintes `NOT VALID` puis `VALIDATE`. Les artefacts **générés** (T14, catalogue d'erreurs, registre de schémas) sont vérifiés à jour en intégration continue. Exécution sous `verqia_owner`, dans une **phase de publication** distincte du démarrage des processus. |
| **TD21** | **Compatibilité pooler en mode transaction** : aucun état de session. Autorisés : `SET LOCAL`, verrous consultatifs **de transaction** (`pg_advisory_xact_lock`). **Interdits** : verrous consultatifs de session, `LISTEN/NOTIFY` comme mécanisme **unique**, tables temporaires de session, curseurs côté serveur au-delà d'une transaction. |

### 3.5 Isolation, temps, partitions

| # | Décision |
|---|---|
| **TD22** | **Recherche d'un événement par identifiant.** `events` est partitionnée par `occurred_at` ; un identifiant seul ne permet pas l'élagage. L'identifiant (UUIDv7) est produit par `IdGenerator`, dont **l'instant vient du `Clock`** : l'instant de l'UUID et `occurred_at` proviennent tous deux de `as_of` et coïncident à la milliseconde près. Toute recherche (`ReplayDeadEvent`, reprise d'un handler, support) borne donc `occurred_at ∈ [instant_uuid − 10 s, instant_uuid + 10 s]` : **une ou deux partitions** à la frontière de mois. Le banc de simulation crée les partitions de l'horizon simulé. |
| **TD23** | **Trois notions de temps, jamais confondues.** (1) **Temps métier** : `as_of`, fourni par le port `Clock`, seule heure que voient le Domain et l'Application ; **toute colonne temporelle qu'ils écrivent** (`created_at`, `occurred_at`, `executed_at`, `resume_at`, `available_at`…) est **écrite explicitement depuis `as_of`**. (2) **Temps technique de la base** : `now()` en `DEFAULT`, simple filet pour les lignes insérées hors application (migration, correctif manuel) ; **jamais lu par une règle, jamais utilisé dans le SQL de l'application** (`WHERE échéance < :as_of`, jamais `< now()`). (3) **Temps système des hôtes** : jamais une source de temps métier ; il ne sert qu'à mesurer des durées (délais, métriques). L'**adaptateur de production** du `Clock` capture l'horodatage de transaction de la base au début de l'unité de travail : c'est un **détail d'adaptateur**, justifié par la **comparabilité entre travailleurs** (un bail écrit par un hôte est lu par un autre) ; le Domain ne connaît ni la base ni cette source (X12, TI1). En test, l'horloge virtuelle **remplace** l'adaptateur : aucune valeur écrite ne coïncide alors avec l'heure réelle, ce qui prouve que le `DEFAULT now()` n'est jamais utilisé. La dérive entre hôtes et base est surveillée (alerte au-delà de 500 ms, valeur initiale) pour détecter une défaillance NTP. *Alternative : horloge d'hôte + NTP derrière le même port : acceptable pour un déploiement monohôte, écartée comme adaptateur de production parce que les baux et les dates locales se comparent entre hôtes.* |
| **TD24** | **La base de fuseaux IANA (`tzdata`) est versionnée avec l'image.** Sa mise à jour est un changement de version **annoncé** (elle peut modifier une date locale future) ; aucune date locale dérivée n'est stockée hors `decision_snapshot`. |

### 3.6 Contre-exemples

| # | Scénario | Ce qui casse | Décision |
|---|---|---|---|
| **CX9** | Un rapport ad hoc `SELECT * FROM invoices` sans filtre | lecture de toutes les organisations | TD17 C |
| **CX10** | Le relais tourne avec `BYPASSRLS` pour lire l'outbox | un défaut du relais lit toutes les tables métier | TD18 |
| **CX11** | Une allocation dépasse le solde ; T2 échoue au **COMMIT** ; l'API renvoie un 500 | l'erreur n'est pas traduite ; le client ne sait pas quoi corriger | TD19 |
| **CX12** | `CREATE INDEX` non concurrent sur `events` en production | verrou d'écriture sur l'outbox : plus aucun événement ne s'émet | TD20 |
| **CX13** | Un verrou consultatif de session posé derrière un pooler en mode transaction | il reste attaché à une connexion réutilisée par un autre appelant | TD21 |
| **CX14** | Un paiement enregistré à 23:59:59.9 selon l'hôte, évalué à 00:00:00.1 selon la base | la date locale d'enregistrement et la date d'évaluation divergent ; la fenêtre de rapprochement est fausse d'un jour | TD23 |
| **CX41** | Un paiement est écrit avec `created_at DEFAULT now()` de la base alors que l'horloge virtuelle du banc simule une autre date | la date locale d'enregistrement (fenêtre de rapprochement) est celle de l'heure réelle : tests faux, ou pire, fenêtre fausse en production si l'horloge d'adaptateur diffère | TD23 |
| **CX37** | Un développeur écrit une requête sans filtre d'organisation : « RLS filtrera » | en production, zéro ligne, aucune erreur : le défaut de conception reste invisible ; un jour RLS est désactivée pour un rapport, tout fuit | TD17, TI18 |
| **CX43** | `CreateOrganization` écrit l'organisation, l'appartenance, l'abonnement et les automatisations dans une seule transaction, en important `billing` et `automation` | `organizations` dépend de `automation`, qui dépend d'`organizations` : cycle d'appel ; Billing est implémenté avant sa spécification (S7) | TD59 |
| **CX44** | `IMPORT_BATCH_COMMITTED` n'a aucun abonné : « c'était peut-être prévu » | les lots restent `COMMITTED` pour toujours, sans erreur ni alerte | TD56 |

---

## 4. TA4 — Transactions et concurrence

### 4.1 Décisions

| # | Décision | Justification |
|---|---|---|
| **TD25** | **Un cas d'usage = une unité de travail = une transaction.** Les frontières de transaction sont ouvertes **uniquement** par la couche Application (via `TransactionManager`). Un cas d'usage appelé par un autre **rejoint** la transaction de l'appelant (arêtes synchrones du §2.3 seulement) ; aucun point de sauvegarde implicite. Ce qui n'est pas une arête synchrone passe par l'outbox. | Aucune frontière ambiguë ; un échec annule tout ou rien (tests « transactions », Engine Contracts §9). |
| **TD26** | **`TransactionManager.begin(tenant, isolation)` est le point unique** qui pose `app.organization_id` (local à la transaction), l'`as_of`, le niveau d'isolation et les délais (§4.4). Aucun accès à la base hors d'une unité de travail. Un handler d'événement ouvre la sienne **avec l'organisation de l'événement**. | Aucune requête ne s'exécute sans organisation ; RLS échoue fermé sinon (TD17). |
| **TD27** | **L'échelle de verrous est dérivée, pas décrétée.** Chaque opération qui acquiert des verrous est enregistrée dans le **Lock Registry** avec sa suite d'acquisitions ; le générateur construit le graphe de précédence, **échoue s'il contient un cycle**, et publie l'échelle. La chaîne gelée EC5 est une **contrainte d'entrée** : elle doit rester compatible. Le `LockManager` charge l'échelle **générée** (jamais écrite à la main) et refuse toute acquisition descendante en test et en CI ; en production il journalise. **Une opération qui acquiert un verrou doit être enregistrée ; toute acquisition demandée par une opération non enregistrée est une violation d'architecture** : le `LockManager` exige un nom d'opération et refuse un nom inconnu (`LOCK_ORDER_VIOLATION`). Modes : `FOR NO KEY UPDATE` par défaut ; `FOR SHARE` pour protéger un parent lu ; un `INSERT` compte comme une acquisition (clé unique, clé étrangère). | Un ordre écrit à la main n'est pas prouvé : le premier jet de cette décision était **incohérent** avec les opérations elles-mêmes (§4.7). La dérivation transforme une convention en propriété vérifiée. |
| **TD28** | **Choisir le mécanisme le plus faible qui suffit** (tableau §4.2). | Un verrou plus fort que nécessaire bloque, un plus faible laisse un défaut de concurrence. |
| **TD29** | **Sérialisation par sujet pour les projections** : `pg_advisory_xact_lock(moteur, organisation, sujet)` est la **première instruction** de la transaction, **avant toute lecture**, puis lecture en `REPEATABLE READ`. | Voir l'argument §4.3. |
| **TD30** | **Nouvelle tentative bornée** sur `40001` et `40P01` : au plus 3 essais, avec délai aléatoire croissant, **uniquement** pour une unité de travail sans effet externe déjà produit. Épuisé : `SERIALIZATION_FAILURE` (retryable). | Un interblocage est légitime sur des verrous croisés ; il ne doit pas fuiter à l'utilisateur. |
| **TD31** | **Réclamer → revalider → autoriser → agir → enregistrer. Le claim n'est jamais une autorisation.** Pour tout effet externe ou effet dans un autre module : (1) transaction courte de **claim** : transition gardée (`SCHEDULED → EXECUTING`, `PENDING/WAITING → RUNNING`) ; (2) dans la **même** transaction, **revalidation complète** (X3 : Rule Engine, contexte D, dont la **revérification des `OverrideGrant`**, Collection V1.2 G4) ; si elle échoue, la transition devient `SUPPRESSED`, `PAUSED` ou `CANCELLED` selon l'issue, **jamais** `EXECUTING` ; (3) **COMMIT** ; (4) l'**effet** : envoi hors transaction (X13) avec clé d'idempotence fournisseur `notification_id:attempt_no`, ou cas d'usage d'un autre module dans **sa** transaction (idempotent : `dedup_key`, `trigger_key`) ; (5) transaction de **résultat**, idempotente. Un travailleur qui tombe après le claim laisse le statut (`EXECUTING`, `RUNNING`) qui sert de **bail** : le `Reaper` le reprend ; livraison **au moins une fois**, doublon possible connu. *Cela vaut aussi pour l'étape d'automatisation : elle ne crée pas d'action dans la transaction qui verrouille l'exécution (§4.7).* | Une transaction longue autour d'un fournisseur verrouille des lignes pendant un appel réseau ; un envoi sans claim double les messages ; un claim sans revalidation autoriserait un envoi que le monde a rendu inapproprié entre-temps (litige, promesse, rapprochement, grant révoqué). |
| **TD32** | **Idempotence des commandes API en une transaction** : la clé est insérée au début de la transaction du cas d'usage (`UNIQUE (organisation, clé, route)`) ; effet et complétion sont **validés ensemble**. Un doublon concurrent **attend** la première transaction, puis relit le résultat stocké. Contenu différent : `IDEMPOTENCY_KEY_REUSED`. Le statut `IN_PROGRESS` du contrat ne sert que pour un cas d'usage **multi-transactions** (import). | Pas de fenêtre « effet écrit, clé absente » ; pas de nouveau code d'erreur. |

### 4.2 Choix du mécanisme

| Situation | Mécanisme | Exemple |
|---|---|---|
| Modifier un agrégat que d'autres peuvent modifier en même temps | verrou de ligne `FOR UPDATE`, dans l'ordre de l'échelle | `AllocatePayment` : paiement, puis factures par identifiant |
| Modification par l'utilisateur d'un objet qu'il a lu | **concurrence optimiste** : `version` comparée ; sinon `CONCURRENT_MODIFICATION` | modification d'une facture `DRAFT` |
| Transition temporelle ou de reprise sans lecture préalable | **`UPDATE … WHERE état = ancien`** ; le nombre de lignes dit qui a gagné | `INVOICE_OVERDUE`, expirations |
| Réclamer du travail parmi N travailleurs | **`FOR UPDATE SKIP LOCKED`** sur l'index de file | `ExecutionWorker`, `ExecuteDueActions` |
| Sérialiser une ressource qui n'est pas une ligne | verrou consultatif **de transaction** | travail `(travail, organisation)` ; sujet d'une projection (TD29) |
| Empêcher un doublon logique | contrainte d'unicité (`dedup_key`, `trigger_key`) | actions, exécutions, notifications |

### 4.3 Pourquoi le verrou consultatif est la première instruction (TD29)

En `REPEATABLE READ`, l'instantané est pris **au début de la première instruction**, y compris un appel de verrou. Deux calculs A et B du même sujet : celui qui obtient le verrou l'a **demandé en premier** (file d'attente), donc son instantané est **antérieur ou égal** à celui de l'autre ; le second attend, puis écrit avec un instantané **plus récent**. Les écritures de projection suivent donc l'ordre des instantanés : un calcul ancien ne peut pas écraser un calcul récent. Si le verrou était pris **après** une lecture, l'inverse serait possible. Ceci ne suppose aucun ordre d'événements (TD36).

**Vérifié sur PostgreSQL 16.2 (PG-05).** L'instantané est bien pris à la **demande** du verrou : après l'attente, la transaction `REPEATABLE READ` ne voit **pas** ce que le détenteur précédent a validé entre-temps (en `READ COMMITTED`, elle le voit). **Conséquence à ne pas oublier** : ce motif convient aux projections, parce que la sortie du détenteur précédent n'est pas une entrée du suivant et que toute source validée pendant l'attente déclenche une nouvelle demande de recalcul ; il **ne convient pas** à un calcul qui doit voir le résultat du détenteur précédent : celui-là utilise `READ COMMITTED`.

### 4.4 Délais initiaux (à confirmer au banc, §12)

| Rôle / contexte | `statement_timeout` | `lock_timeout` | `idle_in_transaction_session_timeout` |
|---|---|---|---|
| API (`verqia_app`, requête utilisateur) | 5 s | 2 s | 15 s |
| Travailleur d'événements, d'exécution | 30 s | 5 s | 30 s |
| Travaux par lots, projections, import | 5 min | 5 s | 60 s |
| Migrations (`verqia_owner`) | 0 (aucun) | 3 s | 60 s |

Ce sont des **hypothèses de départ**, pas des seuils : elles bornent l'impact d'une transaction bloquée.

### 4.5 Cas difficiles

| # | Situation | Déroulement | Issue garantie |
|---|---|---|---|
| **H1** | Deux allocations simultanées du **même paiement** vers deux factures | toutes deux verrouillent le paiement d'abord : la seconde attend, relit `allocated_minor`, et échoue `ALLOCATION_EXCEEDS_PAYMENT_AVAILABLE` si le total dépasse | T1 jamais violée ; au plus un succès si le solde ne suffit pas |
| **H2** | Deux paiements simultanés vers la **même facture** | paiements distincts ; verrou de la facture ensuite : la seconde relit `outstanding` | T2 jamais violée |
| **H3** | Paiement P1 → (I1, I2) et P2 → (I2, I1) | les factures sont verrouillées par identifiant croissant dans les deux | aucun interblocage |
| **H4** | Deux travailleurs, la même action `SCHEDULED` | `UPDATE … WHERE status = 'SCHEDULED'` : un seul obtient une ligne | un seul envoi tenté |
| **H5** | `Reaper` pendant qu'un travailleur envoie encore | le travailleur écrit son résultat ; le `Reaper` a marqué une tentative transitoire | au plus un doublon d'envoi, documenté (TD31) |
| **H6** | Deux handlers, le même événement | reçu `(event_id, handler_name)` : le second reçoit `REPLAY` (clé primaire) | un seul effet |
| **H7** | Paiement créé puis alloué tout de suite | la barrière de rapprochement est **paresseuse** (RN6) : les handlers relisent la source ; aucune suspension | aucune fausse suspension |
| **H8** | Deux recalculs de priorité du même sujet | verrou de sujet en première instruction (TD29) | le plus récent écrit en dernier |
| **H9** | Deux promotions de run Cashflow | promotion monotone : `(as_of, computed_at)` strictement supérieur, désactivation de l'ancien dans la même transaction | un seul `is_current` par `(organisation, horizon, scénario)` |
| **H10** | Un grant d'override est révoqué entre la création et l'envoi | la revalidation (X3, V1.2 G4) a lieu dans la transaction du claim | pas d'envoi non autorisé |

### 4.6 Contre-exemples

| # | Scénario | Ce qui casse | Décision |
|---|---|---|---|
| **CX15** | `AllocatePayment` verrouille les factures avant le paiement | interblocage avec une allocation croisée | TD27 |
| **CX16** | Un envoi d'e-mail à l'intérieur de la transaction de l'action | 300 ms de verrou par message ; en cas d'annulation, e-mail parti sans action | TD31 |
| **CX17** | Le `Reaper` remet `SCHEDULED` une action `EXECUTING` sans la revalider | envoi après qu'un litige s'est ouvert | TD31, X3 |
| **CX18** | Verrou de sujet pris **après** la lecture des faits | un calcul plus ancien écrase un plus récent | TD29 |
| **CX19** | Le rang de `approvals` n'est pas défini ; deux transactions le prennent dans deux ordres | interblocage rare, jamais reproduit en test | TD27 |
| **CX20** | La clé d'idempotence est validée dans une transaction distincte de l'effet | effet écrit, clé absente : le rejeu double l'effet | TD32 |
| **CX38** | L'étape d'automatisation verrouille l'exécution puis crée l'action dans la même transaction ; une autre transaction verrouille l'action puis l'exécution | interblocage rare ; ordre EC5 violé sans que personne le voie | TD27, TD31 |
| **CX40** | Le claim d'une action `SCHEDULED` la passe `EXECUTING` sans revalidation : « elle a été planifiée, donc autorisée » | envoi après l'ouverture d'un litige ou l'arrivée d'un paiement non affecté | TD31, TI19 |

### 4.7 Échelle des verrous : dérivation

Source : `ARCHITECTURE_REGISTRY_V1.md` §4 (généré) : 19 ressources, 46 opérations enregistrées. Échelle publiée :

```text
advisory → idempotency_keys → organizations → identity_members → subscriptions → import_batches → customers
→ payments → invoices → invoice_disputes → promises → collection_holds → automations → collection_actions
→ automation_executions → approvals → notifications → projections → event_receipts
```

**Le générateur a démontré trois choses.**

1. **Le premier jet de TD27 était faux.** Il plaçait `customers` avant `import_batches` (or `NormalizeImportBatch` verrouille le lot d'abord) et `approvals` avant `collection_actions` (or `CreateCollectionAction` crée l'action puis l'approbation). Avec ces rangs, les opérations enregistrées formaient un **cycle**.
2. **La chaîne gelée EC5 est compatible** avec toutes les opérations enregistrées, **à une condition** : l'étape d'automatisation ne doit pas être **une** transaction qui verrouille l'exécution puis crée l'action, car c'est l'ordre **inverse** d'EC5 (`collection_actions → automation_executions`). L'étape est donc **trois** transactions (réclamer, effet dans le module propriétaire, enregistrer), ce que TD31 impose déjà. **Aucun amendement d'EC5**, mais une phrase d'Automation §6.1 est amendée (§13.1-L).
3. **Des verrous cachés existent** : une clé étrangère prend `FOR KEY SHARE` sur la ligne référencée ; il conflit avec `FOR UPDATE` mais pas avec `FOR NO KEY UPDATE`. D'où le mode par défaut. **Vérifié sur PostgreSQL 16.2 (PG-01, PG-02)** : seul `FOR UPDATE` bloque l'insertion d'un enfant ; `FOR NO KEY UPDATE`, `FOR SHARE` et `FOR KEY SHARE` ne la bloquent pas ; et une modification de `status` ou de `dedup_key` (colonnes d'un index unique **partiel**) ne bloque **pas** non plus : un changement d'état n'entre donc pas en conflit avec les insertions qui référencent la ligne. À rejouer sur la version cible (TA-12).

**Ce que l'échelle ne prouve pas.** Elle est cohérente avec les opérations **enregistrées**, pas avec celles qu'on n'a pas encore imaginées : d'où la règle : une opération qui acquiert un verrou **doit** être enregistrée, et le `LockManager` refuse tout nom inconnu, en test comme en production.

---

## 5. TA5 — Bus d'événements et outbox

### 5.1 Vue d'ensemble

```text
Cas d'usage (transaction)
   ├── modification de l'agrégat
   └── ligne dans `events`            ← même transaction (EC-01)
                COMMIT
                  │  → l'événement est PUBLIABLE (le relais sonde l'outbox chaque seconde : TD34)
                  ▼
   Relais ── réclame par BAIL (available_at) ──► pour chaque handler abonné sans reçu :
      │        transaction du handler (organisation de l'événement)
      │          ├─ succès             → reçu PROCESSED / SKIPPED   (effet + reçu ensemble)
      │          ├─ échec transitoire  → reçu RETRYING (attempts, available_at, last_error)
      │          └─ échec permanent    → reçu DEAD
      └── chaque handler a pris en charge l'événement (reçu quel qu'il soit) → published_at posé

   Boucle de reprise ── réclame les reçus RETRYING échus ──► relance CE handler seul
                                                             → PROCESSED / RETRYING suivant / DEAD
```

**Publier n'est pas traiter.** La publication ne dépend jamais de la réussite d'un handler ; chaque handler a son propre état `(event_id, handler_name)`.

### 5.2 Décisions

| # | Décision | Justification |
|---|---|---|
| **TD33** | **Publier n'est pas traiter.** Un événement est **publiable** dès le `COMMIT`. Le relais le **réclame par bail** (transaction courte : `available_at = as_of + durée du bail`, `publish_attempts + 1`, sous `SKIP LOCKED`), puis exécute chaque handler abonné **dans sa propre transaction**, hors de la transaction de réclamation. Chaque handler a **son propre état de traitement** `(event_id, handler_name)` : reçu terminal (`PROCESSED`, `SKIPPED`), `RETRYING` (nouvelle tentative planifiée) ou `DEAD`. `published_at` est posé quand **chaque handler abonné a pris en charge l'événement** (reçu quel qu'il soit) : il ne dépend **jamais de la réussite** d'un handler. Un relais qui tombe laisse un bail qui expire ; les handlers déjà servis répondent `REPLAY`. **Deux calendriers, deux colonnes, jamais réutilisées l'une pour l'autre** : `events.available_at` est la disponibilité du **message** d'outbox (bail, regroupement) ; `event_receipts.available_at` est la prochaine tentative de **ce handler précis**. | Aucun verrou de ligne tenu pendant les handlers, aucun état hors de PostgreSQL ; le bus ne devient pas un mécanisme de coordination : un handler lent ou en échec n'empêche ni la publication ni les autres. |
| **TD34** | **Pas d'indice de réveil en V1** : le relais **sonde** l'outbox chaque seconde. Aucun effet métier ne dépend d'un `on_commit`. *Extension différée* : un indice Redis publié après `COMMIT` (perdu sans conséquence) si le banc montre une latence de l'outbox hors objectif (S5). | Un sondage d'une seconde est simple et suffit tant que la mesure n'a pas montré le contraire (S4). |
| **TD35** | **Nouvelle tentative par handler, portée par son reçu.** Sur échec transitoire, le handler écrit (ou met à jour) **son** reçu `RETRYING` : `attempts`, `available_at = as_of + délai` (10 s, 1 min, 5 min, 30 min, 2 h), `last_error`. Une **boucle de reprise** de la voie `relay` réclame les reçus `RETRYING` échus (bail sur `available_at`, `SKIP LOCKED`) et relance **ce handler seul**. Tentatives épuisées ou échec permanent : reçu `DEAD` et alerte ; seul `ReplayDeadEvent` (rôle `ADMIN`, audité) le repasse à `RETRYING`. | Sans état par handler, le calendrier de retry de l'EC2 n'a **nulle part où vivre** (§13.1-B) ; le porter par le reçu rend l'indépendance des handlers **structurelle** et donne enfin un sens aux colonnes `attempts` et `last_error` du contrat. |
| **TD36** | **L'ordre n'est jamais une condition de correction.** Le relais travaille par `available_at` croissant, sans garantie d'ordre par agrégat ; chaque handler relit la source (X1) et compare `aggregate_version` (EC-02). Un événement obsolète est `SKIPPED`. | Des relais parallèles peuvent inverser deux événements du même agrégat ; le contrat l'a déjà prévu. |
| **TD37** | **Deux réserves d'exécution par catégorie, dans un même processus** : `fanout` (`MUTATION`, `TRANSITION`, `RESULT` : réactions légères, diffusion à tous les abonnés) et `requests` (`REQUEST` : calculs de projection, un seul destinataire). Chaque handler déclare sa voie. *Extension différée* : les exécuter dans deux processus si le banc le justifie. | Un calcul de trésorerie de plusieurs secondes ne doit jamais occuper les emplacements qui servent une suspension d'action après un litige. |
| **TD38** | **Regroupement des `REQUEST`** : un événement `REQUEST` reçoit `available_at = occurred_at + fenêtre de regroupement` (2 s, valeur initiale) ; à la réclamation, le relais réclame **tous** les `REQUEST` de même `(type, organisation, cible)` déjà disponibles et exécute **un** calcul ; chaque événement reçoit son reçu (le premier `PROCESSED`, les autres `SKIPPED`). | Un import qui touche 5 000 factures d'un client ne déclenche pas 5 000 recalculs. |
| **TD39** | **Équité et contre-pression.** Le relais limite la part d'une organisation dans un lot de réclamation ; profondeur de file, âge du plus ancien événement et taux de `DEAD` sont des métriques d'alerte ; au-delà de `causation_depth` 20, rejet et alerte (X7). | Une organisation en import massif ne doit pas affamer les autres. |
| **TD40** | **Registre des schémas et tests pilotés par les consommateurs** (EC6, §9 Engine Contracts) : un fichier de schéma par type d'événement ; le consommateur déclare les champs qu'il lit. | Une évolution additive passe ; un retrait échoue en CI. |

### 5.3 Ce que le relais ne fait jamais

Il n'exécute **aucune** règle métier ; il ne lit **aucune** donnée métier (sa politique RLS est limitée à `events`) ; il ne modifie **aucun** agrégat ; il n'appelle **aucun** fournisseur externe.

### 5.4 Contre-exemples

| # | Scénario | Ce qui casse | Décision |
|---|---|---|---|
| **CX21** | Les tentatives de retry vivent dans une file Redis ; Redis est vidé | les événements en attente d'un retry disparaissent sans reçu `DEAD` : effet perdu, aucune alerte | TD33, TD35 |
| **CX22** | Le relais tient un verrou de ligne pendant l'exécution des handlers (jusqu'à 2 h de retry) | table d'outbox bloquée ; transactions d'émission en attente | TD33 |
| **CX23** | Deux relais traitent les événements v5 et v6 d'une même facture ; v6 finit avant v5 | l'état est écrasé par un effet ancien | TD36 |
| **CX24** | Un calcul de trésorerie de 8 s est exécuté par le relais qui diffuse `INVOICE_DISPUTED` | l'action reste envoyable pendant 8 s après l'ouverture du litige | TD37 |
| **CX25** | Un import de 100 000 factures inonde l'outbox | les événements des autres organisations attendent | TD38, TD39 |
| **CX26** | Un handler échoue pendant deux heures de retry et l'événement reste « non publié » | l'arriéré de l'outbox est faussé (alertes de retard permanentes), les autres consommateurs sont soupçonnés, et l'on est tenté de coordonner les handlers entre eux | TD33, TD35 |

---

## 6. TA6 — Travailleurs et planificateur

### 6.1 Trois rôles, jamais confondus (TD41)

| Rôle | Question à laquelle il répond | Ne fait **jamais** |
|---|---|---|
| **Planificateur** | « quels travaux sont dus maintenant, pour quelles organisations ? » (temps, fuseaux, cadences) | exécuter un travail, contenir une règle |
| **Coureur** (travailleur) | « exécuter ce travail avec des délais, des reprises, de l'équité » | décider quoi faire pour le métier |
| **Moteur métier** | « que faut-il faire ? » : cas d'usage du module propriétaire | connaître l'heure d'exécution, un ordonnanceur ou une file |

**TD41.** Le planificateur calcule des **échéances** (fonction pure de l'horloge injectée, des fuseaux et des calendriers) ; le coureur les exécute ; le moteur décide. Le calcul d'échéance est testé sans base ni processus.

### 6.2 Décisions

| # | Décision | Justification |
|---|---|---|
| **TD42** | **PostgreSQL est la source de vérité des travaux métier** : états, échéances (`resume_at`, `scheduled_for`, `available_at`), outbox. Les « files » ne sont que des **vues** de ces tables, réclamées par `SKIP LOCKED`. **Aucun courtier n'est la source de vérité d'un délai.** Redis peut **accélérer** (réveil), il ne **décide** jamais (TD48). | Un courtier a ses propres délais de visibilité et sa propre perte ; deux sources de vérité pour un même instant se contredisent. Le contrat impose déjà PostgreSQL pour les exécutions, les actions et l'outbox. |
| **TD43** | **Deux classes de travaux.** **Continus** : boucles de sondage qui réclament du travail (`OutboxPublisher`, `ExecutionWorker`, `ExecuteDueActions`, `ImportReleaser`, `EnrollmentRunner`, envoi). **Périodiques** : balayages **à niveau** (« qu'est-ce qui est dû ? ») déclenchés par des **ticks** jetables. | Un tick perdu retarde le prochain balayage, il ne perd rien : la vérité est l'échéance dans les tables. |
| **TD44** | **Le planificateur est une boucle intégrée à chaque `worker`, sans chef** ; l'exécution unique par `(travail, organisation, période)` est garantie par un **verrou consultatif de transaction**. Aucun composant distinct, aucune dépendance à Redis. | Aucun point de défaillance unique ; rien à déployer de plus (S4). |
| **TD45** | **Un travail périodique traite les organisations une par une**, avec un budget de temps par organisation ; l'échec d'une organisation n'arrête pas les autres ; l'ordre de passage est **tournant** pour l'équité. | Contrat commun EC-03. |
| **TD46** | **`jobs` compose, ne décide pas.** Un travail est une suite de cas d'usage **publiés** ; il n'importe que des `contracts`. Un travail qui touche deux modules est **deux cas d'usage**, dans deux transactions. | `ReconciliationWindowScan` envoie des notifications (`collection`) **et** reprend des exécutions (`automation`) : `collection` ne peut pas appeler `automation` (DR4). |
| **TD47** | **Arrêt propre** : SIGTERM arrête la réclamation, laisse finir l'unité de travail en cours (délai borné) ; ce qui reste est repris à l'expiration du bail. | Un déploiement ne perd ni ne double aucun travail. |

### 6.3 Travaux : classe, propriétaire, voie

| Travail (EC-03) | Classe | Module(s) propriétaire(s) | Voie | Garde d'exécution unique |
|---|---|---|---|---|
| `OutboxPublisher` | continu | `events` | `relay` | bail (`available_at`), `SKIP LOCKED` |
| `InvoiceLifecycleScan` | périodique, 15 min, par organisation dont la date locale change | `invoices` | `batch` | verrou consultatif ; `UPDATE … WHERE état = ancien` |
| `PromiseBreachScan` | périodique, horaire | `promises` | `batch` | idem |
| `HoldExpiryScan` | périodique, 5 min | `collection` | `rt` | idem |
| `ApprovalExpiryScan` | périodique, 5 min | `approvals` | `rt` | idem |
| `TimeTriggerScanner` | périodique, 15 min | `automation` | `batch` | `trigger_key` unique |
| `ExecutionWorker` | continu, sondage 30 s | `automation` | `rt` | `SKIP LOCKED` sur `(status, resume_at)` |
| `ExecuteDueActions` | continu, sondage 1 min | `collection` | `rt` | claim gardé (TD31) |
| `Reaper` | périodique, 5 min | `automation` (exécutions) **et** `collection` (actions) | `rt` | transition gardée |
| `ImportReleaser` | continu, **composé par `jobs`** : `automation.ReleaseImportTranche` puis `imports.CompleteImportRelease` (chacun dans sa transaction, TD58) | `automation` et `imports` | `batch` | `trigger_key` d'import |
| `EnrollmentRunner` | continu | `automation` | `batch` | `trigger_key` d'inscription |
| `ProjectionDailyRefresh` | périodique, 05:00 local | `risk`, `priority` (émettent des `REQUEST` regroupés) | `batch` | verrou consultatif ; `input_hash` |
| `ProjectionSafetyNet` | périodique, 2 h | `risk`, `priority` | `batch` | idem |
| `ReconciliationWindowScan` | périodique, horaire | `collection` (revues, alertes) **puis** `automation` (reprises) | `rt` | verrou consultatif ; notifications dédupliquées |
| `CashflowScheduler` | périodique, quotidien par organisation | `cashflow` (émet des `REQUEST`) | `batch` | `input_hash` |
| `PartitionManager` | périodique, quotidien | `platform` | `batch` | `IF NOT EXISTS` |
| `TechnicalPurge` | périodique, quotidien | `platform` | `batch` | suppression bornée par date |

`ProjectionDailyRefresh`, `ProjectionSafetyNet` et `CashflowScheduler` **n'écrivent pas eux-mêmes** les projections : ils émettent des `REQUEST` regroupés qui passent par la **même** file et le **même** verrou de sujet que les recalculs déclenchés par événement (TD29). Il n'existe donc qu'un seul chemin d'écriture par projection. Le contrat d'EC-03 (recalcul de toutes les projections, `input_hash`) est respecté ; seul le mécanisme est précisé.

L'envoi de messages (`NotificationSender`, EC-04) est un **travail continu** de la voie `send`, hors de la liste EC-03.

### 6.4 Processus et voies

**V1 : deux types de processus.** `web` (API, authentification, idempotence) et `worker`. Le `worker` est composé de **voies**, activables par option de démarrage :

| Voie | Contenu | Séparation différée si… |
|---|---|---|
| `relay` | outbox et handlers (réserves `fanout` et `requests`, TD37) | le banc montre un retard de diffusion hors objectif pendant un calcul long |
| `rt` | `ExecutionWorker`, `ExecuteDueActions`, `Reaper`, expirations, `ReconciliationWindowScan` | la latence d'exécution d'étape ou d'action sort de l'objectif quand `batch` est chargée |
| `send` | envoi de notifications | des appels de fournisseur lents pèsent sur les autres voies |
| `batch` | balayages périodiques, imports, libérations, inscriptions, requêtes de projection quotidiennes | — (elle tolère le retard) |

Le **même code** est déployé ; en V1 chaque `worker` porte toutes les voies. Séparer une voie est une **option de démarrage**, pas une modification de code (S5). Le planificateur (TD44) est une boucle de chaque `worker`.

### 6.5 Contre-exemples

| # | Scénario | Ce qui casse | Décision |
|---|---|---|---|
| **CX27** | Les `resume_at` des exécutions sont dupliqués dans des tâches différées d'un courtier ; le courtier est vidé | des exécutions ne reprennent jamais | TD42 |
| **CX28** | Le planificateur unique tombe pendant la nuit | aucun balayage ; fenêtres de rapprochement jamais levées | TD44 |
| **CX29** | `ReconciliationWindowScan` appelle directement `automation` depuis `collection` | violation de DR4 | TD46 |
| **CX30** | Un déploiement tue les travailleurs en plein envoi | doublons d'envoi ou actions bloquées `EXECUTING` | TD47, TD31 |
| **CX31** | Le rafraîchissement quotidien recalcule directement les projections pendant qu'un événement recalcule le même sujet | deux écrivains concurrents de la même projection | §6.3, TD29 |

---

## 7. TA7 — Redis

### 7.1 Décisions

| # | Décision |
|---|---|
| **TD48** | **Règle absolue : vider Redis à tout instant ne perd aucune donnée, ne double aucun effet métier et n'altère aucune décision ; seul un compteur de limitation peut en souffrir. Redis accélère ; il ne décide jamais.** |
| **TD49** | **Redis n'a que deux usages en V1** : (1) limitation de débit de l'API (`RATE_LIMITED`) ; (2) étranglement de l'envoi vers un fournisseur (`send_rate_per_hour`, jeton) : un vidage laisse dépasser brièvement, le fournisseur répond « limité », l'erreur est transitoire (TD31). **Différés** (S5) : indices de réveil (TD34), ticks du planificateur (TD44), cache de lecture d'affichage ; chacun a pour déclencheur une mesure de latence au banc. |
| **TD50** | **Ce que Redis ne porte jamais** : un fait métier, un état, un reçu, une clé d'idempotence, une clé de déduplication, un verrou dont dépend la **correction** (un verrou Redis n'a pas de jeton d'exclusion : après un délai, deux détenteurs coexistent), un `resume_at`, un compteur `reminders_30d` ou `max_customer_messages_per_day` (règles métier calculées depuis PostgreSQL). |

Les clés Redis sont préfixées `verqia:{environnement}:` et, quand elles sont propres à une organisation, portent son identifiant. Aucune persistance n'est exigée (ni AOF ni instantané) : c'est ce qui rend TD48 **vérifiable** en environnement de test.

### 7.2 Contre-exemples

| # | Scénario | Ce qui casse | Décision |
|---|---|---|---|
| **CX32** | `max_customer_messages_per_day` est un compteur Redis ; Redis redémarre | un client reçoit 5 messages au lieu de 2 : garde-fou anti-harcèlement levé | TD50 |
| **CX33** | Un verrou Redis protège l'allocation d'un paiement ; le processus est suspendu au-delà du délai | deux détenteurs coexistent ; seule la base (T1, T2) arrête la faute, **au COMMIT** : on ne peut pas faire dépendre la correction d'un verrou qui peut mentir | TD50, TD28 |
| **CX34** | Un cache d'affichage (différé en V1) met en cache `outstanding_minor` et une décision de relance le lit | relance sur un solde périmé (X1) | TD3 |

---

## 8. TA8 — Ports et adaptateurs

### 8.1 Décisions

| # | Décision |
|---|---|
| **TD51** | **Un port par frontière technique ; un adaptateur de production et un **double en mémoire** pour chaque port** (utilisé par les tests du Domain et de l'Application). Un port sans double est refusé en CI. Un port utilisé par plusieurs modules est déclaré dans `kernel` ; un port propre à un module, dans ses `contracts`. |
| **TD52** | **Un adaptateur n'a aucune règle métier** (DR8). Le fournisseur d'envoi est enveloppé d'une garde qui **échoue** si une transaction est ouverte (X13), active en test et en production. |

### 8.2 Catalogue des ports

`WakeSignal` et `ReadCache` sont **différés** avec les mécanismes Redis correspondants (§0.3).

| Port | Déclaré dans | Rôle | Adaptateur de production | Double |
|---|---|---|---|---|
| `Clock` | `kernel` | `as_of` de l'unité de travail (TD23) | horloge de la base | horloge virtuelle |
| `IdGenerator` | `kernel` | UUIDv7 | générateur applicatif | générateur seedé |
| `TransactionManager` | `kernel` | unité de travail, isolation, organisation, `on_commit` (indices seulement) | Django / psycopg | mémoire |
| `LockManager` | `kernel` | verrous de lignes ordonnés, verrous consultatifs de transaction (TD27, TD29) | PostgreSQL | mémoire avec échelle vérifiée |
| `TenantContext` | `kernel` | organisation courante, refus si absente | contexte de transaction | mémoire |
| `EventOutbox` | `kernel` (types dans chaque `contracts`) | émettre dans la transaction (EC-01) | table `events` | liste en mémoire |
| `AuditWriter` | `kernel` | écrire l'audit dans la transaction | table `audit_logs` | liste en mémoire |
| `IdempotencyStore` | `kernel` | clés de commandes (TD32) | table `idempotency_keys` | mémoire |
| `Repositories` | chaque module | agrégats | Django ORM | mémoire |
| `FactProvider` (par famille) | `rules.contracts` | faits du Rule Engine (TD12) | implémenté par chaque propriétaire | faits fournis par le test |
| `NotificationSender` | `notifications.contracts` | envoi externe (EC-04) | fournisseur d'e-mail | fournisseur simulé (acceptations, erreurs, réponses perdues) |
| `RateLimiter` | `kernel` | limitation API et envoi (TD49) | Redis | compteur en mémoire |
| `JobRunner` | `jobs` | exécuter un travail (§6) | processus travailleur | exécution synchrone |
| `Metrics`, `Tracer`, `Logger` | `kernel` | observabilité sans donnée personnelle | outil retenu (§13.3) | collecteur en mémoire |

### 8.3 Contre-exemples

| # | Scénario | Ce qui casse | Décision |
|---|---|---|---|
| **CX35** | Un adaptateur de fournisseur décide « ne pas renvoyer si envoyé dans l'heure » | une règle métier cachée hors du Rule Engine | TD52, DR8 |
| **CX36** | Le port `NotificationSender` n'a pas de double ; les tests appellent un vrai fournisseur | tests non déterministes ; envois réels | TD51 |

---

## 9. TA9 — Déploiement

### 9.1 Topologie conceptuelle

```text
                     Navigateur (Next.js)
                            │ HTTPS
                       ┌────▼────┐
                       │   web   │  Django / DRF
                       └────┬────┘
        ┌───────────────────┼────────────────────┐
        ▼                   ▼                    ▼
  PostgreSQL primaire   Redis (jetable :     worker  (voies : relay · rt · send · batch)
   ▲    ▲                limitation seule)     │  planificateur = boucle du worker
   │    └── RLS, rôles ─────────────────────────┘
   └── WAL en continu → archivage (restauration à un instant)
```

Cette représentation est **conceptuelle** : l'hébergeur, l'orchestrateur et les réseaux ne sont pas choisis ici (§13.3).

### 9.2 Décisions

| # | Décision |
|---|---|
| **TD53** | **Déploiement.** (1) **Une image**, deux points d'entrée (`web`, `worker`) (§6.4) ; configuration par variables d'environnement ; secrets hors de l'image. (2) **Publication** en trois temps : migrations *expand* sous `verqia_owner` ; déploiement progressif des processus ; migrations *contract* dans une publication ultérieure (TD20). (3) **Retour arrière** = re-déployer l'image précédente (le schéma *expand* est compatible) ; jamais de retour arrière de données ; sinistre : restauration à un instant. (4) **Un seul primaire** PostgreSQL, **sans réplica de lecture en V1** (différé ; s'il apparaît, il ne servira que des lectures d'affichage, jamais une décision : X1). (5) **Santé** : `web` prêt si la base répond ; travailleur prêt si son battement de cœur est récent. (6) **Journaux** structurés avec `correlation_id` ; l'identifiant d'organisation figure dans les journaux et traces, **pas** dans les étiquettes de métriques (cardinalité) ; aucune donnée personnelle. (7) **Sauvegarde** : archivage continu des journaux de transaction, restauration testée à fréquence fixée (§13.3). |

### 9.3 Restauration : limites connues

- Après une restauration à un instant, des e-mails envoyés **après** cet instant n'ont plus de ligne : une reprise naïve les **renverrait**. Procédure : l'envoi reste **suspendu** après une restauration jusqu'à la réconciliation avec le journal du fournisseur.
- Redis n'est **pas** restauré (TD48).
- Un changement de version de `tzdata` est une publication annoncée (TD24).

### 9.4 Objectifs de service à fixer (§13.3)

Point de reprise (RPO), durée de reprise (RTO), disponibilité de l'API, latence de l'outbox, retard maximal du planificateur : **à fixer au banc et par décision produit**. Le document ne les invente pas.

---

## 10. TA10 — Intégration continue et portes d'architecture

### 10.1 Pipeline

| Étape | Niveaux de la matrice | Contenu | Porte |
|---|---|---|---|
| 1 | L0 | statique, types, **architecture** (§10.2), migrations, artefacts générés à jour, `build_matrix.py --check` et `build_registry.py --check` | à chaque commit |
| 2 | L1 | Domain pur, modèle de référence, cas d'or (aucune base) | à chaque commit |
| 3 | L2 | PostgreSQL réel : contraintes, triggers, RLS, rôles, partitions, catalogue ↔ contrat | à chaque demande de fusion |
| 4 | L3 | cas d'usage intégrés : transactions, outbox, idempotence, concurrence | à chaque demande de fusion |
| 5 | L4 | flux entre moteurs, relais, travailleurs, planificateur | à la fusion |
| 6 | L5 | bout en bout, horloge virtuelle, vérificateurs globaux | quotidien |
| 7 | L6 | propriétés, différentiel, chaos (pannes, Redis vidé, doublons, retards) | quotidien |
| 8 | L7 | performance et volumétrie (banc, §12) | hebdomadaire et avant version |

Les durées cibles des étapes 1 à 4 (retour rapide sur une demande de fusion) sont **à mesurer** ; elles ne sont pas fixées ici.

### 10.2 Règles d'architecture exécutables

| # | Règle | Méthode de vérification |
|---|---|---|
| **AR-01** | `domain` n'importe ni Django, Redis, psycopg, SDK, réseau (I1) | analyse d'imports |
| **AR-02** | aucune lecture d'horloge système hors adaptateur `Clock` (I2) ; **aucun `now()` ni `current_date` dans le SQL de l'application** (TD23) | analyse syntaxique des appels et du texte SQL ; exécution des tests avec l'heure système gelée à une date absurde |
| **AR-03** | un module n'importe que `contracts` des autres, dans les arêtes du §2.3 (I3) | analyse d'imports ; graphe sans cycle |
| **AR-04** | aucune table d'un autre module dans l'ORM ni le SQL (I4) | modèles importables seulement par leur module ; analyse du SQL brut : noms de tables comparés à la propriété du §2.1 |
| **AR-05** | une projection n'est écrite que par son moteur (I5, X5) | dépôts d'écriture privés au module |
| **AR-06** | **Collection ne contourne jamais le Rule Engine** (I6) | chaque cas d'usage de changement de statut est exécuté avec un espion sur `rules.evaluate` : appelé ; analyse : les écritures de statut n'existent que dans `collection.application` |
| **AR-07** | **Automation ne crée jamais directement une action** (I7, X4) | `automation` n'importe pas de dépôt de `collection` ; seul `collection.contracts` |
| **AR-08** | **aucun message externe dans une transaction** (I8, X13) | garde d'exécution sur l'adaptateur d'envoi (échoue si une transaction est ouverte) ; SDK de fournisseur importé seulement par l'adaptateur |
| **AR-09** | Redis n'est jamais une source de vérité (I9) | test « Redis vidé » (TA-30) ; interdiction d'importer le client Redis hors des adaptateurs |
| **AR-10** | pas de signal Django ni d'`on_commit` porteur d'effet (I11) | analyse syntaxique ; liste blanche des indices |
| **AR-11** | SQL brut et verrous seulement dans l'infrastructure et le `LockManager` (I12) | analyse d'imports et d'appels |
| **AR-12** | administration Django en lecture seule (I13) | inspection du registre d'administration |
| **AR-13** | graphe des **migrations** sans cycle et compatible avec l'ordre du §2.4 | analyse des dépendances de migrations |
| **AR-14** | toute contrainte du contrat existe en base, et rien d'autre (O9) | comparaison du catalogue PostgreSQL au contrat |
| **AR-15** | tout type d'événement a un schéma, un producteur, et ses consommateurs déclarés (EC6) | registre généré ; tests pilotés par les consommateurs |
| **AR-16** | l'échelle du `LockManager` est **générée** depuis le Lock Registry, sans cycle, compatible avec la chaîne gelée EC5 ; toute opération qui acquiert des verrous est enregistrée (TD27) | `build_registry.py --check` ; test unitaire de l'échelle ; exécution des cas d'usage de tests avec vérification active |
| **AR-17** | tout port a un double (TD51) | énumération des ports |
| **AR-18** | le rôle d'exécution n'est ni propriétaire, ni `BYPASSRLS` ; RLS active partout (TD17, TD18) | introspection du catalogue |
| **AR-19** | un état métier n'est écrit que par les commandes de son module propriétaire ; les seuls franchissements sont les exceptions C12 nommées (TD55, I5) | Command Registry (« écriture hors propriétaire ») ; analyse d'imports : les dépôts d'écriture ne sont importables que par le module propriétaire |
| **AR-20** | les quatre registres sont cohérents entre eux et avec les documents figés : tables, événements (catalogue, classement des sans-abonné), listes de rafraîchissement, dépendances requises, **trois graphes**, producteurs, destinataires `REQUEST`, **C12 fermé**, **transactions inter-modules** (TD56, TD58) | `build_registry.py --check` ; `test_registry.py` (injection de violations) |

---

## 11. Invariants

| # | Invariant |
|---|---|
| **TI1** | Le Domain ne dépend d'aucun cadre ni d'aucune horloge système. |
| **TI2** | Tout accès à la base a lieu dans une unité de travail qui a posé l'organisation ; sans organisation, **aucune ligne** n'est visible. |
| **TI3** | Le graphe des imports **et** le graphe des migrations sont sans cycle. |
| **TI4** | Toute acquisition de verrous respecte l'échelle **générée** du Lock Registry, compatible avec toutes les opérations enregistrées et avec la chaîne gelée EC5. Une opération qui acquiert un verrou doit être enregistrée ; une acquisition par une opération non enregistrée est une violation d'architecture. |
| **TI5** | Un effet externe n'a jamais lieu dans une transaction ; il est précédé d'une revalidation validée. |
| **TI6** | Toute écriture qui doit produire un événement produit sa ligne d'outbox **dans la même transaction**. |
| **TI7** | **Publier n'est pas traiter.** `published_at` est posé quand chaque handler abonné a **pris en charge** l'événement (reçu terminal, `RETRYING` ou `DEAD`) ; il ne dépend jamais de la réussite d'un handler. L'échec, le retard ou le `DEAD` d'un handler n'affecte ni la publication ni le traitement des autres. |
| **TI8** | Aucun état de vérité n'existe hors de PostgreSQL (Redis vidé : aucune perte, aucun doublon d'effet métier). |
| **TI9** | Une projection n'a qu'un chemin d'écriture, sérialisé par sujet. |
| **TI10** | Aucun handler ne suppose d'ordre entre événements. |
| **TI11** | Le relais ne lit aucune donnée métier ; il ne dispose que de politiques nommées sur `events` et sur les reçus `RETRYING`. |
| **TI12** | Le résultat d'un travail périodique ne dépend jamais de l'heure de son exécution (Collection V1.2, W6). |
| **TI13** | Toute erreur de base atteignant l'API est traduite ; une violation d'invariant qui l'atteint est un défaut. |
| **TI14** | Une commande rejouée avec la même clé produit le même résultat, sans second effet. |
| **TI15** | Après restauration, aucun message n'est renvoyé avant réconciliation. |
| **TI16** | Un port n'existe pas sans double de test. |
| **TI17** | Toute colonne temporelle écrite par l'application provient de `as_of` ; le `DEFAULT now()` de la base n'est jamais utilisé par un flux applicatif. |
| **TI18** | RLS est un filet : aucun code ne s'appuie sur elle pour cibler l'organisation ; la suite métier donne les mêmes résultats avec RLS désactivée. |
| **TI19** | Un claim n'est jamais une autorisation : toute action externe est précédée d'une revalidation complète, dans la transaction du claim. |
| **TI20** | Un état métier n'est écrit que par les cas d'usage de son module propriétaire, par la fonction de transition du Domain (exceptions : C12 nommées). |
| **TI21** | Toute écriture inter-modules hors des exceptions C12 nominatives s'exécute dans la transaction du **module propriétaire**, à la demande de l'appelant (TD58). |
| **TI22** | Tout événement contractuel est au catalogue normatif, classé technique, ou en amendement en attente ; tout événement sans abonné est classé A ou B. |

---

## 12. Tests et banc d'essai

### 12.1 Nouvelle famille `TA` (à insérer dans la matrice après validation)

| Test | Niveau | Contenu | Décisions / invariants |
|---|---|---|---|
| **TA-01** | L0 | règles `AR-01` à `AR-05`, `AR-09` à `AR-13`, `AR-17`, `AR-19`, `AR-20` : analyse d'imports, d'appels et de modèles ; un service de requête ne lit que les tables de son module ; `rules` n'importe aucun module ; `events` n'importe aucun producteur ; l'administration est en lecture seule ; chaque port a un double | TD2, TD4, TD9, TD10, TI1, TI3, TD1, TD3, TD5, TD12, TD13, TD14, TD51, TI16 |
| **TA-02** | L0 | `AR-02` : suite complète avec l'**horloge virtuelle** réglée à une date absurde et l'heure système gelée ; **aucune colonne temporelle écrite ne coïncide avec l'heure réelle** (le `DEFAULT now()` n'est jamais utilisé) ; les cas d'or de fuseau (`R11` à `R14`) passent avec la version de `tzdata` figée dans l'image | TD23, TI1, TI17, TD24 |
| **TA-03** | L1 | `AR-06` et `AR-07` : espion sur `rules.evaluate`, absence d'écriture directe d'action | TD6, I6, I7 |
| **TA-04** | L2 | `AR-14` : catalogue PostgreSQL ↔ contrat ; contraintes nommées ; T14 généré = T14 réel ; noms de tables et de contraintes du contrat, schéma `verqia`, schéma `public` vide | TD16, TD8, TD15 |
| **TA-05** | L2 | `AR-18` et RLS : sans organisation posée, aucune ligne ; rôle non propriétaire ; aucune politique manquante ; **relais** : lecture de `events` seule, autre table refusée | TD17, TD18, TI2, TI11 |
| **TA-06** | L2 | privilèges de chaque rôle : `DELETE`, `TRUNCATE`, `UPDATE` sur LOG refusés à `verqia_app` ; colonnes de `verqia_relay` et `verqia_privacy` | TD18 |
| **TA-07** | L2 | deux organisations : requête sans filtre → uniquement l'organisation courante ; écriture vers une autre organisation refusée par FK composite **et** RLS ; **la suite métier complète, exécutée avec RLS désactivée, donne les mêmes résultats** (RLS est un filet, pas un chemin) ; un gestionnaire d'ORM sans organisation lève `TENANT_CONTEXT_MISSING` avant la base | TD17, TI18 |
| **TA-08** | L2 | traduction d'erreurs : chaque contrainte nommée produit le code attendu, y compris les erreurs levées **au COMMIT** | TD19, TI13 |
| **TA-09** | L2 | migrations : base vide → dernière version ; ordre du §2.4 ; *expand* compatible avec le code N ; index concurrents | TD20, AR-13 |
| **TA-10** | L2 | partitions : élagage ; recherche par identifiant UUIDv7 à la frontière de mois ; partition par défaut vide | TD22 |
| **TA-11** | L3 | `TransactionManager` : organisation posée, délais, `as_of` unique par unité de travail ; `on_commit` ne porte pas d'effet ; aucun verrou de session, `LISTEN/NOTIFY` ni table temporaire ; exécution derrière un pooler en mode transaction | TD23, TD26, TD21 |
| **TA-12** | L3 | échelle de verrous **générée** depuis le registre ; acquisition descendante refusée ; cas `H1` à `H3` ; **exécuté sur PostgreSQL réel** : 10 expériences (`pg_experiments.py`, `test_pg_locks.py`) : modes de verrou et clés étrangères, colonnes d'index partiel, interblocage, instantané après verrou consultatif, `UPDATE` gardé, `INSERT` en attente, `SKIP LOCKED`, RLS (fail-closed, réglage local, clés étrangères) ; **à rejouer sur la version cible** (16.2 embarqué sous Windows ici) | TD27, TD29, TD17, TI4 |
| **TA-13** | L3 | concurrence : `H1` à `H4`, `H6`, `H9` avec deux et dix travailleurs | TD28, TD31 |
| **TA-14** | L3 | verrou de sujet en première instruction : calcul ancien ne peut écraser un calcul récent (`H8`, `CX18`) | TD29, TI9 |
| **TA-15** | L3 | nouvelle tentative sur `40001` / `40P01` : bornée, sans effet externe déjà produit | TD30 |
| **TA-16** | L3 | idempotence d'API : même clé même contenu (rejeu), contenu différent (`IDEMPOTENCY_KEY_REUSED`), concurrence de deux requêtes | TD32, TI14 |
| **TA-17** | L3 | réclamer-valider-agir : panne entre chaque étape de `ExecuteDueAction` ; garde d'envoi dans une transaction ; **un claim sans revalidation validée ne mène jamais à `EXECUTING`** (litige, promesse, hold, rapprochement ou grant révoqué apparus entre la planification et le claim) ; étape d'automatisation en trois transactions | TD31, TD52, TI5, TI19 |
| **TA-18** | L4 | outbox : tout événement produit dans la transaction ; annulation de transaction → aucun événement | TD33, TI6 |
| **TA-19** | L4 | bail du relais : relais tué en plein traitement ; reprise ; handlers déjà servis : `REPLAY` ; **publication indépendante du succès des handlers** ; l'outbox se vide par sondage seul, sans aucun indice de réveil | TD33, TI7, TD34 |
| **TA-20** | L4 | un handler en échec : reçu `RETRYING`, reprise `10 s … 2 h`, puis `DEAD` ; **les autres handlers de l'événement ne sont ni retardés ni rejoués** ; `ReplayDeadEvent` | TD35, TI7 |
| **TA-21** | L4 | désordre : v6 avant v5, doublons, événement retardé : même état final | TD36, TI10 |
| **TA-22** | L4 | réserves : un calcul de trésorerie long n'occupe pas les emplacements de `fanout` ; la suspension après litige reste dans l'objectif | TD37 |
| **TA-23** | L4 | regroupement : 5 000 `REQUEST` d'un client → un calcul, reçus `PROCESSED` et `SKIPPED` | TD38 |
| **TA-24** | L4 | équité : deux organisations, l'une inonde l'outbox ; l'autre garde sa latence | TD39 |
| **TA-25** | L4 | planificateur : deux exemplaires, exécution unique ; arrêt de six heures, rattrapage ; **même résultat à 00:05 et 23:55** ; l'échéance se calcule sans base ni processus (fonction pure) ; un échec d'organisation n'arrête pas les autres | TD44, TI12, TD41, TD43, TD45 |
| **TA-26** | L4 | `ReconciliationWindowScan` en deux cas d'usage (`collection` puis `automation`), deux transactions | TD46 |
| **TA-27** | L4 | arrêt propre : SIGTERM en plein traitement ; aucun travail perdu ni doublé | TD47 |
| **TA-28** | L5 | e-mail : envoi hors transaction, réponse perdue, doublon documenté | TD31 |
| **TA-29** | L5 | restauration à un instant : envois suspendus jusqu'à réconciliation | TI15 |
| **TA-30** | L6 | **Redis vidé** pendant un scénario de plusieurs jours : mêmes états finaux, mêmes vérificateurs globaux ; indices perdus retardent seulement ; seuls la limitation d'API et l'étranglement d'envoi utilisent Redis ; aucune valeur d'un délai ne s'y trouve | TD48, TI8, TD42, TD49, TD50 |
| **TA-31** | L6 | chaos : pannes de processus entre instructions, échecs de sérialisation, partitions absentes | TD25, TD30 |
| **TA-32** | L6 | différentiel : verrous et allocations concurrentes contre une exécution séquentielle | TD28 |
| **TA-33** | L7 | banc (§12.2) | TD53 |
| **TA-34** | L0 | **injection de violation** : pour chaque règle `AR-*`, une violation volontaire dans un module d'essai **fait échouer la porte** ; une règle jamais vue échouer n'est pas prouvée | TD54, AR-01 à AR-20 |
| **TA-35** | L0 | **registres** : `build_registry.py --check` sans erreur ; **36 tests d injection** : cycle de verrous, écriture hors propriétaire, C12 hors liste, appel inter-modules dans la même transaction, travail de composition hors `own:`, événement sans producteur / sans classement / classé C / contractuel non catalogué, destinataire `REQUEST` multiple, dépendance non déclarée, cycle d'appels, cycle de schéma, table sans propriétaire, dérive des listes de rafraîchissement ; `--freeze` tant qu'un nom est provisoire ; tables ↔ modules (22 unités), `approvals` module propriétaire, schémas d'événements (AR-15), fiche complète de chaque module, événements catalogués ou classés | TD55, TD56, TD58, TI20, TD7, TD11, TD40, TD57, TI22 |
| **TA-36** | L4 | **plan de provisioning** : `CreateOrganization` écrit `PROVISIONING` ; chaque étape (`identity`, `billing`, `automation`) est idempotente par `(organisation, étape)` ; panne entre deux étapes puis `ResumeProvisioning` ; une organisation `PROVISIONING` refuse toute commande métier ; `CompleteProvisioning` émet `ORGANIZATION_CREATED` une seule fois ; `organizations` n'importe ni `billing` ni `automation` | TD59, TD58, TI21 |
| **TA-37** | L4 | **composition orchestrée** : action `PROPOSED` → approbation → `PENDING_APPROVAL` avec panne entre chaque temps et reprise par `ResumeProposedActions` ; `ExecuteDueAction` : claim, notification (transaction de `notifications`), envoi, résultat, panne entre chaque temps ; aucune écriture inter-modules dans une même transaction hors exceptions C12 ; expiration d'une approbation par le port `ApprovalTargetReader` | TD58, TD31, TI21 |

### 12.2 Banc d'essai

Les seuils sont **posés après mesure**. Le protocole fixe ce qu'on mesure, pas le résultat attendu.

| Mesure | Scénario |
|---|---|
| latence des cas d'usage financiers (`AllocatePayment`) sous concurrence croissante | 1, 10, 100 allocations simultanées sur des factures partagées |
| retard de l'outbox (âge du plus ancien événement) | flux régulier ; rafale ; import de N factures |
| débit des handlers par réserve | `fanout` et `requests` séparément |
| équité entre organisations | une organisation en rafale, quatre au repos |
| coût de RLS | mêmes requêtes avec et sans politique (mesure d'écart) |
| travaux périodiques | balayage `InvoiceLifecycleScan` sur N factures actives ; `ReconciliationWindowScan` |
| volumétrie | partitions `events` et `audit_logs` sur 24 mois simulés |
| récupération | temps de reprise après arrêt du relais, du planificateur, de Redis |

Les délais du §4.4 et la fenêtre de regroupement (TD38) sont **confirmés ou corrigés** par ce banc.

---

## 13. Décisions à valider, écarts et amendements

### 13.1 Écarts découverts dans les documents figés

| # | Constat | Proposition |
|---|---|---|
| **A** | `approvals` appartient à `automation` (Contrat §8.5, matrice §13) alors que `collection` crée des approbations pour ses actions et que DR4 lui interdit d'appeler `automation` | module `approvals` (TD11) |
| **B** | L'EC2 fixe un calendrier de nouvelles tentatives (10 s … 2 h) **par handler**, mais `event_receipts` n'existe qu'à l'état terminal et `events` n'a aucune colonne d'instant de reprise | `event_receipts.outcome` reçoit `RETRYING` et une colonne `available_at` ; `events.available_at` sert de bail et de fenêtre de regroupement (TD33, TD35, TD38) |
| **C** | `ReconciliationWindowScan` (Collection V1.2) envoie des notifications **et** reprend des exécutions, donc touche `collection` et `automation`, alors que DR4 interdit l'appel de l'un vers l'autre | travail composé de **deux cas d'usage** (TD46) |
| **D** | Les faits `hold_active`, `highest_level_reached`, `reminders_30d` viennent des tables de `collection` ; `rules` ne peut ni les lire (DR2, DR4, cycle) ni être importé par elle sans cycle | inversion : `rules` déclare les fournisseurs de faits, chaque propriétaire les implémente (TD12) |
| **E** | L'échelle de verrous gelée (EC5) ne couvre que six tables ; le premier jet de TD27 était incohérent avec les opérations | échelle **dérivée** du Lock Registry (19 ressources, 46 opérations), compatible avec EC5 (TD27, §4.7) |
| **F** | La liste des modules ne contient ni `identity`, `billing`, `approvals`, ni le socle ; `jobs` y figure comme domaine alors qu'il n'est qu'exécution | TD7 |
| **G** | **Tranché.** Des flux gelés créent un enregistrement d'un autre module dans la transaction de l'appelant (`collection` → `approvals`, `notifications`), hors des exceptions nommées de C12 | **Pas d'extension de C12.** Composition orchestrée (TD58) : chaque module écrit dans sa transaction, à la demande de l'appelant. Amende Collection §4 (étape 7), §6, §8 |
| **H** | **Tranché.** `import_batches.status` (`RELEASING`, `RELEASED`) est modifié par `ImportReleaser`, qui crée aussi des exécutions d'`automation` | Conséquence de TD25 + TD55, pas une exception : `jobs.ImportReleaser` **compose** `imports.StartImportRelease`, `automation.ReleaseImportTranche`, `imports.CompleteImportRelease`, chacun dans sa transaction |
| **I** | **Tranché.** `CreateOrganization` provisionne aussi l'abonnement d'essai (`billing`, S7) et le jeu d'automatisations (`automation`) | **Plan de provisioning** (TD59) : état `PROVISIONING`, port `ProvisioningStep`, une transaction par étape ; `CreateOrganization` sort de C12. Amende Invariants C12, State Machines §1, contrat (`organizations.status`) |
| **J** | **Tranché.** Le contrat déclare `USER_CREATED`, `USER_STATUS_CHANGED`, `MEMBER_ADDED`, `MEMBER_ROLE_CHANGED`, `MEMBER_REMOVED`, absents du catalogue des Invariants §10.3 | les ajouter au catalogue ; **porte** : tout événement contractuel est au catalogue, classé technique, ou en amendement en attente (TI22). Les cinq sont en attente |
| **K** | **Tranché et validé.** Cashflow : aucun émetteur listé ; 33 événements sans abonné | Le registre exige un **classement** : sur 31 événements restés sans abonné, **29 A** (journal, interface, audit) et **2 B** (`CASHFLOW_UPDATED` : alertes de trésorerie hors V1 ; `SUBSCRIPTION_CHANGED` : S7), **0 C**. **Déclencheurs de recalcul du Cashflow (validés)** : 14 événements, portée `ORGANISATION`, horizons 30 et 90 jours, scénario `BASE`, coalescence de 5 minutes (Cashflow §4.8) ; **`ORG_SETTINGS_CHANGED` a un abonné Cashflow, filtré** sur les champs que lit `cash-1.0` ; le rafraîchissement de 05:00 reste le filet. **Constat de la mise en œuvre** : `cash-1.0` ne lit aucun champ d'`org_settings` (il lit le fuseau et la devise de `organizations`, la date des promesses et des délais calculés sur les factures) : l'ensemble filtré est donc **vide** en V1 (`CASHFLOW_ORG_SETTINGS_RELEVANT`), l'abonné écarte chaque événement (`SKIPPED`) et le filtre est la place où `cash-2.0` déclarera ses champs. Un changement de **fuseau** passe par `ORGANIZATION_UPDATED`, non abonné : rattrapé à 05:00 |
| **L** | Automation §6.1 dit « une transaction par étape : effet, ligne d'étape, nouvel état » ; l'effet d'une étape écrit dans un autre module (action, notification, approbation), ce que X8 et C12 n'autorisent pas dans une même transaction | l'étape est **réclamer, effet dans le module propriétaire, enregistrer** (TD31) ; la phrase d'Automation §6.1 est amendée ; les effets sont déjà idempotents (AU11) |
| **M** | **Tranché.** `promises → payments`, `priority → collection`, `payments → customers`… | trois graphes séparés (TD10), calculés par le registre : appels sans cycle (7 niveaux), événements, schéma. `notifications → approvals` s'ajoute (`APPROVAL_REQUESTED`) |
| **N** | Omissions trouvées en classant les événements sans abonné : `IMPORT_BATCH_UPLOADED` et `IMPORT_BATCH_COMMITTED` n'avaient aucun consommateur (la validation et la normalisation ne démarraient jamais) ; `APPROVAL_REQUESTED` ne notifiait personne ; `AUTOMATION_PAUSED` / `_DISABLED` ne pausaient ni n'annulaient les exécutions ; **`ORGANIZATION_CLOSED` n'est traité par personne** (State Machines §16 ne cite que `ORGANIZATION_SUSPENDED`) | quatre handlers ajoutés au registre (`ValidateImportBatch`, `NormalizeImportBatch`, `NotifyApprovers`, `OnAutomationPausedOrDisabled`) et `ORGANIZATION_CLOSED` ajouté aux deux handlers de suspension (amende State Machines §16) |
| **O** | L'expiration d'une approbation dont la cible est résolue est décrite comme une écriture de `collection` dans `approvals` (EC-13, Collection §6) | `approvals` interroge la cible par un port ; retard borné par la cadence du balayage (TD58) |

### 13.2 Amendements à appliquer après validation

| Document | Amendement |
|---|---|
| Data Contract V1.3 | `events` : colonne `available_at timestamptz NOT NULL DEFAULT now()` (mutable ; ajoutée aux colonnes autorisées par le trigger d'immutabilité), index partiel `(available_at, id) WHERE published_at IS NULL` ; §12.1 : `published_at` = tous les handlers abonnés ont **pris en charge** l'événement ; `event_receipts` : `outcome` reçoit `RETRYING` (état technique, comme `DEAD`), colonne `available_at` (NN ssi `RETRYING`), index partiel `(available_at) WHERE outcome = 'RETRYING'` ; `approvals` : propriétaire `approvals` ; §13 : ligne `approvals` ; événements `USER_*`, `MEMBER_*` à ajouter au catalogue (écart J) ; `organizations.status` : valeur `PROVISIONING` (CK ; T14 : `PROVISIONING → ACTIVE`, `PROVISIONING → CLOSED`) |
| Engine Contracts V1.1 | DR4 : précision sur l'implémentation de `rules.contracts` par les propriétaires de faits ; §1.1 : `approvals` en couche Action ; EC-02 : `RETRYING`, et `REPLAY` = reçu terminal présent ; EC-03 : `ReconciliationWindowScan` en deux cas d'usage ; EC5 : **inchangé**, complété par l'échelle générée ; X8 et C12 : catégorie « service d'enregistrement dépendant » (écart G) ; EC-12 : étape en trois transactions (écart L) ; Annexe A : `DB_INVARIANT_VIOLATED` (INTERNAL), `TENANT_CONTEXT_MISSING` (INTERNAL), `LOCK_ORDER_VIOLATION` (INTERNAL) |
| Invariants V1.2 | **C12 : liste fermée et nominative de deux familles** (`AllocatePayment`, `ReverseAllocation`, `ReversePayment` ; `NormalizeImportBatch`) : `CreateOrganization` en sort ; §10.3 : événements `USER_*`, `MEMBER_*` ; règle : toute écriture inter-modules hors C12 se fait dans la transaction du module propriétaire (TD58) |
| Automation Engine V1.1 | §6.1 : l'étape s'exécute en trois transactions (réclamer, effet, enregistrer) ; §10.1 : `ImportReleaser` composé par `jobs` avec `imports.StartImportRelease` et `imports.CompleteImportRelease` |
| State Machines V1 | §1 : état `PROVISIONING` et ses transitions ; `ORGANIZATION_CREATED` émis à la fin du provisioning ; §16 : `ORGANIZATION_CLOSED` traité comme `ORGANIZATION_SUSPENDED` par `collection` et `automation` ; approbation : expiration par interrogation de la cible |
| Collection Engine V1.1 et V1.2 | §4 étape 7 : action `PROPOSED` puis approbation puis `PENDING_APPROVAL`, chacun dans la transaction de son module ; §6 : expiration des approbations ; §8 : `EXECUTING` puis création de la notification dans la transaction de `notifications` |
| Rule Engine V1.1 | §2.3 : les fournisseurs de faits sont implémentés par les propriétaires ; le `FactReader` reste le point d'assemblage |
| Global Test Matrix V1 | famille `TA` (`TA-01` à `TA-37`) ; univers étendu aux décisions `TD`, invariants `TI` et règles `AR` |
| Documents Collection | le nom de module `collection` remplace `collections` (glossaire) |
| Rappels obsolètes (2026-09-19) | `CreateOrganization` n'est plus une écriture inter-agrégats synchrone (TD55, TD59, C12) : synthèse de tête du présent document et justification de TD1 ; Engine Contracts DR3 ; ligne `AR-04` de la matrice. Correction des rappels seulement : aucune décision rouverte |
| Application Contract V1, amendement **B3** (2026-09-21) | mécanique, sans règle métier nouvelle : **B3-a** `ApplySettlement`, `ReverseAllocation` et `ReversePayment` écrivent `invoices.lifecycle` (et `ApplySettlement` émet `INVOICE_DUE_SOON` / `_DUE` / `_OVERDUE`) pour le recalcul immédiat du cycle de vie après annulation d'un règlement (Invariants §3.1) ; **B3-b** lectures déclarées (`OrgStatus`, `CustomerFacts`, `InvoiceFacts`) pour sept cas d'usage de `invoices` et `payments` ; **B3-c** catalogue d'erreurs : quatre codes de litige décidés en Invariants §3.3 mais absents de l'Annexe A (défaut du générateur : la ligne « Erreurs » du tableau du litige n'était pas lue) et `INVOICE_HAS_OPEN_DISPUTE` (T15), erreurs déclarées alignées. Domain V1, tranche 1, §11 |
| Application Contract V1, amendement **B4** (2026-09-21) | mécanique, sans règle métier nouvelle, arbitré après les écarts DV1-1 et DV1-2 révélés par le Domain V1 : **B4-a** `IssueInvoice` et `InvoiceLifecycleScan` écrivent `invoices.collection_cycle` (règle (a) des Invariants §3.1 bis : `+ 1` dans la transaction de la transition vers `OVERDUE`, jamais dans un handler) ; **B4-b** `ReverseAllocation` et `ReversePayment` ne déclarent plus `invoices.InvoiceFacts` (DD23). Aucune modification de C12, des verrous ni des machines à états |
| TD32 et Data Contract, `idempotency_keys` (2026-09-19) | exception nommée : `CreateOrganization` a une portée d'idempotence `(acteur, clé, route)`, l'organisation n'existant pas encore (Application Contract V1, AP-14). Le schéma reprendra l'exception à l'étape PostgreSQL |
| TD19, traduction de la violation de déduplication (**R12-B**, 2026-10-04) | précision, **sans réécriture de TD19** : « violation d'unicité de `dedup_key` → `REPLAY` » s'applique quand l'objet occupant est relu dans l'unité de reprise ; si la contrainte **déclarée** a établi le doublon mais que l'objet occupant n'est plus récupérable à cette relecture (sorti de l'index par une transition concurrente : PG-11c), l'Application rend `DEDUP_REPLAY_UNAVAILABLE` (`CONFLICT`, 409, retryable ; Engine Contracts, Annexe A et EC-11, amendement R12-B ; Application Contract V1, amendement **B11**). Ce n'est pas un défaut (`DB_INVARIANT_VIOLATED` ne s'applique pas : aucun invariant n'est violé) ; l'Application ne retente pas d'elle-même ; aucune règle d'identification historique de l'objet. Toute autre violation reste traduite selon TD19 / TI13. Décision R12-O1 (option B) : `R12_O1_FICHE_B.md` |

### 13.3 Points ouverts (ne bloquent pas la validation)

| # | Point |
|---|---|
| **O1** | Mécanisme d'authentification (session, jeton) et politique de `users` / `memberships` avant le choix de l'organisation : `users` est une table globale sans `organization_id` ; sa politique d'accès doit permettre la recherche par e-mail **avant** la pose de l'organisation, sans ouvrir `memberships` |
| **O2** | Fournisseur d'e-mail, outil d'observabilité, hébergeur, orchestrateur |
| **O3** | Objectifs RPO, RTO, disponibilité, latence de l'outbox (produit + banc) ; fréquence du test de restauration |
| **O4** | Billing (S7) : autorisations issues de l'abonnement ; le module reste vide |
| **O5** | Cadence de mise à jour de `tzdata` |
| **O6** | Outil d'analyse d'imports et d'analyse syntaxique retenu pour la porte d'architecture |

### 13.4 Décisions

| # | Sujet | Statut |
|---|---|---|
| TD1 à TD6 | principes, couches, commandes / requêtes, surface publique, racine de composition, moteurs séparés | **gelé** |
| TD7 à TD14 | découpage : 22 unités ; noms ; références par identifiant ; deux graphes ; `approvals` ; faits inversés ; registre inversé ; administration en lecture seule | à valider (**TD11, TD12 : écarts A, D**) |
| TD15 à TD24 | PostgreSQL : schéma, contraintes nommées, **responsabilités de l'isolation, RLS filet et non chemin (TD17)**, quatre rôles (TD18), traduction d'erreurs, migrations, pooler, UUIDv7 et partitions (TD22), **trois temps (TD23)**, `tzdata` | **gelé** |
| TD25 à TD32 | transactions : unité de travail, point unique de contexte, **échelle de verrous dérivée (TD27, écarts E)**, mécanisme le plus faible, verrou de sujet, nouvelle tentative, **réclamer → revalider → autoriser → agir (TD31)**, idempotence | **gelé** |
| TD33 à TD40 | outbox : **publier n'est pas traiter (TD33)**, **reçu `RETRYING` par handler (TD35, écart B)**, ordre non requis, deux réserves, regroupement, équité, schémas | **gelé** |
| TD41 à TD47 | travailleurs : trois rôles, PostgreSQL file de référence, deux classes, planificateur à plusieurs exemplaires, arrêt propre, `jobs` compose (**écart C**) | **gelé** |
| TD48 à TD50 | Redis : règle « vidé sans perte », usages permis et interdits | **gelé** |
| TD51, TD52 | ports : un double pour chacun, adaptateurs sans règle | **gelé** |
| TD53 | déploiement | **gelé** |
| TD54 | structure par module, démontrée par injection de violation | **gelé** |
| K1 à K23 | **Constitution technique** : propriétaire unique de chaque décision | **gelé** |
| S1 à S6 | **règles de sobriété** ; triage requis / simplifié / différé (§0.3) | **gelé** |
| TD55 | **propriété des écritures** : un module propriétaire, un ensemble fermé de cas d'usage | **gelé** |
| TD56 | **quatre registres** (Module, Commande, Événement, Verrou), source des tests d'architecture | **gelé** |
| TD57 | **fiche de module obligatoire** (possède, commandes, requêtes, événements) | **gelé** |
| TD58 | **composition orchestrée** : un service d'enregistrement dépendant ne devient jamais propriétaire (écart G) | **gelé** |
| TD59 | **plan de provisioning** : `PROVISIONING`, `ProvisioningStep`, `CreateOrganization` hors C12 (écart I) | **gelé** |
| G à M, N, O | écarts **tranchés et validés** ; amendements **appliqués** aux documents figés (§13.2) | **gelé** |
| Noms | **20 noms de commandes figés** ; convention de nommage vérifiée par la porte (§2.6) | **gelé** |
