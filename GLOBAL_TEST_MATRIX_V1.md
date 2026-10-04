# VERQIA — Global Test Matrix V1

Références : Data Contract V1.3, Invariants V1.2, State Machines V1, Rule Engine V1.1, Collection Engine V1.1, Automation Engine V1.1, Engine Contracts V1.1, Risk / Priority / Cashflow V1.1 et `reference_model/`.
Statut : **V1.1** — famille O complétée par Collection Engine V1.2 (proposition à valider). Ce document est **généré** par `test_matrix/build_matrix.py` à partir de `matrix_rows.py` ; la couverture est vérifiée contre un univers extrait des documents figés (`universe.py`).

## 0. Objet

La matrice est l’**oracle d’intégration** de VERQIA. Elle ne juxtapose pas les tests de chaque module : elle croise le Data Contract, les Invariants, les machines à états, les trois moteurs, les contrats d’interface et les projections, avec deux idées directrices :

1. **Des vérificateurs globaux** (§4) qui portent des invariants du *système entier* et s’exécutent après **chaque** scénario, chaque jour simulé.
2. **Une traçabilité vérifiée par machine** (§7) : chaque invariant, règle, machine, contrat, erreur, événement et table est couvert par au moins un test ; un élément sans test fait échouer la porte de CI.

Elle ne contient **aucun seuil de performance chiffré** : ils seront fixés au banc d’essai de l’architecture technique. Elle en fixe les scénarios et les mesures (§5, famille M).

## 1. Niveaux de test

| Niveau | Nom | Contenu | Tests |
|---|---|---|---:|
| L0 | Statique / CI | architecture, contrat ↔ schéma, registres, portes de couverture | 13 |
| L1 | Domain pur | fonctions pures sans base : Rule Engine, modèles, calcul de créneau | 22 |
| L2 | PostgreSQL | contraintes, triggers, index, rôles, partitions | 29 |
| L3 | Cas d’usage intégré | un cas d’usage avec base et outbox, dans une transaction | 52 |
| L4 | Flux entre moteurs | événement → handler → moteur → événement | 46 |
| L5 | Scénario de bout en bout | horloge virtuelle, plusieurs jours simulés, tous les vérificateurs | 30 |
| L6 | Propriétés, différentiel, chaos | génération aléatoire, comparaison à une version naïve, injection de fautes | 18 |
| L7 | Non fonctionnel | performance, volumétrie, exploitation | 6 |

## 2. Oracles

Un test n’est utile que si l’on sait **comment** le résultat attendu est déterminé.

| Oracle | Nom | Principe |
|---|---|---|
| O1 | Modèle de référence exécutable | `reference_model/verqia_models.py` : risque, priorité, trésorerie ; arithmétique entière, sans horloge. L’implémentation de production est comparée à lui. |
| O2 | Cas d’or | Tables d’entrées et de résultats attendus : `golden_cases.json` (22 cas chiffrés), scénarios d’or du Rule Engine (46), scénario de référence du Collection Engine, exemples des passes. |
| O3 | Table de transitions générée | La table des transitions du Domain (source unique) sert à générer les tests positifs et négatifs de chaque machine, et le trigger T14. |
| O4 | Vérificateurs globaux | Les 24 vérificateurs du §4, exécutés à la fin de chaque scénario et après chaque jour simulé. Ils portent des invariants du système entier, pas d’un module. |
| O5 | Registres de schémas et de couverture | Schémas versionnés des événements et de `Decision` ; registres générés des types d’événement, des codes d’erreur et des tables. |
| O6 | Implémentations naïves | Pour chaque calcul SQL ou concurrent : une version simple et lente en Python, comparée sur données aléatoires. |
| O7 | Relations métamorphiques et propriétés | Relations qui doivent tenir quelle que soit l’entrée (monotonie, conservation, stabilité du hash, hystérésis, permutation). |
| O8 | Rejeu et reconstruction | Rejouer le journal, ou reconstruire une projection, doit redonner exactement l’état observé. |
| O9 | Contrat ↔ schéma | Le Data Contract est l’oracle du schéma réel : tout écart est une erreur. |

## 3. Harnais de simulation

| Élément | Contrat |
|---|---|
| **Horloge virtuelle** | seule source de temps, injectée par le port `Clock` ; avance par jours ou par instants ; fuseaux et heure d’été simulables |
| **Identifiants déterministes** | générateur d’UUID seedé ; deux exécutions d’un scénario avec la même graine produisent les mêmes identifiants |
| **Bus d’événements instrumenté** | publie l’outbox ; peut **dupliquer, retarder, réordonner, perdre** des événements selon un plan de fautes |
| **Fournisseur d’envoi simulé** | acceptations, erreurs transitoires et permanentes, réponses perdues, rapports en double ; journalise chaque appel avec l’état des transactions |
| **Scénario en langage déclaratif** | une chronologie d’ordres (créer, émettre, payer, annuler…) et d’attentes ; rejouable |
| **Plan de fautes** | pannes de processus entre instructions, échecs de sérialisation, partitions absentes, décalages d’horloge ; chaque faute est reproductible par sa graine |
| **Instantané et différence d’état** | l’état du monde (toutes les tables métier) est capturé avant et après pour comparer deux exécutions ou deux ordres de livraison |
| **Isolation** | chaque scénario s’exécute dans sa propre organisation (et certains dans deux organisations simultanées) |

## 4. Vérificateurs globaux (post-conditions)

Exécutés **à la fin de chaque scénario de niveau L4 à L6** et **après chaque jour simulé** des scénarios L5. Un seul rouge invalide le scénario.

| # | Vérificateur | Ce qu’il garantit |
|---|---|---|
| G01 | Isolation du tenant | aucune clé étrangère ni requête ne franchit une organisation ; RLS active ; aucune ligne d’une organisation dans le résultat d’un rôle scopé à une autre |
| G02 | Conservation de l’argent | `paid_minor` = Σ allocations (par facture) ; `allocated_minor` = Σ allocations (par paiement) ; `outstanding_minor` = total − payé ; 0 ≤ Σ ≤ bornes (T1 à T6, T10) |
| G03 | Cohérence des états dérivés | règlement et statut de paiement égaux à la fonction de leurs montants ; `settled_on` ⇔ `PAID` |
| G04 | Cycle de vie et historique | le cycle de vie est monotone ; la chaîne de `invoice_state_history` se rejoue jusqu’à l’état courant ; aucune facture hors `DRAFT` créée hors import |
| G05 | Validité des transitions | toute transition enregistrée (historiques, exécutions, actions…) appartient à la table de transitions de sa machine |
| G06 | Immuabilité | empreinte des lignes append-only et des champs figés inchangée entre deux instants |
| G07 | Outbox | chaque transaction qui change un état ou un fait a son événement ; chaque événement `TRANSITION` correspond à une ligne d’historique ; `aggregate_version` croît par agrégat ; aucun événement sans transaction |
| G08 | Charges utiles sans donnée personnelle | aucun nom, téléphone, e-mail dans `events`, `decision_snapshot`, traces |
| G09 | Idempotence globale | rejouer chaque événement et chaque commande une seconde fois ne change pas l’état (reçus, clés, garde d’état) |
| G10 | Déduplication | aucune paire d’actions ou de notifications non annulées avec la même clé ; aucun `(automation_id, trigger_key, subject_id)` en double |
| G11 | Concurrence d’exécution | au plus une exécution non terminale par (automatisation, sujet) |
| G12 | Causalité bornée | `causation_depth` ≤ 20 ; aucun cycle dans les chaînes de causalité |
| G13 | Aucun envoi dans une transaction | le journal du fournisseur ne contient aucun appel émis pendant une transaction de base ouverte |
| G14 | Niveaux de recouvrement | dans un (facture, cycle) le plus haut niveau `SCHEDULED`/`EXECUTING`/`DONE` ne décroît jamais ; niveau ≥ 3 dès `OVERDUE` |
| G15 | Garde-fous respectés | aucune action automatique n’a été planifiée ou exécutée alors qu’une exception intégrée s’appliquait à cet instant (audit des décisions enregistrées) |
| G16 | Décisions explicables | chaque action porte les niveaux de risque, de priorité et de recouvrement **séparés**, la version des règles, `primary_exception` ; chaque étape porte sa revalidation |
| G17 | Projections = modèle de référence | risque, priorité et trésorerie courants égalent le résultat du modèle de référence recalculé depuis les sources ; âge des projections dans les SLO |
| G18 | Conservation de la trésorerie | pour chaque run : somme des lignes ≤ restant dû par facture et par client (CF4) ; un seul `is_current` par triplet ; promotion monotone |
| G19 | Audit conforme | chaque commande sensible a sa ligne d’audit ; les transitions temporelles du Scheduler n’en ont pas |
| G20 | Lots d’import | aucune exécution issue d’un événement de lot avant `RELEASING` ; démarrages par jour ≤ `release_max_per_day` ; toutes les exécutions existent dès la libération |
| G21 | Non-rétroactivité | aucune exécution déclenchée par un événement antérieur à `active_since` ni par un instant antérieur à l’émission de la facture |
| G22 | Ordre des verrous | le journal des verrous respecte l’ordre global (paiements → factures par identifiant → promesses → actions → exécutions → notifications) |
| G23 | Anonymisation sans effet financier | après une anonymisation, l’empreinte de toutes les colonnes financières, dates et états est inchangée |
| G24 | Aucune lecture d’horloge dans le Domain | analyse statique : aucun appel à l’heure système hors du port `Clock` ; rejeu déterministe à `as_of` égal |

## 5. Tests par famille

Colonne « Couvre » : jetons de l’univers de traçabilité (`CON` contrat, `TAB` tables, `INV` invariants et décisions, `SM`/`SMX` machines et cascades, `RULE`/`EXC`/`RE` Rule Engine, `COL` Collection, `AUT` Automation, `ENG` Engine Contracts, `JOB` jobs, `RPC` Risk/Priority/Cashflow, `GOLD` cas d’or, `ERR` erreurs, `EVT` événements, `OUT` issues, `RSN` causes). `FAM:*` = **porte de couverture** (registre vérifié en CI). La liste complète par test est en Annexe B.

### A. Schéma et contraintes PostgreSQL

Ces tests s’exécutent **sur PostgreSQL** (jamais sur une base de substitution) : les garanties financières vivent dans la base, pas seulement dans le code.

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| DB-01 | L2 | Allocations : la somme par paiement reste dans [0, montant] et la somme par facture dans [0, total] ; un reversal ne dépasse jamais son allocation d’origine ; deux sessions concurrentes qui allouent le même disponible : une seule réussit. | O4-G02, O6 | CON:T1 CON:T2 CON:T3 · ENG:EC-05 ENG:EC5 |
| DB-02 | L2 | Caches vérifiés en fin de transaction : `paid_minor`, `settlement_state`, `settled_on`, `allocated_minor`, `status` égalent la somme des allocations ; toute divergence provoquée à la main est refusée au `COMMIT`. | O4-G02, O4-G03 | CON:T4 CON:T5 · TAB:invoices TAB:payments TAB:payment_allocations TAB:payment_reversals |
| DB-03 | L2 | Aucune allocation nette positive sur une facture `DRAFT`, `CANCELLED` ou `VOID`, ni sur un paiement `REVERSED`. | O4-G02 | CON:T6 CON:T10 |
| DB-04 | L2 | Lignes de facture immuables hors `DRAFT` ; à l’émission, la somme des lignes égale le total. | O4-G06 | CON:T7 CON:T9 · TAB:invoice_items |
| DB-05 | L2 | Tables append-only : `UPDATE`, `DELETE` et `TRUNCATE` refusés au rôle applicatif sur toutes les tables historiques ; le rôle de confidentialité ne peut toucher que ses colonnes de texte. | O4-G06 | CON:T8 · TAB ×9 · INV:D7 |
| DB-06 | L2 | Montant contesté ≤ total de la facture ; numéro de tentative ≤ `max_attempts`. | O4-G03 | CON:T11 CON:T12 · TAB:invoice_disputes |
| DB-07 | L2 | Après émission, `number`, `customer_id`, `currency`, `issue_date`, `due_date`, `total_minor` sont immuables ; une création par import (INSERT) n’est pas concernée ; une renégociation passe par une promesse. | O4-G06 | CON:T13 · INV:N1 |
| DB-08 | L2 | Garde de transition : pour chacune des 12 machines protégées, **tout couple (état, état)** est essayé ; il est accepté si et seulement s’il figure dans la table de transitions du Domain ; la table SQL est **générée** depuis le Domain et comparée. | O3 | CON:T14 · SM ×13 · INV:C3 |
| DB-09 | L2 | `VOID` refusé tant qu’un litige `OPEN` existe ; accepté dès sa résolution. | O3 | CON:T15 · SM:S5 |
| DB-10 | L2 | Clés étrangères composites : pour **chaque** FK composite, un enregistrement pointant vers une ligne d’une autre organisation est refusé ; `collection_actions`, `promises`, `priority_items` refusent un client différent de celui de la facture. | O4-G01 | **TAB:\*** · INV:C2 · ENG:X11 |
| DB-11 | L2 | Index uniques partiels : un litige `OPEN`, une promesse `ACTIVE` par portée, un contact principal actif par canal, une exécution non terminale par (automatisation, sujet), un run `RUNNING` et un run courant par triplet de trésorerie, un abonnement actif, clés de déduplication hors `CANCELLED`/`SUPPRESSED`. | O4-G10, O4-G11 | AUT:AU6 · RPC:RP17 · SM:13 · TAB ×7 |
| DB-12 | L2 | Colonnes générées : `outstanding_minor`, `weighted_minor`, `automation_versions.trigger_type` ; `weighted_minor` égale le modèle de référence sur 20 000 valeurs aléatoires. | O1, O6 | RPC:RP20 · TAB:cashflow_lines TAB:automation_versions |
| DB-13 | L2 | Chaque `CHECK` d’énumération et de cohérence (états, portées XOR, `is_current ⇒ COMPLETED`, dates) est refusé quand on le viole. | O9 | **TAB:\*** |
| DB-14 | L2 | Exclusion des suspensions : chevauchement refusé, y compris pour la portée organisation (cible non nulle grâce au `coalesce`) ; extension `btree_gist` présente. | O4 | TAB:collection_holds |
| DB-15 | L2 | Partitions : `events` et `audit_logs` partitionnées par mois (clé `(id, occurred_at)`) ; le gestionnaire crée les trois prochaines partitions ; alerte si la partition par défaut reçoit une ligne ; le détachement d’une partition la conserve. | O4 | JOB:PartitionManager · INV:D8 · TAB:events TAB:event_receipts TAB:idempotency_keys |
| DB-16 | L2 | Row-Level Security : sans `app.organization_id`, aucune ligne n’est visible ; le rôle applicatif n’est pas propriétaire des tables ; le rôle de migration est distinct du rôle d’exécution. | O4-G01 | INV:C2 · ENG:X11 |
| DB-17 | L2 | `ON DELETE RESTRICT` partout : la suppression d’une ligne parente référencée est refusée pour chaque FK. | O4 | **TAB:\*** |
| DB-18 | L2 | Types : montants `bigint` en unité mineure, devise `char(3)` majuscule, tous les instants `timestamptz` UTC ; aucune colonne flottante monétaire. | O9 | **TAB:\*** |
| DB-19 | L0 | **Contrat ↔ schéma** : le schéma réel (colonnes, types, nullité, contraintes, index) est comparé au Data Contract ; tout écart fait échouer la CI. | O9 | **TAB:\*** |
| DB-20 | L2 | Tables du domaine « import » et « organisation » : contraintes des lots (unicité du fichier, `approved_by` requis à partir de `APPROVED`), des réglages et des jours fériés. | O4 | TAB ×9 |
| DB-21 | L2 | Tables des moteurs : contraintes de `risk_profiles`, `priority_items`, leurs snapshots, `approvals`, `automations`, `message_templates`, `notification_deliveries`. | O4 | TAB:risk_profiles TAB:priority_items TAB:approvals TAB:automations TAB:message_templates TAB:notification_deliveries |

### B. Machines à états et cascades

Pour chaque machine, deux familles de tests **générées** depuis la table de transitions : chaque transition permise réussit (garde satisfaite, historique écrit, événement émis) ; chaque couple non permis est refusé au Domain **et** en base (T14).

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| SM-01 | L3 | Organisation : `ACTIVE ⇄ SUSPENDED`, `→ CLOSED` terminal ; suspension : exécutions en pause `ORG_INACTIVE`, aucune communication ; réactivation : reprise. Client : matrice `ACTIVE`/`INACTIVE`/`ARCHIVED` opération par opération ; archivage refusé avec facture ouverte ; réactivation jamais automatique. | O3, tableau §Customer | SM:1 SM:2 · INV:N3 INV:D6 · RSN:ORG_INACTIVE RSN:CUSTOMER_INACTIVE RSN:CUSTOMER_ARCHIVED |
| SM-02 | L3 | Facture, cycle de vie : sauts permis, jamais de retour en arrière, gel quand `PAID`, recalcul à l’annulation du règlement, rattrapage à l’émission tardive, immuabilité de l’échéance, une seule transition par événement émis. | O3, O4-G04 | SM:3 SM:S3 · INV:N1 INV:C3 |
| SM-03 | L3 | Facture, règlement dérivé : chaque transition provoquée par une allocation ou un reversal produit le bon événement ; `PARTIALLY_PAID → PARTIALLY_PAID` n’en produit aucun ; `settled_on` posé et effacé ; `collection_cycle` incrémenté dans les deux cas prévus, jamais deux fois dans la même transaction ; annulation d’un règlement : cycle de vie recalculé en avant dans la transaction du reversal (B3-a), sans attendre le balayage. | O3, O4-G02 | SM:4 SM:S11 · INV:N12 |
| SM-04 | L3 | Litige : ouverture, résolution rejetée / fondée ; effet sur `collectible_minor` ; suspension seulement si le recouvrable est nul ; `VOID` refusé pendant un litige ouvert ; procédure V1 d’un litige fondé (reverser, annuler, ré-émettre). | O3 | SM:5 SM:S5 · INV:D1 |
| SM-05 | L3 | Paiement : allocation, reversal d’allocation, reversal du paiement (toutes les allocations reversées dans la même transaction), états dérivés, `REVERSED` terminal ; date de valeur non future dans le fuseau de l’organisation. | O3 | SM:6 · INV:N2 INV:C10 |
| SM-06 | L3 | Promesse : création (montant, date, unicité par portée), tenue, rupture après délai de grâce, annulation ; modification = annulation + création ; `FULFILLED` reste terminal après un reversal ; promesse client sans facture ouverte annulée. | O3 | SM:7 · INV:N5 INV:N6 INV:N11 |
| SM-07 | L3 | Action de recouvrement : toutes les transitions du tableau, dont `SCHEDULED → DONE` (tâche humaine, issue obligatoire), `PENDING_APPROVAL → SUPPRESSED`, retry `EXECUTING → SCHEDULED`, `SUPPRESSED` ≠ `CANCELLED` ; libération de la clé après suppression. | O3 | SM:8 SM:S1 SM:S8 SM:S9 · COL:C6 |
| SM-08 | L3 | Suspension manuelle et approbation : création, libération, expiration (lecture par dates, indépendante du balayage) ; approbation accordée / refusée / expirée / cible résolue (`TARGET_RESOLVED`). | O3 | SM:9 SM:10 |
| SM-09 | L3 | Automatisation (`active_since` posé et effacé) et exécution (les 7 états, retry, reprise) : chaque cause de pause et sa levée. | O3 | SM:11 SM:12 SM:S2 · RSN ×10 |
| SM-10 | L3 | Run de trésorerie : `RUNNING → COMPLETED / FAILED`, bascule de `is_current`, jamais courant si `FAILED`. | O3 | SM:13 |
| SM-11 | L3 | Lot d’import : les 13 états, annulation possible seulement avant `COMMITTED`, jamais après. | O3 | SM:14 |
| SM-12 | L3 | Machines compactes : notification, abonnement, utilisateur, adhésion (au moins un `OWNER` actif), gabarit de message. | O3 | SM:15 |
| SM-13 | L4 | Les 17 cascades du tableau des couplages : chacune est déclenchée par son événement source et vérifiée ; celles « par événement » sont idempotentes et revalident ; celle de l’allocation est atomique. | O3, O4-G09 | SMX ×17 |
| SM-14 | L1 | Chaque `UPDATE … WHERE état = ancien` qui ne touche aucune ligne produit `INVALID_TRANSITION` ou `CONCURRENT_MODIFICATION` ; deux transitions concurrentes : une seule gagne. | O3 | INV:C3 INV:C4 |
| SM-15 | L3 | Décisions d’état verrouillées : `DISPUTED` orthogonal, facture émise à zéro refusée, archivage refusé avec facture ouverte, une correction financière ne réactive jamais un client archivé. | O3 | INV:D6 INV:N3 |

### C. Événements, outbox et handlers

Le socle de fiabilité : aucun effet sans événement, aucun événement perdu, aucun effet dupliqué.

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| EV-01 | L3 | Atomicité de l’outbox : panne avant `COMMIT` = ni changement ni événement ; après `COMMIT` = les deux ; mutation, transition et demande produisent chacune leur événement dans la même transaction. | O4-G07 | INV:C5 · ENG:EC-01 ENG:EC1 |
| EV-02 | L1 | Charges utiles : liste blanche de champs par type ; aucune donnée personnelle (nom, téléphone, e-mail) dans `events`, `decision_snapshot`, traces du Rule Engine. | O5, O4-G08 | INV:C9 · ENG:X10 · ERR:EVENT_SCHEMA_INVALID ERR:EVENT_PAYLOAD_NOT_WHITELISTED |
| EV-03 | L4 | Handler : première livraison → `PROCESSED` ou `SKIPPED` ; deuxième livraison → `REPLAY` (compté, rien d’écrit) ; échecs répétés (10 s, 1 min, 5 min, 30 min, 2 h) → `DEAD` ; `DEAD` jamais retraité automatiquement, seul `ReplayDeadEvent` le relance ; `REPLAY` et `SKIPPED` distincts dans les métriques. | O4-G09 | ENG:EC-02 ENG:EC2 ENG:P1 ENG:P2 ENG:X16 · INV:C6 INV:C11 INV:N10 |
| EV-04 | L6 | Désordre : événements d’un même agrégat livrés dans le désordre, ou obsolètes (`aggregate_version` plus ancienne) → `SKIPPED` ; les handlers relisent l’état et ne supposent aucun ordre entre agrégats. | O8 | ENG:X1 ENG:X14 ENG:X6 |
| EV-05 | L4 | Profondeur de causalité ≤ 20 ; au-delà, l’émission est refusée et alertée ; une chaîne Risk → Priority → Automation reste finie. | O4-G12 | ENG:X7 · AUT:AU9 · ERR:CAUSATION_DEPTH_EXCEEDED |
| EV-06 | L0 | Registre de schémas : chaque type d’événement et `Decision` ont un schéma versionné ; une évolution non additive (champ retiré, renommé) fait échouer la CI ; une rupture exige une double publication. | O5 | ENG:EC6 ENG:EC-01 |
| EV-07 | L4 | Catégories : `REQUEST` a un seul destinataire et se regroupe ; `TRANSITION` correspond à une ligne d’historique ; `RESULT` seulement sur changement de niveau ; `MUTATION` pour les faits append-only. | O4-G07 | INV:C5 INV:N9 · ENG:EC-14 |
| EV-08 | L4 | Événements des lots d’import : `import_batch_id` propagé ; aucune automatisation ne les consomme avant `RELEASING`. | O4-G20 | ENG:X9 · AUT:AU10 |
| EV-09 | L6 | **Rejeu global** : rejouer tout le journal d’événements sur une base vierge (ou rejouer chaque événement deux fois) aboutit au même état final (projections, actions, exécutions). | O8 | ENG:X6 · INV:C6 |
| EV-10 | L0 | Porte de couverture : **tout type d’événement du catalogue** a un test producteur, un test de schéma et, s’il a des consommateurs, un test de réaction ; le registre est généré et vérifié en CI. | O5 | **EVT:\*** |
| EV-11 | L3 | Catalogue explicite : les événements d’organisation, de client, de facture, de paiement, de promesse, d’action, de suspension, d’approbation, d’automatisation, d’import, de notification et d’abonnement sont chacun observés dans un scénario de bout en bout (contrôle croisé de la porte). | O4-G07 | EVT ×10 |

### D. Rule Engine

Le Rule Engine est une fonction pure : ses tests sont des tables d’entrées et de décisions attendues.

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| RE-01 | L1 | **Les 52 scénarios d’or du Rule Engine §10.2**, exécutés à l’identique (une entrée, une décision complète : issue, exception primaire, trace, niveau). | O2 | RE ×52 |
| RE-02 | L1 | Les 13 garde-fous, chacun en échec et en réussite ; **ordre fixe** ; toutes évaluées et consignées, une seule décide (`primary_exception`). | O2 | EXC ×13 · RULE:R1 RULE:R2 |
| RE-03 | L1 | Déterminisme : mêmes entrées, même `decision_id` ; aucune lecture d’horloge ; permutation des termes d’un `all` / `any` sans effet ; ajouter une exception ne transforme jamais `SUPPRESS` en `PROCEED`. | O7 | RULE:P1 RULE:P2 RULE:P3 · COL:CP3 · ENG:X12 |
| RE-04 | L1 | Logique à trois valeurs : table de vérité complète ; `UNKNOWN` jamais traité comme vrai ; racine inconnue ⇒ `SKIP`. | O7 | RULE:R7 |
| RE-05 | L1 | Non-contournement : une définition ne peut ni retirer, ni réordonner, ni désactiver une exception intégrée ; les exceptions ajoutées s’évaluent après. | O2 | RULE:P4 RULE:R1 |
| RE-06 | L4 | Barrière de fraîcheur : projection plus ancienne que l’événement → `DEFER` (30 s, 2 min, 10 min, 30 min) puis évaluation marquée `stale` ; égalité acceptée ; événement hors `refresh_events` → aucune barrière ; recalcul sans changement met `computed_at` à jour. | O2 | RULE:R2 RULE:R13 RULE:P5 |
| RE-07 | L1 | Applicabilité et contournement : classes intégrité / métier / politique / livraison ; `OverrideGrant` typé produit par le domaine (jamais un booléen) ; rôles minimaux ; hold `LEGAL` jamais contournable. | O2 | RULE:R3 RULE:R10 · ERR:OVERRIDE_NOT_ALLOWED ERR:OVERRIDE_ROLE_INSUFFICIENT ERR:OVERRIDE_REASON_REQUIRED ERR:OVERRIDE_ORIGIN_NOT_MANUAL |
| RE-08 | L1 | Temps : faits calculés depuis les dates, indépendants du retard du Scheduler ; fuseau de l’organisation, jours ouvrés, jours fériés, heure d’été. | O2 | RULE:R4 RULE:P7 · INV:C10 |
| RE-09 | L0 | Validateur de définitions : une définition invalide **par code d’erreur** (schéma, fait inconnu, type, action, niveau, complexité, retrait d’une exception, boucle, projection, canal désactivé, couple niveau/type, plage d’étape) ; fuzzing du schéma. | O2 | RULE:R8 · ERR ×14 |
| RE-10 | L6 | Chaque fait SQL comparé à une implémentation naïve sur données aléatoires ; faits comportementaux (formules entières, demi-haut) ; `unallocated_payment_minor`. | O6 | RULE:R5 · RPC:RP8 |
| RE-11 | L4 | Persistance de la décision : trace complète dans `decision_snapshot` et `revalidation_result` ; `SKIP` et `DEFER` au niveau du déclencheur non persistés (compteurs) ; explication à la demande identique à la décision réelle. | O8 | RULE:R6 · COL:CP2 |
| RE-12 | L1 | Niveau : table ordonnée, premier appariement, niveau initial 0, plancher 3 dès `OVERDUE`, non-régression sur `SCHEDULED`/`EXECUTING`/`DONE` seulement, `SKIP` avec raison. | O2 | RULE:R9 RULE:R15 RULE:R16 · INV:N7 |
| RE-13 | L2 | Isolation : évaluer un sujet de l’organisation A avec le contexte de B → `SUBJECT_NOT_FOUND`, aucune ligne de A lue. | O4-G01 | RULE:R11 RULE:R12 RULE:R14 RULE:P6 · ERR:SUBJECT_NOT_FOUND ERR:FACT_UNKNOWN_NAME |

### E. Collection Engine

De la décision à l’action : création, planification, exécution, retry, repli.

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| CO-01 | L5 | **Scénario de référence** (émission le 2026-09-28, échéance 2026-10-15) : chaque action attendue (date, niveau, type, statut) comparée à la table du Collection Engine §11 ; week-ends et jours fériés ; S6 sans effet à risque `MEDIUM` (REPLAY). | O2 | COL:C10 COL:C3 COL:CP1 |
| CO-02 | L5 | Variantes du scénario : risque `HIGH` (niveau 5) ; règlement à J+7 ; promesse à J+5 ; litige partiel (montant recouvrable dans le message) ; client `INACTIVE` en cours de route. | O2 | COL:C11 |
| CO-03 | L3 | Déduplication `{facture}:{type}:L{niveau}:C{cycle}:R{occurrence}` : `occurrence` lue dans l’exécution, jamais fournie ; `manual:{clé}` ; une action `SUPPRESSED` libère sa clé, une `DONE`/`FAILED` la garde ; rejet d’approbation → pas de re-proposition dans le cycle. | O4-G10 | COL:C4 COL:C8 · ERR:ACTION_LEVEL_REGRESSION |
| CO-04 | L3 | Canaux : `EMAIL` (client), `IN_APP` (interne), `PHONE` (tâche humaine) ; `SMS` et `WHATSAPP` rejetés à la validation ; `IN_APP` ne joint jamais le client. | O2 | COL:C1 · ERR:CHANNEL_NOT_ENABLED |
| CO-05 | L3 | Repli humain : `NO_CONTACT`, `NO_CONSENT`, `FAILED` → une seule tâche `FOLLOW_UP`, sans repli du repli ; consentement du contact de référence sans repli vers un autre contact. | O2 | COL:C2 · RULE:R11 · INV:N4 |
| CO-06 | L1 | Matrice type × niveau (rappel 1–4, appel 3–5, suivi 3–5, escalade 4–5) et plages de niveaux par étape. | O2 | COL:C3 · INV:N8 · ERR:ACTION_LEVEL_INVALID ERR:ACTION_LEVEL_BELOW_MINIMUM |
| CO-07 | L3 | Pool de rôle : réclamation simultanée par deux membres (une seule gagne) ; pool jamais vide ; file de travail triée par priorité puis niveau puis échéance. | O6 | COL:C5 · ERR:CONCURRENT_MODIFICATION |
| CO-08 | L3 | Tâches humaines : `SCHEDULED → DONE` avec issue obligatoire ; alerte de retard sans changement de statut ; issues suggérant promesse ou litige sans les créer. | O3 | COL:C6 · OUT ×7 |
| CO-09 | L3 | Issues d’une action en liste fermée : `SENT`, `BOUNCED`, annulations ; toute autre valeur refusée par la base. | O4 | COL:C7 · OUT:SENT OUT:BOUNCED OUT:USER_CANCELLED OUT:APPROVAL_REJECTED OUT:APPROVAL_EXPIRED |
| CO-10 | L3 | Plafond de messages par client et par jour, lissage du débit, fenêtre de communication (report, pas erreur), consolidation **non** faite (un message par facture, répétition seulement si définie). | O2 | COL:C9 · ERR:ACTION_MAX_ATTEMPTS_REACHED |
| CO-11 | L3 | Actions manuelles : mêmes garde-fous, même plancher, même non-régression ; override avec audit ; niveau dans la plage du type. | O2 | COL:C11 · ERR:ACTION_APPROVAL_REQUIRED |
| CO-12 | L3 | Gabarits par défaut en `DRAFT` : l’activation d’une automatisation exige des gabarits `ACTIVE` ; gabarit introuvable à l’exécution → `FAILED` sans réessai. | O2 | COL:C12 · ERR:TEMPLATE_UNAVAILABLE |
| CO-13 | L4 | Rebond : action `DONE`, issue `BOUNCED`, alerte et tâche de suivi ; rapport de livraison idempotent. | O2 | COL:C13 · ENG:EC-04 |
| CO-14 | L4 | Envoi : tentatives 5 min / 30 min / 2 h avec revalidation à chacune ; erreur permanente = `FAILED` immédiat ; `EXECUTING` bloqué > 15 min repris ; aucun envoi dans une transaction de base ; clé fournisseur `{notification_id}:{attempt_no}`. | O4-G13 | ENG:X13 ENG:X3 ENG:EC8 · COL:CP4 COL:CP5 COL:CP6 COL:CP7 |
| CO-16 | L3 | Alerte responsable : une **notification interne** `MANAGER_ALERT` (une par membre du pool), dédupliquée par `{action_id}:{user_id}` ; jamais un type d’action ; les escalades de niveau 4–5 la produisent. | O2 | INV:D5 |
| CO-15 | L1 | Principes : le Collection Engine ne décide jamais si agir ; une action porte son snapshot ; revalidation à chaque frontière. | O4-G15 | COL:CP1 COL:CP2 COL:CP3 · ENG:EC-11 |

### F. Automation Engine

Exécutions longues et datées : la difficulté est le temps, la reprise et l’absence d’effets rétroactifs.

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| AT-01 | L5 | Une exécution longue et datée par (automatisation, sujet) : le gabarit par défaut déroule ses six étapes aux bonnes dates ; chaque étape se revalide. | O2 | AUT:AU1 AUT:AP1 AUT:AP2 |
| AT-02 | L0 | Schéma de définition : les huit types d’étapes ; branches vers l’avant seulement (terminaison) ; `PAUSE` n’est pas une étape ; déclencheurs autorisés et sujets ; pas de `CASHFLOW_UPDATED`. | O2 | AUT:AU2 AUT:AU3 AUT:AP6 · INV:D2 |
| AT-03 | L3 | Grammaire du `trigger_key` : chaque source (événement, temps unique, temps récurrent, inscription, import, reprise) ; `occurrence = n.k` ; répétition bornée. | O2 | AUT:AU4 |
| AT-04 | L5 | Non-rétroactivité : événement antérieur à `active_since` ; facture émise tardivement ; balayeur arrêté 30 h (rattrapé) et 5 jours (écarté et compté) ; événement de plus de 72 h écarté. | O4-G21 | AUT:AP5 AUT:AU5 · SM:S6 |
| AT-05 | L1 | `LATEST_ONLY` : dernière étape **applicable** d’une séquence continue ; remontée si la dernière n’est pas applicable ; les précédentes `SUPERSEDED` ; **jamais une autorisation d’exécution** (repasse par Rule et Collection) ; imposé à la reprise, à l’import, à la ré-inscription. | O2 | ENG:X15 ENG:P3 |
| AT-06 | L4 | Pause et reprise : chaque cause levée par son événement ; deux causes simultanées (une seule levée) ; reprise à l’étape courante revalidée ; alerte à 180 jours sans annulation. | O2 | AUT:AP7 |
| AT-07 | L3 | Une seule exécution non terminale par (automatisation, sujet) : déclenchement pendant une exécution active → `SKIPPED` ; les états terminaux coexistent. | O4-G11 | AUT:AU6 · ERR:EXECUTION_RATE_LIMITED |
| AT-08 | L5 | Ré-inscription : règlement annulé après la fin du parcours → nouvelle exécution, nouveau cycle, nouvelles clés de déduplication ; reprise manuelle d’un échec (`retry:{id}`). | O2 | AUT:AU7 |
| AT-09 | L3 | Activation : `enrollment_mode` obligatoire ; préconditions ; aperçu = simulation **sans effet** (aucune écriture, aucun événement, aucune notification) ; vérification atomique de l’empreinte ; `active_since = as_of` de l’aperçu ; empreinte différente → `ENROLLMENT_PREVIEW_STALE`, **aucune inscription partielle** ; aperçu identique à l’exécution réelle rejouée. | O8 | AUT:AU8 · ERR:AUTOMATION_PRECONDITIONS_NOT_MET ERR:ENROLLMENT_PREVIEW_STALE · INV:N13 · ENG:P4 |
| AT-10 | L4 | Anti-boucles : définition (branches, répétitions), **ensemble actif** (A ↔ B refusé à l’activation), exécution (profondeur ≤ 20, 10 démarrages par sujet et par jour). | O4-G12 | AUT:AU9 · ERR:AUTOMATION_SET_LOOP_DETECTED |
| AT-11 | L5 | Libération d’un lot de 5 000 factures : les 5 000 exécutions **existent** dès la libération (`WAITING`) ; au plus `release_max_per_day` démarrent par jour, dans l’ordre de priorité ; pause / reprise ; `RELEASED` = toutes créées et planifiées. | O4-G20 | AUT:AU10 · INV:N14 |
| AT-12 | L6 | Au moins une fois, effets idempotents : panne entre l’effet et l’écriture de la ligne d’étape ; deux workers sur la même exécution ; `Reaper` ; nouvelles tentatives 1 / 5 / 30 min ; isolation d’une exécution défaillante ; équité entre organisations. | O8 | AUT:AU11 AUT:AP3 AUT:AP4 |
| AT-13 | L2 | Amendements de contrat : `active_since` (⇔ `ACTIVE`), index d’exécution unique, index d’import, grammaire du `trigger_key`. | O9 | AUT:AU12 |
| AT-14 | L4 | Approbations en attente : `WAITING` jusqu’à `expires_at` ; décision qui réveille ; cible résolue → `TARGET_RESOLVED` ; explicabilité de chaque étape (`revalidation_result`). | O4-G16 | AUT:AP7 AUT:AP8 · ENG:EC-13 · ERR:APPROVER_NOT_ELIGIBLE ERR:APPROVAL_ALREADY_DECIDED ERR:SELF_APPROVAL_FORBIDDEN ERR:APPROVAL_COMMENT_REQUIRED ERR:APPROVAL_EXPIRED |

### G. Risk, Priority, Cashflow

Le modèle de référence (`reference_model/`) est l’oracle ; l’implémentation SQL est comparée à lui.

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| RP-01 | L1 | **Cas d’or de risque** G1 à G5 reproduits chiffre pour chiffre ; score maximal 100 ; monotonie de chaque facteur ; historique insuffisant = 0. | O1, O2 | GOLD:G1 GOLD:G2 GOLD:G3 GOLD:G4 GOLD:G5 · RPC:RP3 RPC:RP1 RPC:PA RPC:PB RPC:PG |
| RP-02 | L1 | **Cas d’or de priorité** P1 à P7 ; domaine 0–95 ; plafonds après stabilisation ; un plafond ne relève jamais un niveau ; le niveau publié est la référence suivante ; le signal de rapprochement ne change ni score ni niveau mais change le hash. | O1, O2 | GOLD ×7 · RPC:RP4 RPC:RP15 RPC:RP16 RPC:RP23 |
| RP-03 | L1 | **Cas d’or de trésorerie** C1 à C10 (scénarios, échue / non échue, litige, promesse, retard long, non-alloué FIFO, non-alloué qui couvre tout). | O1, O2 | GOLD ×10 · RPC:RP5 RPC:RP11 |
| RP-04 | L6 | Propriétés du Cashflow : conservation par facture **et par client** ; réserve ≤ non-alloué ; aucune ligne `REALIZED` dans une prévision ; `pondéré` = arrondi décimal demi-haut ; probabilités dans [0, 1] ; déterminisme. | O7 | RPC ×9 |
| RP-05 | L6 | `input_hash` : stable dans une tranche (17 → 18 jours), distinct entre tranches, sensible au niveau précédent ; contenu du snapshot **identique** pour deux valeurs brutes d’une même tranche ; Cashflow haché sur des entrées **brutes**. | O7 | RPC:RP6 RPC:RP14 · ENG:X17 |
| RP-06 | L6 | Hystérésis : séquences aléatoires oscillant autour d’un seuil ; jamais plus de changements qu’en son absence ; `RESULT` seulement sur changement de niveau publié. | O7 | RPC:RP3 RPC:RP15 |
| RP-07 | L4 | `RISK_CHANGED` → une demande de portée client → traitement par lots de 200 factures, reprenables, chacun idempotent ; un client à 50 000 factures ne produit pas de transaction unique ; pas de cycle Risk ↔ Priority. | O4-G17 | RPC:RP21 RPC:RP13 RPC:PE |
| RP-08 | L4 | Fraîcheur : `ProjectionDailyRefresh` (05:00 local) et `ProjectionSafetyNet` (2 h) ; un événement de rafraîchissement supprimé est réparé ; SLO mesurés (99 % avant 08:00, p99 ≤ 26 h, alerte à 36 h). | O8 | RPC:RP9 RPC:RP22 RPC:RP7 · JOB:ProjectionDailyRefresh JOB:ProjectionSafetyNet |
| RP-09 | L4 | Reconstruction et mise à niveau de modèle : `RebuildProjection` reproduit exactement les projections courantes ; aperçu du nombre de changements de niveau ; `cause = MODEL_UPGRADE` regroupé. | O8 | RPC:RP10 RPC:PC RPC:PD |
| RP-10 | L3 | Run de trésorerie : au plus un `is_current` par triplet ; promotion atomique et **monotone** (un run retardataire ne remplace pas un plus récent) ; même `input_hash` → `REPLAY` ; runs planifiés (10 par jour) et événementiels regroupés sur 5 min. | O1 | RPC:RP17 RPC:RP11 · ERR:CASHFLOW_RUN_CONFLICT ERR:CASHFLOW_HORIZON_INVALID ERR:CASHFLOW_SCENARIO_INVALID ERR:CASHFLOW_INPUT_INCONSISTENT |
| RP-11 | L4 | Faits ajoutés au Rule Engine (compte de factures soldées, paiements annulés, tendance, non-alloué, jours depuis la dernière action) : formules entières ; refresh_events définitifs. | O6 | RPC:RP8 RPC:RP7 |
| RP-12 | L3 | Rétention des runs de trésorerie : 13 mois, dernier run mensuel des horizons 30 et 90 jours conservé ; archive, jamais suppression. | O4 | RPC:RP12 RPC:RP2 · INV:D8 |
| RP-13 | L1 | Modèles versionnés et sans paramètre d’organisation (hors montant critique) ; `risk_level` est un indicateur d’attention, jamais une probabilité ; aucune donnée inventée. | O1 | RPC:PD RPC:PH RPC:PG |
| RP-14 | L4 | Erreurs des moteurs de projection : modèle inconnu, concurrence rejouée. | O2 | ERR:RISK_MODEL_UNKNOWN ERR:PRIORITY_MODEL_UNKNOWN ERR:CASHFLOW_MODEL_UNKNOWN ERR:ENGINE_INTERNAL_ERROR |
| RP-15 | L1 | Principes de projection : fonction pure des sources ; un seul sens de dépendance ; convergence par événements `RESULT`. | O4-G17 | RPC:PC RPC:PE RPC:PF |

### H. Sécurité, tenant, données personnelles, audit

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| SE-01 | L3 | Tenant : chaque cas d’usage et chaque contrat appelé avec un sujet d’une autre organisation → `NOT_FOUND` (jamais 403), aucune ligne lue ; deux organisations simultanées ne se voient jamais. | O4-G01 | INV:C2 · ENG:X11 · ERR:INSUFFICIENT_ROLE |
| SE-02 | L3 | Verrou optimiste : deux modifications de la même version → `CONCURRENT_MODIFICATION` ; rejeu par le client ; `SERIALIZATION_FAILURE` rejoué de façon bornée. | O6 | INV:C4 · ENG:EC10 · ERR:SERIALIZATION_FAILURE |
| SE-03 | L3 | Clés d’idempotence : même clé et même contenu → première réponse ; contenu différent → `IDEMPOTENCY_KEY_REUSED`. | O4-G09 | INV:C6 · ERR:IDEMPOTENCY_KEY_REUSED · TAB:idempotency_keys |
| SE-04 | L3 | Organisation non active : aucune automatisation ni communication (`ORG_NOT_ACTIVE`) ; réactivation : reprise. | O2 | INV:C7 · ERR:ORG_NOT_ACTIVE |
| SE-05 | L3 | Corrections : une donnée financière immuable ne se corrige que par annulation + nouvelle saisie (paiement mal saisi, facture erronée). | O4-G06 | INV:C8 |
| SE-06 | L3 | Anonymisation : nom, téléphone, e-mail, textes libres, payloads de notification et `audit_logs.before/after` nettoyés ; **aucune colonne financière, date ou état modifié** (vérifié par empreinte avant/après) ; ligne d’audit `PII_ANONYMIZED` sans donnée personnelle ; archives froides incluses. | O4-G23 | INV:D7 INV:C9 |
| SE-07 | L3 | Audit : commandes utilisateur ou automatisation, configuration, droits, suspensions, approbations, actions sensibles écrites dans la transaction ; transitions temporelles du Scheduler **absentes** de l’audit. | O4-G19 | INV:D3 INV:C13 |
| SE-08 | L3 | Rôles : approbation seulement `MANAGER`+ avec limite suffisante ; personne ne s’approuve soi-même si la politique l’exige ; au moins un `OWNER` actif ; activation réservée à `OWNER`/`ADMIN`. | O2 | INV:N13 · ERR:LAST_OWNER_REQUIRED |
| SE-09 | L3 | Erreurs d’objets financiers et d’import : chaque code produit par au moins un test avec sa classe et son indicateur de nouvelle tentative (voir porte ERR). | O2 | ERR ×14 |
| SE-10 | L3 | Erreurs de facture, client, organisation, promesse et suspension. | O2 | ERR ×26 |
| SE-11 | L3 | Erreurs de lot d’import. | O2 | ERR ×7 |
| SE-12 | L0 | Porte de couverture des erreurs : **chaque code de l’Annexe A** est produit par au moins un test qui vérifie sa classe HTTP et son indicateur de nouvelle tentative ; le registre est généré et vérifié en CI. | O5 | **ERR:\*** |
| SE-13 | L3 | Course de création dédupliquée (R-12) : violation de la contrainte **déclarée** → `REPLAY` de l’objet occupant relu dans l’unité de reprise ; occupant sorti de l’index avant la relecture → `DEDUP_REPLAY_UNAVAILABLE` (`CONFLICT`, retryable), rien d’écrit, clé de requête non consommée, Domain non rappelé ; autre contrainte : non traduite (R12-B, B11). | O6 | TD:19 · ERR:DEDUP_REPLAY_UNAVAILABLE |

### I. Jobs planifiés et temps

Contrat commun : idempotent par construction, verrou consultatif, isolation par organisation, fuseau de l’organisation, rattrapage borné.

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| JB-01 | L4 | Contrat commun des jobs : deux instances simultanées → une seule agit ; l’échec d’une organisation n’arrête pas les autres ; un job rejoué sans effet ; métriques de retard émises. | O4-G09 | ENG:EC-03 ENG:EC7 |
| JB-02 | L4 | Publication des événements : arriéré traité dans l’ordre d’`occurred_at` ; `FOR UPDATE SKIP LOCKED` ; publication idempotente. | O8 | JOB:OutboxPublisher |
| JB-03 | L4 | Cycle de vie des factures : transitions dues rattrapées après arrêt (sauts permis), une seule fois, dans le fuseau de l’organisation ; heure d’été ; changement de date locale. | O3 | JOB:InvoiceLifecycleScan · INV:C10 |
| JB-04 | L4 | Promesses rompues, expirations de suspension et d’approbation : gardes d’état, rattrapage. | O3 | JOB:PromiseBreachScan JOB:HoldExpiryScan JOB:ApprovalExpiryScan |
| JB-05 | L4 | Déclencheurs temporels : fenêtre `(dernier balayage, as_of]`, tolérance de 48 h, aucune double exécution. | O2 | JOB:TimeTriggerScanner |
| JB-06 | L4 | Workers d’exécution et d’actions : sondage, verrouillage, équité par organisation, plafond de concurrence, reprise des tâches bloquées. | O6 | JOB:ExecutionWorker JOB:ExecuteDueActions JOB:Reaper |
| JB-07 | L4 | Import : libérateur et exécuteur d’inscription (étalement, pause, reprise). | O4-G20 | JOB:ImportReleaser JOB:EnrollmentRunner |
| JB-08 | L4 | Trésorerie planifiée : 05:00 local par organisation, regroupement des demandes. | O1 | JOB:CashflowScheduler |
| JB-09 | L4 | Purges techniques : `idempotency_keys` expirées, `event_receipts` de plus de 90 jours ; aucune donnée métier purgée. | O4 | JOB:TechnicalPurge |

### J. Import historique

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| IM-01 | L5 | Séquence complète : import → validation → lot prêt → approbation → engagement → normalisation → événements des moteurs → libération → exécution contrôlée ; 5 000 factures ≠ 5 000 relances immédiates. | O2 | INV:N14 INV:D9 · SM:14 |
| IM-02 | L3 | Deux chemins de création : `CreateInvoice` produit toujours un `DRAFT` ; `ImportHistoricalInvoice` reconstruit l’état historique avec son historique ; aucun autre chemin ne crée une facture hors brouillon. | O4-G04 | INV:D9 |
| IM-03 | L3 | Normalisation tout ou rien : un échec ne laisse aucune donnée ; toutes les entités portent `import_batch_id` ; un lot engagé n’est jamais annulé ni supprimé ; le staging figé. | O4 | INV:N14 |

### K. Scénarios de bout en bout (horloge virtuelle)

Chaque scénario est rejoué avec **tous les vérificateurs globaux** (§4) exécutés à la fin et après chaque jour simulé.

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| E2E-01 | L5 | Cycle de vie complet d’une facture sans incident : émission, rappels, paiement, projections, trésorerie. | O4-G* | INV:D4 |
| E2E-02 | L5 | Paiement partiel puis solde, puis annulation du règlement : nouveau cycle, nouvelles relances, priorité et risque recalculés, trésorerie recalculée. | O4-G* | EVT:INVOICE_PARTIALLY_PAID EVT:INVOICE_SETTLEMENT_REVERTED EVT:PAYMENT_ALLOCATION_REVERSED EVT:PAYMENT_REVERSED |
| E2E-03 | L5 | Litige partiel puis résolu ; litige total ; procédure d’un litige fondé. | O4-G* | EVT:INVOICE_DISPUTED EVT:INVOICE_DISPUTE_RESOLVED EVT:INVOICE_VOIDED |
| E2E-04 | L5 | Promesse créée, tenue, rompue ; suspension des relances puis reprise ; effet sur le risque. | O4-G* | EVT:PROMISE_CREATED EVT:PROMISE_FULFILLED EVT:PROMISE_CANCELLED |
| E2E-05 | L5 | Suspension manuelle (`NEGOTIATION`, `LEGAL`) : pause, libération, expiration ; override refusé pour `LEGAL`. | O4-G* | EVT:COLLECTION_HOLD_PLACED EVT:COLLECTION_HOLD_RELEASED |
| E2E-06 | L5 | Client désactivé puis archivé en cours de recouvrement ; reversal qui rouvre une facture d’un client archivé (alerte, aucune relance, aucune réactivation automatique). | O4-G* | EVT:CUSTOMER_DEACTIVATED EVT:CUSTOMER_ARCHIVED EVT:CUSTOMER_REACTIVATED |
| E2E-07 | L5 | Approbation : accordée, refusée, expirée, cible payée pendant l’attente. | O4-G* | EVT:APPROVAL_REQUESTED EVT:APPROVAL_GRANTED EVT:APPROVAL_REJECTED |
| E2E-08 | L5 | Envoi : succès, erreur transitoire puis succès, erreurs épuisées, erreur permanente, repli humain, rebond. | O4-G* | EVT:NOTIFICATION_CREATED EVT:NOTIFICATION_SENT EVT:NOTIFICATION_FAILED EVT:COLLECTION_ACTION_FAILED EVT:COLLECTION_ACTION_SUPPRESSED |
| E2E-09 | L5 | Activation d’une automatisation sur 300 factures existantes : aperçu, empreinte, `FUTURE_ONLY` puis `LATEST_STEP`, aperçu périmé. | O4-G* | EVT:AUTOMATION_ACTIVATED EVT:AUTOMATION_EXECUTION_STARTED |
| E2E-10 | L5 | Import de 5 000 factures dont 1 200 en retard, puis libération étalée sur plusieurs jours, avec pause et reprise. | O4-G* | EVT:IMPORT_BATCH_UPLOADED EVT:IMPORT_BATCH_NORMALIZED EVT:IMPORT_BATCH_COMMITTED |
| E2E-11 | L5 | Automatisation mise en pause, désactivée, réactivée ; changement de version pendant des exécutions en vol ; retour arrière par nouvelle version. | O4-G* | EVT:AUTOMATION_PAUSED EVT:AUTOMATION_DISABLED EVT:AUTOMATION_EXECUTION_COMPLETED EVT:AUTOMATION_EXECUTION_CANCELLED |
| E2E-12 | L5 | Panne du balayeur 30 h et 5 jours ; panne de worker au milieu d’une étape ; événements dupliqués, perdus, en désordre ; `DEAD` puis rejeu. | O4-G* | EVT:INVOICE_DUE_SOON EVT:INVOICE_DUE |
| E2E-13 | L5 | Paiement non alloué : trésorerie (réserve FIFO), signal de rapprochement, allocation ultérieure ; aucune double prévision à aucun moment. | O4-G18 | EVT:PAYMENT_CREATED |
| E2E-14 | L5 | Cascade de projections : `INVOICE_OVERDUE` → risque → `RISK_CHANGED` → priorité par lots → `PRIORITY_CHANGED` → automatisations sensibles ; barrière de fraîcheur ; hystérésis. | O4-G17 |  |
| E2E-15 | L5 | Deux organisations en parallèle, mêmes numéros de facture et mêmes codes clients : aucune interférence, aucune fuite ; suspension de l’une sans effet sur l’autre. | O4-G01 | EVT:ORGANIZATION_SUSPENDED EVT:ORGANIZATION_REACTIVATED |
| E2E-16 | L5 | Anonymisation d’un contact et d’un client personne physique en plein recouvrement ; partition d’audit archivée. | O4-G23 | EVT:CUSTOMER_CONTACT_UPDATED |
| E2E-17 | L5 | Cycle de vie de l’organisation : création atomique (réglages, `OWNER`, abonnement d’essai, automatisations modèles en `DRAFT`), modification des réglages, création et modification de clients, abonnement expiré, membre retiré, dernier `OWNER` protégé, changement de plan. | O4-G* | EVT:SUBSCRIPTION_CHANGED EVT:ORGANIZATION_CREATED EVT:ORGANIZATION_UPDATED EVT:ORG_SETTINGS_CHANGED EVT:CUSTOMER_CREATED EVT:CUSTOMER_UPDATED |
| E2E-18 | L5 | Facture émise en retard, impayée : rattrapage immédiat, exécution, niveau plancher 3, escalade. | O4-G* | EVT:INVOICE_CREATED EVT:INVOICE_DUE |
| E2E-19 | L5 | Facture annulée avant émission (`CANCELLED`) et facture annulée après émission (`VOID`) ; effets sur promesses, actions, exécutions ; actions proposées, planifiées puis annulées. | O4-G* | EVT:INVOICE_CANCELLED EVT:COLLECTION_ACTION_PROPOSED EVT:COLLECTION_ACTION_SCHEDULED EVT:COLLECTION_ACTION_CANCELLED |
| E2E-20 | L5 | Scénarios courts complémentaires qui produisent les événements du catalogue non déclenchés plus haut : création d’une automatisation et de ses versions, archivage, exécution échouée, lot d’import prêt, approuvé, en échec ou annulé, clôture d’une organisation, ajout d’un contact, demandes de recalcul regroupées. | O4-G* | EVT ×19 |

### L. Chaos et résilience

Injection de fautes dans le harnais (§3) ; les vérificateurs globaux doivent rester verts.

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| CH-01 | L6 | Événements dupliqués (1 à 5 fois), perdus (échantillon), retardés, réordonnés ; état final identique à la livraison parfaite après reprise. | O8 | ENG:X6 ENG:X14 |
| CH-02 | L6 | Panne du processus entre chaque instruction d’un cas d’usage (transaction avortée) : tout ou rien, aucun événement orphelin. | O4-G07 | INV:C5 · ENG:X8 |
| CH-03 | L6 | Fournisseur d’envoi : délai dépassé, réponse perdue après acceptation, rapport de livraison en double. | O4-G13 | ENG:EC-04 |
| CH-04 | L6 | Concurrence : deux allocations, deux réclamations de tâche, deux activations, deux promotions de run, deux recalculs du même client, verrous dans l’ordre global (aucun interblocage). | O4-G22 | ENG:EC5 ENG:EC-05 |
| CH-05 | L6 | Base : échec de sérialisation, perte de connexion en milieu de lot, partition manquante. | O4 | ENG:EC10 |
| CH-06 | L6 | Horloge : décalage entre serveurs, saut d’heure d’été, passage de minuit dans un fuseau ; aucune lecture d’horloge hors `Clock`. | O4-G24 | ENG:EC3 |
| CH-07 | L6 | Charge : rafale de 10 000 événements pour une organisation pendant qu’une autre s’exécute ; équité, aucun effet sur l’autre. | O4 | JOB:ExecutionWorker |

### M. Performance et volumétrie

Les seuils chiffrés sont fixés au banc d’essai de l’architecture technique ; la matrice impose **les scénarios et les mesures**.

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| PF-01 | L7 | Évaluation par lots : 5 000 factures évaluées par le Rule Engine ; nombre de requêtes par famille de faits (jamais une par facture) ; durée. | O6 | RULE:P6 |
| PF-02 | L7 | Recalcul complet : 5 000 clients et 50 000 factures (risque, priorité) ; un client à 50 000 factures ouvertes ; taille et retard des lots. | O1 | RPC:RP21 |
| PF-03 | L7 | Run de trésorerie et faits sur 12 mois glissants : index, plan d’exécution, durée. | O1 | RPC:RP5 |
| PF-04 | L7 | Débit de l’outbox et des handlers ; retard de publication ; volume des partitions. | O4 | JOB:OutboxPublisher |
| PF-05 | L7 | File de travail des collecteurs sur 50 000 éléments (tri total, pagination). | O6 | RPC:RP4 |

### N. Architecture et contrats d’interface

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| AR-04 | L0 | **Exceptions à « un agrégat par transaction »** : analyse statique et journal des transactions : seules `AllocatePayment`, `ReverseAllocation`, `ReversePayment` et `NormalizeImportBatch` écrivent dans plusieurs agrégats (`CreateOrganization` n’en fait plus partie : TD59) ; toute autre écriture inter-agrégats passe par un événement. | O4 | INV:C12 · ENG:EC1 |
| AR-01 | L0 | **Tests d’architecture** : règles DR1 à DR9 exprimées comme règles d’import ; le Domain n’importe ni Django, ni Redis, ni un fournisseur ; aucun module ne lit les tables d’un autre ; aucun appel ascendant ; aucun cycle ; une violation bloque la fusion. | O4 | ENG ×10 · INV:C1 |
| AR-02 | L4 | Contrats d’interface EC-05 à EC-13 : chaque contrat testé sur entrée, sortie, préconditions, erreurs, idempotence, transaction, événements (tests pilotés par les consommateurs). | O5 | ENG ×8 |
| AR-03 | L0 | Invariants inter-moteurs X1 à X14 : chacun vérifié par au moins un vérificateur global ou une règle d’architecture. | O4 | ENG:X2 ENG:X4 ENG:X5 ENG:X3 |

### O. Rapprochement : paiement non alloué et barrière de recouvrement (Collection V1.2)

La barrière ne présume rien : elle suspend les factures candidates pendant une fenêtre bornée. Ces tests s’appuient sur `reconciliation_state` du modèle de référence et sur les cas d’or `R1` à `R10`.

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| RC-01 | L1 | Qualification Q1 à Q5 : paiement candidat, antérieur à l’émission, alloué, annulé, partiel (reliquat), jour férié dans la fenêtre, deux paiements, autre devise, facture fermée, paiement enregistré tard. | O1, O2 | GOLD ×10 · RCN:RN2 RCN:RN11 |
| RC-02 | L1 | Calendrier et fuseau (W1 à W7) : jours ouvrés, jours fériés ; départ = date **locale** d’enregistrement (pas la date UTC, pas la date de valeur : R11, R12) ; barrière active jusqu’à la fin du dernier jour local et périmée dès le jour local suivant (R13) ; changement d’heure (R14) ; résultat identique pour toute minute d’une journée locale ; le dernier jour de suspension est toujours un jour ouvré ; la barrière ne revient pas avec le seul temps. | O7 | RCN:RN5 RCN:RN12 · GOLD:R11 GOLD:R12 GOLD:R13 GOLD:R14 |
| RC-03 | L1 | Exception n° 13 `RECONCILIATION_PENDING` : suspension automatique ; action manuelle avec `OverrideGrant` `COLLECTOR` ; **jamais** contournable par une automatisation ; ordre avec `PAID` et `HOLD_ACTIVE` ; notifications internes exemptées ; fenêtre écoulée → `PROCEED` avec `reconciliation_stale` ; **grant revérifié à l’exécution** (G4 à G6) : acteur désactivé, rôle rétrogradé, organisation suspendue, hold `LEGAL` apparu, autre exception apparue. | O2 | RCN:RN3 RCN:RN4 · RPC:RP23 |
| RC-04 | L4 | **Aucune présomption** : deux factures (100 000 et 500 000) et un paiement de 100 000 non alloué : **les deux** sont suspendues ; après allocation complète à l’une, l’autre est levée ; jamais de choix implicite. | O2 | RCN:RN1 RCN:RN2 |
| RC-05 | L4 | États d’action : `SCHEDULED` suspendue à l’exécution ; `PENDING_APPROVAL` → `SUPPRESSED` ; `EXECUTING` non interrompue ; `DONE` inchangée ; clé de déduplication libérée puis nouvelle action créée à la levée. | O3 | RCN:RN4 RCN:RN10 |
| RC-06 | L4 | Exécutions : `PAUSED` (`RECONCILIATION_PENDING`) à la revalidation ; reprise sur `PAYMENT_ALLOCATED`, `PAYMENT_REVERSED` et fin de fenêtre ; reste en pause si un second paiement qualifie ; exécution `WAITING` évaluée seulement à son réveil ; **une automatisation ne crée ni ne consomme jamais de grant** (G7). | O2 | RCN:RN6 |
| RC-07 | L4 | Évolution : allocation partielle (barrière sur le reliquat), complète, allocation annulée (la barrière peut réapparaître), paiement annulé, nouveau paiement, deux paiements aux fenêtres différentes. | O2 | RCN:RN6 RCN:RN2 |
| RC-08 | L4 | Job `ReconciliationWindowScan` : revue à +1 jour ouvré, alerte en fin de fenêtre, idempotence (notifications dédupliquées par paiement et par membre), rattrapage après un arrêt, isolation par organisation ; **même résultat quelle que soit l’heure du passage** (00:05 ou 23:55, W6). | O4-G09 | RCN:RN7 RCN:RN5 · JOB:ReconciliationWindowScan |
| RC-09 | L3 | Auditabilité : `decision_snapshot` avec le bloc `reconciliation` (identifiants, montants, dates, sans donnée personnelle) ; audit d’un contournement manuel à la création **et** à chaque vérification à l’exécution (`decision_snapshot` immuable) ; aucune donnée personnelle dans les notifications de revue. | O4-G16 | RCN:RN9 |
| RC-10 | L4 | Signal de Priority aligné sur le fait `invoice.reconciliation_pending` ; aucun effet sur score ni niveau ; hash modifié ; bascule à la fin de la fenêtre par le rafraîchissement quotidien. | O1 | RCN:RN8 |
| RC-11 | L5 | Bout en bout : paiement le lundi, rappel prévu le mardi (suspendu), allocation le mercredi (reprise, nouveau rappel) ; cas sans rapprochement : fenêtre écoulée le vendredi, relance et alerte aux managers ; paiement importé historique sans barrière. | O4-G* | RCN:RN5 RCN:RN11 |
| RC-12 | L6 | Propriétés du modèle de référence (pas de présomption, montant en attente ≤ non alloué, fenêtre bornée) et test différentiel du fait SQL contre `reconciliation_state` sur données aléatoires. | O6 | RCN:RN1 RCN:RN12 |

### P. Réservé : abonnement et autorisations (Billing)

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| BL-01 | L4 | **(À spécifier avec le module Billing)** Lien entre l’état de l’abonnement (`PAST_DUE`, `EXPIRED`, `CANCELLED`) et les autorisations : automatisations, communications, création de données. | O2 | SM:S7 |

### Q. Architecture technique (TD1 à TD59, registres, PostgreSQL réel)

Famille **générée** depuis `TECHNICAL_ARCHITECTURE_V1.md` (tableau « Nouvelle famille TA ») : les décisions `TD`, les invariants `TI` et les règles `AR` de l’architecture technique sont des éléments de l’univers, couverts comme les autres. Les portes `AR-*` sont produites par `architecture_registry/build_registry.py` ; les expériences PostgreSQL par `pg_experiments.py`.

| ID | Niv. | Ce que le test prouve | Oracle | Couvre |
|---|---|---|---|---|
| TA-01 | L0 | règles `AR-01` à `AR-05`, `AR-09` à `AR-13`, `AR-17`, `AR-19`, `AR-20` : analyse d'imports, d'appels et de modèles ; un service de requête ne lit que les tables de son module ; `rules` n'importe aucun module ; `events` n'importe aucun producteur ; l'administration est en lecture seule ; chaque port a un double | O5 | TD ×11 · TI:1 TI:3 TI:16 |
| TA-02 | L0 | `AR-02` : suite complète avec l'**horloge virtuelle** réglée à une date absurde et l'heure système gelée ; **aucune colonne temporelle écrite ne coïncide avec l'heure réelle** (le `DEFAULT now()` n'est jamais utilisé) ; les cas d'or de fuseau (`R11` à `R14`) passent avec la version de `tzdata` figée dans l'image | O5 | TD:23 TD:24 · TI:1 TI:17 |
| TA-03 | L1 | `AR-06` et `AR-07` : espion sur `rules.evaluate`, absence d'écriture directe d'action | O5 | TD:6 |
| TA-04 | L2 | `AR-14` : catalogue PostgreSQL ↔ contrat ; contraintes nommées ; T14 généré = T14 réel ; noms de tables et de contraintes du contrat, schéma `verqia`, schéma `public` vide | O9 | TD:8 TD:15 TD:16 |
| TA-05 | L2 | `AR-18` et RLS : sans organisation posée, aucune ligne ; rôle non propriétaire ; aucune politique manquante ; **relais** : lecture de `events` seule, autre table refusée | O9 | TD:17 TD:18 · TI:2 TI:11 |
| TA-06 | L2 | privilèges de chaque rôle : `DELETE`, `TRUNCATE`, `UPDATE` sur LOG refusés à `verqia_app` ; colonnes de `verqia_relay` et `verqia_privacy` | O9 | TD:18 |
| TA-07 | L2 | deux organisations : requête sans filtre → uniquement l'organisation courante ; écriture vers une autre organisation refusée par FK composite **et** RLS ; **la suite métier complète, exécutée avec RLS désactivée, donne les mêmes résultats** (RLS est un filet, pas un chemin) ; un gestionnaire d'ORM sans organisation lève `TENANT_CONTEXT_MISSING` avant la base | O9 | TD:17 · TI:18 · ERR:TENANT_CONTEXT_MISSING |
| TA-08 | L2 | traduction d'erreurs : chaque contrainte nommée produit le code attendu, y compris les erreurs levées **au COMMIT** | O9 | TD:19 · TI:13 · ERR:DB_INVARIANT_VIOLATED |
| TA-09 | L2 | migrations : base vide → dernière version ; ordre du §2.4 ; *expand* compatible avec le code N ; index concurrents | O9 | AR:13 · TD:20 |
| TA-10 | L2 | partitions : élagage ; recherche par identifiant UUIDv7 à la frontière de mois ; partition par défaut vide | O9 | TD:22 |
| TA-11 | L3 | `TransactionManager` : organisation posée, délais, `as_of` unique par unité de travail ; `on_commit` ne porte pas d'effet ; aucun verrou de session, `LISTEN/NOTIFY` ni table temporaire ; exécution derrière un pooler en mode transaction | O5 | TD:21 TD:23 TD:26 |
| TA-12 | L3 | échelle de verrous **générée** depuis le registre ; acquisition descendante refusée ; cas `H1` à `H3` ; **exécuté sur PostgreSQL réel** : 10 expériences (`pg_experiments.py`, `test_pg_locks.py`) : modes de verrou et clés étrangères, colonnes d'index partiel, interblocage, instantané après verrou consultatif, `UPDATE` gardé, `INSERT` en attente, `SKIP LOCKED`, RLS (fail-closed, réglage local, clés étrangères) ; **à rejouer sur la version cible** (16.2 embarqué sous Windows ici) | O5 | TD:17 TD:27 TD:29 · TI:4 · ERR:LOCK_ORDER_VIOLATION |
| TA-13 | L3 | concurrence : `H1` à `H4`, `H6`, `H9` avec deux et dix travailleurs | O5 | TD:28 TD:31 |
| TA-14 | L3 | verrou de sujet en première instruction : calcul ancien ne peut écraser un calcul récent (`H8`, `CX18`) | O5 | TD:29 · TI:9 |
| TA-15 | L3 | nouvelle tentative sur `40001` / `40P01` : bornée, sans effet externe déjà produit | O5 | TD:30 |
| TA-16 | L3 | idempotence d'API : même clé même contenu (rejeu), contenu différent (`IDEMPOTENCY_KEY_REUSED`), concurrence de deux requêtes | O5 | TD:32 · TI:14 |
| TA-17 | L3 | réclamer-valider-agir : panne entre chaque étape de `ExecuteDueAction` ; garde d'envoi dans une transaction ; **un claim sans revalidation validée ne mène jamais à `EXECUTING`** (litige, promesse, hold, rapprochement ou grant révoqué apparus entre la planification et le claim) ; étape d'automatisation en trois transactions | O5 | TD:31 TD:52 · TI:5 TI:19 |
| TA-18 | L4 | outbox : tout événement produit dans la transaction ; annulation de transaction → aucun événement | O5 | TD:33 · TI:6 |
| TA-19 | L4 | bail du relais : relais tué en plein traitement ; reprise ; handlers déjà servis : `REPLAY` ; **publication indépendante du succès des handlers** ; l'outbox se vide par sondage seul, sans aucun indice de réveil | O5 | TD:33 TD:34 · TI:7 |
| TA-20 | L4 | un handler en échec : reçu `RETRYING`, reprise `10 s … 2 h`, puis `DEAD` ; **les autres handlers de l'événement ne sont ni retardés ni rejoués** ; `ReplayDeadEvent` | O5 | TD:35 · TI:7 |
| TA-21 | L4 | désordre : v6 avant v5, doublons, événement retardé : même état final | O5 | TD:36 · TI:10 |
| TA-22 | L4 | réserves : un calcul de trésorerie long n'occupe pas les emplacements de `fanout` ; la suspension après litige reste dans l'objectif | O5 | TD:37 |
| TA-23 | L4 | regroupement : 5 000 `REQUEST` d'un client → un calcul, reçus `PROCESSED` et `SKIPPED` | O5 | TD:38 |
| TA-24 | L4 | équité : deux organisations, l'une inonde l'outbox ; l'autre garde sa latence | O5 | TD:39 |
| TA-25 | L4 | planificateur : deux exemplaires, exécution unique ; arrêt de six heures, rattrapage ; **même résultat à 00:05 et 23:55** ; l'échéance se calcule sans base ni processus (fonction pure) ; un échec d'organisation n'arrête pas les autres | O5 | TD:41 TD:43 TD:44 TD:45 · TI:12 |
| TA-26 | L4 | `ReconciliationWindowScan` en deux cas d'usage (`collection` puis `automation`), deux transactions | O5 | TD:46 |
| TA-27 | L4 | arrêt propre : SIGTERM en plein traitement ; aucun travail perdu ni doublé | O5 | TD:47 |
| TA-28 | L5 | e-mail : envoi hors transaction, réponse perdue, doublon documenté | O5 | TD:31 |
| TA-29 | L5 | restauration à un instant : envois suspendus jusqu'à réconciliation | O5 | TI:15 |
| TA-30 | L6 | **Redis vidé** pendant un scénario de plusieurs jours : mêmes états finaux, mêmes vérificateurs globaux ; indices perdus retardent seulement ; seuls la limitation d'API et l'étranglement d'envoi utilisent Redis ; aucune valeur d'un délai ne s'y trouve | O5 | TD:42 TD:48 TD:49 TD:50 · TI:8 |
| TA-31 | L6 | chaos : pannes de processus entre instructions, échecs de sérialisation, partitions absentes | O5 | TD:25 TD:30 |
| TA-32 | L6 | différentiel : verrous et allocations concurrentes contre une exécution séquentielle | O5 | TD:28 |
| TA-33 | L7 | banc (§12.2) | O5 | TD:53 |
| TA-34 | L0 | **injection de violation** : pour chaque règle `AR-*`, une violation volontaire dans un module d'essai **fait échouer la porte** ; une règle jamais vue échouer n'est pas prouvée | O5 | AR ×20 · TD:54 |
| TA-35 | L0 | **registres** : `build_registry.py --check` sans erreur ; **36 tests d injection** : cycle de verrous, écriture hors propriétaire, C12 hors liste, appel inter-modules dans la même transaction, travail de composition hors `own:`, événement sans producteur / sans classement / classé C / contractuel non catalogué, destinataire `REQUEST` multiple, dépendance non déclarée, cycle d'appels, cycle de schéma, table sans propriétaire, dérive des listes de rafraîchissement ; `--freeze` tant qu'un nom est provisoire ; tables ↔ modules (22 unités), `approvals` module propriétaire, schémas d'événements (AR-15), fiche complète de chaque module, événements catalogués ou classés | O5 | TD ×7 · TI:20 TI:22 · EVT:USER_CREATED EVT:USER_STATUS_CHANGED EVT:MEMBER_ADDED EVT:MEMBER_ROLE_CHANGED EVT:MEMBER_REMOVED |
| TA-36 | L4 | **plan de provisioning** : `CreateOrganization` écrit `PROVISIONING` ; chaque étape (`identity`, `billing`, `automation`) est idempotente par `(organisation, étape)` ; panne entre deux étapes puis `ResumeProvisioning` ; une organisation `PROVISIONING` refuse toute commande métier ; `CompleteProvisioning` émet `ORGANIZATION_CREATED` une seule fois ; `organizations` n'importe ni `billing` ni `automation` | O5 | TD:58 TD:59 · TI:21 · SM:S10 |
| TA-37 | L4 | **composition orchestrée** : action `PROPOSED` → approbation → `PENDING_APPROVAL` avec panne entre chaque temps et reprise par `ResumeProposedActions` ; `ExecuteDueAction` : claim, notification (transaction de `notifications`), envoi, résultat, panne entre chaque temps ; aucune écriture inter-modules dans une même transaction hors exceptions C12 ; expiration d'une approbation par le port `ApprovalTargetReader` | O5 | TD:31 TD:58 · TI:21 |

## 6. Ordonnancement en intégration continue

| Étape | Contenu | Déclencheur |
|---|---|---|
| 1. Statique | L0 : architecture, contrat ↔ schéma, registres, portes de couverture, `build_matrix.py --check` | chaque commit |
| 2. Rapide | L1 (Domain pur) et `reference_model` | chaque commit |
| 3. Base | L2 (PostgreSQL) et L3 | chaque demande de fusion |
| 4. Flux | L4 et scénarios L5 courts (un à sept jours simulés) | chaque demande de fusion |
| 5. Complet | L5 longs, L6 (propriétés, différentiel, chaos avec plusieurs graines) | chaque nuit |
| 6. Mesure | L7 (banc d’essai) | avant chaque version, et sur alerte |

## 7. Traçabilité : couverture vérifiée

Univers extrait des documents figés par `universe.py`. « Explicite » : le jeton figure dans un test (ou son code figure dans le texte du test) ; « porte » : couvert uniquement par une porte de couverture de niveau L0 ; « sans test » : **doit être nul**.

| Famille | Sens | Éléments | Explicite | Porte seule | Sans test |
|---|---|---:|---:|---:|---:|
| `CON` | contraintes T1–T15 | 15 | 15 | 0 | 0 |
| `TAB` | tables | 41 | 41 | 0 | 0 |
| `OUT` | issues d’action | 12 | 12 | 0 | 0 |
| `RSN` | causes de pause / annulation | 13 | 13 | 0 | 0 |
| `INV` | règles communes, décisions D et N | 36 | 36 | 0 | 0 |
| `SM` | machines à états et décisions S | 26 | 26 | 0 | 0 |
| `SMX` | cascades entre machines | 17 | 17 | 0 | 0 |
| `RULE` | décisions et principes du Rule Engine | 23 | 23 | 0 | 0 |
| `EXC` | garde-fous | 13 | 13 | 0 | 0 |
| `RE` | scénarios d’or du Rule Engine | 52 | 52 | 0 | 0 |
| `COL` | décisions et principes du Collection Engine | 20 | 20 | 0 | 0 |
| `AUT` | décisions et principes de l’Automation Engine | 20 | 20 | 0 | 0 |
| `ENG` | décisions, contrats, invariants, règles de dépendance | 55 | 54 | 0 | 0 |
| `JOB` | jobs planifiés | 17 | 17 | 0 | 0 |
| `ERR` | codes d’erreur | 110 | 104 | 6 | 0 |
| `RPC` | décisions, principes, règles de conservation | 37 | 37 | 0 | 0 |
| `GOLD` | cas d’or chiffrés | 36 | 36 | 0 | 0 |
| `RCN` | décisions de Collection V1.2 (rapprochement) | 12 | 12 | 0 | 0 |
| `TD` |  | 59 | 59 | 0 | 0 |
| `TI` |  | 22 | 22 | 0 | 0 |
| `AR` |  | 20 | 20 | 0 | 0 |
| `EVT` | types d’événement | 77 | 77 | 0 | 0 |
| **Total** | | **733** | **726** | **6** | **0** |

**Tests définis : 216.** Identifiants dupliqués : 0. Jetons inconnus : 0.

**Éléments exemptés** (non testables, justifiés) : `ENG:P5` — décision d’ordre des passes de conception (Risk / Priority / Cashflow avant la matrice) : non testable.

## 8. Points ouverts

| # | Point | Traitement |
|---|---|---|
| M1 | **Barrière de recouvrement du non-alloué (RP23)** : la famille O est écrite d’après Collection Engine V1.2 (proposition) ; elle devient définitive à la validation de V1.2 | vérifier l’alignement après validation |
| M2 | Seuils de performance chiffrés | fixés au banc d’essai de l’architecture technique |
| M3 | Implémentation du harnais (§3) | architecture technique |
| M4 | Couverture **explicite** des codes d’erreur et des événements : certains ne sont couverts que par la porte L0 | à réduire à mesure que les scénarios sont écrits ; l’Annexe C liste les éléments concernés |

## Annexe A · Univers

- `CON` (15) : T1, T2, T3, T4, T5, T6, T7, T8, T9, T10, T11, T12, T13, T14, T15
- `TAB` (41) : voir Annexe C
- `OUT` (12) : SENT, BOUNCED, CONTACTED, NO_ANSWER, PROMISE_OBTAINED, DISPUTE_RAISED, REFUSED, WRONG_CONTACT, OTHER, USER_CANCELLED, APPROVAL_REJECTED, APPROVAL_EXPIRED
- `RSN` (13) : USER, AUTOMATION_PAUSED, AUTOMATION_DISABLED, DISPUTED, PROMISE_ACTIVE, HOLD_ACTIVE, CUSTOMER_INACTIVE, CUSTOMER_ARCHIVED, ORG_INACTIVE, IMPORT_HELD, RECONCILIATION_PENDING, SUBJECT_PAID, SUBJECT_VOIDED
- `INV` (36) : C1, C2, C3, C4, C5, C6, C7, C8, C9, C10, C11, C12, C13, D1, D2, D3, D4, D5, D6, D7, D9, N1, N6, N7, N11, N12, N13, N14, N2, N3, N4, N5, N8, N9, N10, D8
- `SM` (26) : 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, S1, S2, S3, S4, S5, S6, S7, S10, S8, S9, S11
- `SMX` (17) : 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17
- `RULE` (23) : R1, R2, R3, R4, R5, R6, R7, R8, R14, R9, R10, R13, R15, R16, R11, R12, P1, P2, P3, P4, P5, P6, P7
- `EXC` (13) : ORG_INACTIVE, CUSTOMER_ARCHIVED, CUSTOMER_INACTIVE, VOIDED, PAID, DISPUTED, PROMISE_ACTIVE, HOLD_ACTIVE, IMPORT_HELD, FREQUENCY_LIMIT, NO_CONTACT, NO_CONSENT, RECONCILIATION_PENDING
- `RE` (52) : 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52
- `COL` (20) : C1, C2, C3, C4, C5, C6, C7, C8, C9, C10, C11, C12, C13, CP1, CP2, CP3, CP4, CP5, CP6, CP7
- `AUT` (20) : AU1, AU2, AU3, AU4, AU5, AU6, AU7, AU8, AU9, AU10, AU11, AU12, AP1, AP2, AP3, AP4, AP5, AP6, AP7, AP8
- `ENG` (55) : EC1, EC2, EC3, EC4, EC5, EC6, EC7, EC8, EC9, EC10, P1, P2, P3, P4, P5, EC-01, EC-02, EC-03, EC-04, EC-05, EC-06, EC-07, EC-08, EC-09, EC-10, EC-11, EC-12, EC-13, EC-14, X1, X2, X3, X4, X5, X6, X7, X8, X9, X10, X11, X12, X13, X14, X15, X16, X17, DR1, DR2, DR3, DR4, DR5, DR6, DR7, DR8, DR9
- `JOB` (17) : OutboxPublisher, InvoiceLifecycleScan, PromiseBreachScan, HoldExpiryScan, ApprovalExpiryScan, TimeTriggerScanner, ExecutionWorker, ExecuteDueActions, Reaper, ImportReleaser, EnrollmentRunner, ProjectionDailyRefresh, ProjectionSafetyNet, ReconciliationWindowScan, CashflowScheduler, PartitionManager, TechnicalPurge
- `ERR` (110) : voir Annexe C
- `RPC` (37) : RP1, RP2, RP3, RP4, RP5, RP6, RP7, RP8, RP9, RP10, RP11, RP12, RP13, RP14, RP15, RP16, RP17, RP18, RP19, RP20, RP21, RP22, RP23, PA, PB, PC, PD, PE, PF, PG, PH, CF1, CF2, CF3, CF4, CF5, CF6
- `GOLD` (36) : G1, G2, G3, G4, G5, P1, P2, P3, P4, P5, P6, P7, C1, C10, C2, C3, C4, C5, C6, C7, C8, C9, R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R14
- `RCN` (12) : RN1, RN2, RN3, RN4, RN5, RN6, RN7, RN8, RN9, RN10, RN11, RN12
- `TD` (59) : 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59
- `TI` (22) : 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22
- `AR` (20) : 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20
- `EVT` (77) : voir Annexe C

## Annexe B · Tests par jeton (traçabilité inverse)

| Jeton | Tests |
|---|---|
| `CON:T1` | DB-01 |
| `CON:T2` | DB-01 |
| `CON:T3` | DB-01 |
| `CON:T4` | DB-02 |
| `CON:T5` | DB-02 |
| `CON:T6` | DB-03 |
| `CON:T7` | DB-04 |
| `CON:T8` | DB-05 |
| `CON:T9` | DB-04 |
| `CON:T10` | DB-03 |
| `CON:T11` | DB-06 |
| `CON:T12` | DB-06 |
| `CON:T13` | DB-07 |
| `CON:T14` | DB-08 |
| `CON:T15` | DB-09 |
| `OUT:SENT` | CO-09 |
| `OUT:BOUNCED` | CO-09 |
| `OUT:CONTACTED` | CO-08 |
| `OUT:NO_ANSWER` | CO-08 |
| `OUT:PROMISE_OBTAINED` | CO-08 |
| `OUT:DISPUTE_RAISED` | CO-08 |
| `OUT:REFUSED` | CO-08 |
| `OUT:WRONG_CONTACT` | CO-08 |
| `OUT:OTHER` | CO-08 |
| `OUT:USER_CANCELLED` | CO-09 |
| `OUT:APPROVAL_REJECTED` | CO-09 |
| `OUT:APPROVAL_EXPIRED` | CO-09 |
| `RSN:USER` | SM-09 |
| `RSN:AUTOMATION_PAUSED` | SM-09 |
| `RSN:AUTOMATION_DISABLED` | SM-09 |
| `RSN:DISPUTED` | SM-09 |
| `RSN:PROMISE_ACTIVE` | SM-09 |
| `RSN:HOLD_ACTIVE` | SM-09 |
| `RSN:CUSTOMER_INACTIVE` | SM-01 |
| `RSN:CUSTOMER_ARCHIVED` | SM-01 |
| `RSN:ORG_INACTIVE` | SM-01 |
| `RSN:IMPORT_HELD` | SM-09 |
| `RSN:RECONCILIATION_PENDING` | SM-09 |
| `RSN:SUBJECT_PAID` | SM-09 |
| `RSN:SUBJECT_VOIDED` | SM-09 |
| `INV:C1` | AR-01 |
| `INV:C2` | DB-10, DB-16, SE-01 |
| `INV:C3` | DB-08, SM-02, SM-14 |
| `INV:C4` | SE-02, SM-14 |
| `INV:C5` | CH-02, EV-01, EV-07 |
| `INV:C6` | EV-03, EV-09, SE-03 |
| `INV:C7` | SE-04 |
| `INV:C8` | SE-05 |
| `INV:C9` | EV-02, SE-06 |
| `INV:C10` | JB-03, RE-08, SM-05 |
| `INV:C11` | EV-03 |
| `INV:C12` | AR-04 |
| `INV:C13` | SE-07 |
| `INV:D1` | SM-04 |
| `INV:D2` | AT-02 |
| `INV:D3` | SE-07 |
| `INV:D4` | E2E-01 |
| `INV:D5` | CO-16 |
| `INV:D6` | SM-01, SM-15 |
| `INV:D7` | DB-05, SE-06 |
| `INV:D9` | IM-01, IM-02 |
| `INV:N1` | DB-07, SM-02 |
| `INV:N6` | SM-06 |
| `INV:N7` | RE-12 |
| `INV:N11` | SM-06 |
| `INV:N12` | SM-03 |
| `INV:N13` | AT-09, SE-08 |
| `INV:N14` | AT-11, IM-01, IM-03 |
| `INV:N2` | SM-05 |
| `INV:N3` | SM-01, SM-15 |
| `INV:N4` | CO-05 |
| `INV:N5` | SM-06 |
| `INV:N8` | CO-06 |
| `INV:N9` | EV-07 |
| `INV:N10` | EV-03 |
| `INV:D8` | DB-15, RP-12 |
| `SM:1` | DB-08, SM-01 |
| `SM:2` | DB-08, SM-01 |
| `SM:3` | DB-08, SM-02 |
| `SM:4` | SM-03 |
| `SM:5` | DB-08, SM-04 |
| `SM:6` | DB-08, SM-05 |
| `SM:7` | DB-08, SM-06 |
| `SM:8` | DB-08, SM-07 |
| `SM:9` | DB-08, SM-08 |
| `SM:10` | DB-08, SM-08 |
| `SM:11` | DB-08, SM-09 |
| `SM:12` | DB-08, SM-09 |
| `SM:13` | DB-11, SM-10 |
| `SM:14` | DB-08, IM-01, SM-11 |
| `SM:15` | SM-12 |
| `SM:S1` | SM-07 |
| `SM:S2` | SM-09 |
| `SM:S3` | SM-02 |
| `SM:S4` | DB-08 |
| `SM:S5` | DB-09, SM-04 |
| `SM:S6` | AT-04 |
| `SM:S7` | BL-01 |
| `SM:S10` | TA-36 |
| `SM:S8` | SM-07 |
| `SM:S9` | SM-07 |
| `SM:S11` | SM-03 |
| `SMX:1` | SM-13 |
| `SMX:2` | SM-13 |
| `SMX:3` | SM-13 |
| `SMX:4` | SM-13 |
| `SMX:5` | SM-13 |
| `SMX:6` | SM-13 |
| `SMX:7` | SM-13 |
| `SMX:8` | SM-13 |
| `SMX:9` | SM-13 |
| `SMX:10` | SM-13 |
| `SMX:11` | SM-13 |
| `SMX:12` | SM-13 |
| `SMX:13` | SM-13 |
| `SMX:14` | SM-13 |
| `SMX:15` | SM-13 |
| `SMX:16` | SM-13 |
| `SMX:17` | SM-13 |
| `RULE:R1` | RE-02, RE-05 |
| `RULE:R2` | RE-02, RE-06 |
| `RULE:R3` | RE-07 |
| `RULE:R4` | RE-08 |
| `RULE:R5` | RE-10 |
| `RULE:R6` | RE-11 |
| `RULE:R7` | RE-04 |
| `RULE:R8` | RE-09 |
| `RULE:R14` | RE-13 |
| `RULE:R9` | RE-12 |
| `RULE:R10` | RE-07 |
| `RULE:R13` | RE-06 |
| `RULE:R15` | RE-12 |
| `RULE:R16` | RE-12 |
| `RULE:R11` | CO-05, RE-13 |
| `RULE:R12` | RE-13 |
| `RULE:P1` | RE-03 |
| `RULE:P2` | RE-03 |
| `RULE:P3` | RE-03 |
| `RULE:P4` | RE-05 |
| `RULE:P5` | RE-06 |
| `RULE:P6` | PF-01, RE-13 |
| `RULE:P7` | RE-08 |
| `EXC:ORG_INACTIVE` | RE-02 |
| `EXC:CUSTOMER_ARCHIVED` | RE-02 |
| `EXC:CUSTOMER_INACTIVE` | RE-02 |
| `EXC:VOIDED` | RE-02 |
| `EXC:PAID` | RE-02 |
| `EXC:DISPUTED` | RE-02 |
| `EXC:PROMISE_ACTIVE` | RE-02 |
| `EXC:HOLD_ACTIVE` | RE-02 |
| `EXC:IMPORT_HELD` | RE-02 |
| `EXC:FREQUENCY_LIMIT` | RE-02 |
| `EXC:NO_CONTACT` | RE-02 |
| `EXC:NO_CONSENT` | RE-02 |
| `EXC:RECONCILIATION_PENDING` | RE-02 |
| `RE:01` | RE-01 |
| `RE:02` | RE-01 |
| `RE:03` | RE-01 |
| `RE:04` | RE-01 |
| `RE:05` | RE-01 |
| `RE:06` | RE-01 |
| `RE:07` | RE-01 |
| `RE:08` | RE-01 |
| `RE:09` | RE-01 |
| `RE:10` | RE-01 |
| `RE:11` | RE-01 |
| `RE:12` | RE-01 |
| `RE:13` | RE-01 |
| `RE:14` | RE-01 |
| `RE:15` | RE-01 |
| `RE:16` | RE-01 |
| `RE:17` | RE-01 |
| `RE:18` | RE-01 |
| `RE:19` | RE-01 |
| `RE:20` | RE-01 |
| `RE:21` | RE-01 |
| `RE:22` | RE-01 |
| `RE:23` | RE-01 |
| `RE:24` | RE-01 |
| `RE:25` | RE-01 |
| `RE:26` | RE-01 |
| `RE:27` | RE-01 |
| `RE:28` | RE-01 |
| `RE:29` | RE-01 |
| `RE:30` | RE-01 |
| `RE:31` | RE-01 |
| `RE:32` | RE-01 |
| `RE:33` | RE-01 |
| `RE:34` | RE-01 |
| `RE:35` | RE-01 |
| `RE:36` | RE-01 |
| `RE:37` | RE-01 |
| `RE:38` | RE-01 |
| `RE:39` | RE-01 |
| `RE:40` | RE-01 |
| `RE:41` | RE-01 |
| `RE:42` | RE-01 |
| `RE:43` | RE-01 |
| `RE:44` | RE-01 |
| `RE:45` | RE-01 |
| `RE:46` | RE-01 |
| `RE:47` | RE-01 |
| `RE:48` | RE-01 |
| `RE:49` | RE-01 |
| `RE:50` | RE-01 |
| `RE:51` | RE-01 |
| `RE:52` | RE-01 |
| `COL:C1` | CO-04 |
| `COL:C2` | CO-05 |
| `COL:C3` | CO-01, CO-06 |
| `COL:C4` | CO-03 |
| `COL:C5` | CO-07 |
| `COL:C6` | CO-08, SM-07 |
| `COL:C7` | CO-09 |
| `COL:C8` | CO-03 |
| `COL:C9` | CO-10 |
| `COL:C10` | CO-01 |
| `COL:C11` | CO-02, CO-11 |
| `COL:C12` | CO-12 |
| `COL:C13` | CO-13 |
| `COL:CP1` | CO-01, CO-15 |
| `COL:CP2` | CO-15, RE-11 |
| `COL:CP3` | CO-15, RE-03 |
| `COL:CP4` | CO-14 |
| `COL:CP5` | CO-14 |
| `COL:CP6` | CO-14 |
| `COL:CP7` | CO-14 |
| `AUT:AU1` | AT-01 |
| `AUT:AU2` | AT-02 |
| `AUT:AU3` | AT-02 |
| `AUT:AU4` | AT-03 |
| `AUT:AU5` | AT-04 |
| `AUT:AU6` | AT-07, DB-11 |
| `AUT:AU7` | AT-08 |
| `AUT:AU8` | AT-09 |
| `AUT:AU9` | AT-10, EV-05 |
| `AUT:AU10` | AT-11, EV-08 |
| `AUT:AU11` | AT-12 |
| `AUT:AU12` | AT-13 |
| `AUT:AP1` | AT-01 |
| `AUT:AP2` | AT-01 |
| `AUT:AP3` | AT-12 |
| `AUT:AP4` | AT-12 |
| `AUT:AP5` | AT-04 |
| `AUT:AP6` | AT-02 |
| `AUT:AP7` | AT-06, AT-14 |
| `AUT:AP8` | AT-14 |
| `ENG:EC1` | AR-04, EV-01 |
| `ENG:EC2` | EV-03 |
| `ENG:EC3` | CH-06 |
| `ENG:EC4` | AR-02 |
| `ENG:EC5` | CH-04, DB-01 |
| `ENG:EC6` | EV-06 |
| `ENG:EC7` | JB-01 |
| `ENG:EC8` | AR-02, CO-14 |
| `ENG:EC9` | AR-01 |
| `ENG:EC10` | CH-05, SE-02 |
| `ENG:P1` | EV-03 |
| `ENG:P2` | EV-03 |
| `ENG:P3` | AT-05 |
| `ENG:P4` | AT-09 |
| `ENG:P5` | **aucun** |
| `ENG:EC-01` | EV-01, EV-06 |
| `ENG:EC-02` | EV-03 |
| `ENG:EC-03` | JB-01 |
| `ENG:EC-04` | CH-03, CO-13 |
| `ENG:EC-05` | CH-04, DB-01 |
| `ENG:EC-06` | AR-02 |
| `ENG:EC-07` | AR-02 |
| `ENG:EC-08` | AR-02 |
| `ENG:EC-09` | AR-02 |
| `ENG:EC-10` | AR-02 |
| `ENG:EC-11` | CO-15 |
| `ENG:EC-12` | AR-02 |
| `ENG:EC-13` | AT-14 |
| `ENG:EC-14` | EV-07 |
| `ENG:X1` | EV-04 |
| `ENG:X2` | AR-03 |
| `ENG:X3` | AR-03, CO-14 |
| `ENG:X4` | AR-03 |
| `ENG:X5` | AR-03 |
| `ENG:X6` | CH-01, EV-04, EV-09 |
| `ENG:X7` | EV-05 |
| `ENG:X8` | CH-02 |
| `ENG:X9` | EV-08 |
| `ENG:X10` | EV-02 |
| `ENG:X11` | DB-10, DB-16, SE-01 |
| `ENG:X12` | RE-03 |
| `ENG:X13` | CO-14 |
| `ENG:X14` | CH-01, EV-04 |
| `ENG:X15` | AT-05 |
| `ENG:X16` | EV-03 |
| `ENG:X17` | RP-05 |
| `ENG:DR1` | AR-01 |
| `ENG:DR2` | AR-01 |
| `ENG:DR3` | AR-01 |
| `ENG:DR4` | AR-01 |
| `ENG:DR5` | AR-01 |
| `ENG:DR6` | AR-01 |
| `ENG:DR7` | AR-01 |
| `ENG:DR8` | AR-01 |
| `ENG:DR9` | AR-01 |
| `JOB:OutboxPublisher` | JB-02, PF-04 |
| `JOB:InvoiceLifecycleScan` | JB-03 |
| `JOB:PromiseBreachScan` | JB-04 |
| `JOB:HoldExpiryScan` | JB-04 |
| `JOB:ApprovalExpiryScan` | JB-04 |
| `JOB:TimeTriggerScanner` | JB-05 |
| `JOB:ExecutionWorker` | CH-07, JB-06 |
| `JOB:ExecuteDueActions` | JB-06 |
| `JOB:Reaper` | JB-06 |
| `JOB:ImportReleaser` | JB-07 |
| `JOB:EnrollmentRunner` | JB-07 |
| `JOB:ProjectionDailyRefresh` | RP-08 |
| `JOB:ProjectionSafetyNet` | RP-08 |
| `JOB:ReconciliationWindowScan` | RC-08 |
| `JOB:CashflowScheduler` | JB-08 |
| `JOB:PartitionManager` | DB-15 |
| `JOB:TechnicalPurge` | JB-09 |
| `RPC:RP1` | RP-01 |
| `RPC:RP2` | RP-12 |
| `RPC:RP3` | RP-01, RP-06 |
| `RPC:RP4` | PF-05, RP-02 |
| `RPC:RP5` | PF-03, RP-03 |
| `RPC:RP6` | RP-05 |
| `RPC:RP7` | RP-08, RP-11 |
| `RPC:RP8` | RE-10, RP-11 |
| `RPC:RP9` | RP-08 |
| `RPC:RP10` | RP-09 |
| `RPC:RP11` | RP-03, RP-10 |
| `RPC:RP12` | RP-12 |
| `RPC:RP13` | RP-07 |
| `RPC:RP14` | RP-05 |
| `RPC:RP15` | RP-02, RP-06 |
| `RPC:RP16` | RP-02 |
| `RPC:RP17` | DB-11, RP-10 |
| `RPC:RP18` | RP-04 |
| `RPC:RP19` | RP-04 |
| `RPC:RP20` | DB-12, RP-04 |
| `RPC:RP21` | PF-02, RP-07 |
| `RPC:RP22` | RP-08 |
| `RPC:RP23` | RC-03, RP-02 |
| `RPC:PA` | RP-01 |
| `RPC:PB` | RP-01 |
| `RPC:PC` | RP-09, RP-15 |
| `RPC:PD` | RP-09, RP-13 |
| `RPC:PE` | RP-07, RP-15 |
| `RPC:PF` | RP-15 |
| `RPC:PG` | RP-01, RP-13 |
| `RPC:PH` | RP-13 |
| `RPC:CF1` | RP-04 |
| `RPC:CF2` | RP-04 |
| `RPC:CF3` | RP-04 |
| `RPC:CF4` | RP-04 |
| `RPC:CF5` | RP-04 |
| `RPC:CF6` | RP-04 |
| `GOLD:G1` | RP-01 |
| `GOLD:G2` | RP-01 |
| `GOLD:G3` | RP-01 |
| `GOLD:G4` | RP-01 |
| `GOLD:G5` | RP-01 |
| `GOLD:P1` | RP-02 |
| `GOLD:P2` | RP-02 |
| `GOLD:P3` | RP-02 |
| `GOLD:P4` | RP-02 |
| `GOLD:P5` | RP-02 |
| `GOLD:P6` | RP-02 |
| `GOLD:P7` | RP-02 |
| `GOLD:C1` | RP-03 |
| `GOLD:C10` | RP-03 |
| `GOLD:C2` | RP-03 |
| `GOLD:C3` | RP-03 |
| `GOLD:C4` | RP-03 |
| `GOLD:C5` | RP-03 |
| `GOLD:C6` | RP-03 |
| `GOLD:C7` | RP-03 |
| `GOLD:C8` | RP-03 |
| `GOLD:C9` | RP-03 |
| `GOLD:R1` | RC-01 |
| `GOLD:R2` | RC-01 |
| `GOLD:R3` | RC-01 |
| `GOLD:R4` | RC-01 |
| `GOLD:R5` | RC-01 |
| `GOLD:R6` | RC-01 |
| `GOLD:R7` | RC-01 |
| `GOLD:R8` | RC-01 |
| `GOLD:R9` | RC-01 |
| `GOLD:R10` | RC-01 |
| `GOLD:R11` | RC-02 |
| `GOLD:R12` | RC-02 |
| `GOLD:R13` | RC-02 |
| `GOLD:R14` | RC-02 |
| `RCN:RN1` | RC-04, RC-12 |
| `RCN:RN2` | RC-01, RC-04, RC-07 |
| `RCN:RN3` | RC-03 |
| `RCN:RN4` | RC-03, RC-05 |
| `RCN:RN5` | RC-02, RC-08, RC-11 |
| `RCN:RN6` | RC-06, RC-07 |
| `RCN:RN7` | RC-08 |
| `RCN:RN8` | RC-10 |
| `RCN:RN9` | RC-09 |
| `RCN:RN10` | RC-05 |
| `RCN:RN11` | RC-01, RC-11 |
| `RCN:RN12` | RC-02, RC-12 |
| `TD:1` | TA-01 |
| `TD:2` | TA-01 |
| `TD:3` | TA-01 |
| `TD:4` | TA-01 |
| `TD:5` | TA-01 |
| `TD:6` | TA-03 |
| `TD:7` | TA-35 |
| `TD:8` | TA-04 |
| `TD:9` | TA-01 |
| `TD:10` | TA-01 |
| `TD:11` | TA-35 |
| `TD:12` | TA-01 |
| `TD:13` | TA-01 |
| `TD:14` | TA-01 |
| `TD:15` | TA-04 |
| `TD:16` | TA-04 |
| `TD:17` | TA-05, TA-07, TA-12 |
| `TD:18` | TA-05, TA-06 |
| `TD:19` | SE-13, TA-08 |
| `TD:20` | TA-09 |
| `TD:21` | TA-11 |
| `TD:22` | TA-10 |
| `TD:23` | TA-02, TA-11 |
| `TD:24` | TA-02 |
| `TD:25` | TA-31 |
| `TD:26` | TA-11 |
| `TD:27` | TA-12 |
| `TD:28` | TA-13, TA-32 |
| `TD:29` | TA-12, TA-14 |
| `TD:30` | TA-15, TA-31 |
| `TD:31` | TA-13, TA-17, TA-28, TA-37 |
| `TD:32` | TA-16 |
| `TD:33` | TA-18, TA-19 |
| `TD:34` | TA-19 |
| `TD:35` | TA-20 |
| `TD:36` | TA-21 |
| `TD:37` | TA-22 |
| `TD:38` | TA-23 |
| `TD:39` | TA-24 |
| `TD:40` | TA-35 |
| `TD:41` | TA-25 |
| `TD:42` | TA-30 |
| `TD:43` | TA-25 |
| `TD:44` | TA-25 |
| `TD:45` | TA-25 |
| `TD:46` | TA-26 |
| `TD:47` | TA-27 |
| `TD:48` | TA-30 |
| `TD:49` | TA-30 |
| `TD:50` | TA-30 |
| `TD:51` | TA-01 |
| `TD:52` | TA-17 |
| `TD:53` | TA-33 |
| `TD:54` | TA-34 |
| `TD:55` | TA-35 |
| `TD:56` | TA-35 |
| `TD:57` | TA-35 |
| `TD:58` | TA-35, TA-36, TA-37 |
| `TD:59` | TA-36 |
| `TI:1` | TA-01, TA-02 |
| `TI:2` | TA-05 |
| `TI:3` | TA-01 |
| `TI:4` | TA-12 |
| `TI:5` | TA-17 |
| `TI:6` | TA-18 |
| `TI:7` | TA-19, TA-20 |
| `TI:8` | TA-30 |
| `TI:9` | TA-14 |
| `TI:10` | TA-21 |
| `TI:11` | TA-05 |
| `TI:12` | TA-25 |
| `TI:13` | TA-08 |
| `TI:14` | TA-16 |
| `TI:15` | TA-29 |
| `TI:16` | TA-01 |
| `TI:17` | TA-02 |
| `TI:18` | TA-07 |
| `TI:19` | TA-17 |
| `TI:20` | TA-35 |
| `TI:21` | TA-36, TA-37 |
| `TI:22` | TA-35 |
| `AR:01` | TA-34 |
| `AR:02` | TA-34 |
| `AR:03` | TA-34 |
| `AR:04` | TA-34 |
| `AR:05` | TA-34 |
| `AR:06` | TA-34 |
| `AR:07` | TA-34 |
| `AR:08` | TA-34 |
| `AR:09` | TA-34 |
| `AR:10` | TA-34 |
| `AR:11` | TA-34 |
| `AR:12` | TA-34 |
| `AR:13` | TA-09, TA-34 |
| `AR:14` | TA-34 |
| `AR:15` | TA-34 |
| `AR:16` | TA-34 |
| `AR:17` | TA-34 |
| `AR:18` | TA-34 |
| `AR:19` | TA-34 |
| `AR:20` | TA-34 |

## Annexe C · Familles couvertes en partie par une porte

- `ERR` : 110 éléments, **104** couverts explicitement, **6** par la porte seule.
- `EVT` : 77 éléments, **77** couverts explicitement, **0** par la porte seule.
- `TAB` : 41 éléments, **41** couverts explicitement, **0** par la porte seule.
