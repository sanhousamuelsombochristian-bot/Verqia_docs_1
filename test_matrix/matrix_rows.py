# -*- coding: utf-8 -*-
"""Lignes de la matrice de tests globale.

Chaque test : (identifiant, niveau, ce que l'on prouve, oracle, éléments couverts).
Niveaux : L0 statique/CI · L1 Domain pur · L2 PostgreSQL · L3 cas d'usage intégré · L4 flux entre moteurs ·
          L5 scénario de bout en bout (horloge virtuelle) · L6 propriétés / différentiel / chaos · L7 non fonctionnel.
Oracles : voir §2 du document (O1 modèle de référence, O2 cas d'or, O3 table de transitions, O4 vérificateurs globaux,
          O5 registre de schémas, O6 implémentation naïve, O7 relations métamorphiques, O8 rejeu / reconstruction, O9 contrat ↔ schéma).
"""

SECTIONS = []


def S(code, title, intro, rows):
    SECTIONS.append({'code': code, 'title': title, 'intro': intro, 'rows': rows})


# ------------------------------------------------------------------------------------------------ A
S('DB', 'A. Schéma et contraintes PostgreSQL',
  'Ces tests s’exécutent **sur PostgreSQL** (jamais sur une base de substitution) : les garanties financières vivent dans la base, pas seulement dans le code.',
  [
      ('DB-01', 'L2', 'Allocations : la somme par paiement reste dans [0, montant] et la somme par facture dans [0, total] ; un reversal ne dépasse jamais son allocation d’origine ; deux sessions concurrentes qui allouent le même disponible : une seule réussit.', 'O4-G02, O6', 'CON:T1 CON:T2 CON:T3 ENG:EC-05 ENG:EC5'),
      ('DB-02', 'L2', 'Caches vérifiés en fin de transaction : `paid_minor`, `settlement_state`, `settled_on`, `allocated_minor`, `status` égalent la somme des allocations ; toute divergence provoquée à la main est refusée au `COMMIT`.', 'O4-G02, O4-G03', 'CON:T4 CON:T5 TAB:invoices TAB:payments TAB:payment_allocations TAB:payment_reversals'),
      ('DB-03', 'L2', 'Aucune allocation nette positive sur une facture `DRAFT`, `CANCELLED` ou `VOID`, ni sur un paiement `REVERSED`.', 'O4-G02', 'CON:T6 CON:T10'),
      ('DB-04', 'L2', 'Lignes de facture immuables hors `DRAFT` ; à l’émission, la somme des lignes égale le total.', 'O4-G06', 'CON:T7 CON:T9 TAB:invoice_items'),
      ('DB-05', 'L2', 'Tables append-only : `UPDATE`, `DELETE` et `TRUNCATE` refusés au rôle applicatif sur toutes les tables historiques ; le rôle de confidentialité ne peut toucher que ses colonnes de texte.', 'O4-G06', 'CON:T8 TAB:invoice_state_history TAB:promise_history TAB:risk_snapshots TAB:priority_snapshots TAB:automation_versions TAB:automation_execution_steps TAB:collection_action_attempts TAB:notification_deliveries TAB:audit_logs INV:D7'),
      ('DB-06', 'L2', 'Montant contesté ≤ total de la facture ; numéro de tentative ≤ `max_attempts`.', 'O4-G03', 'CON:T11 CON:T12 TAB:invoice_disputes'),
      ('DB-07', 'L2', 'Après émission, `number`, `customer_id`, `currency`, `issue_date`, `due_date`, `total_minor` sont immuables ; une création par import (INSERT) n’est pas concernée ; une renégociation passe par une promesse.', 'O4-G06', 'CON:T13 INV:N1'),
      ('DB-08', 'L2', 'Garde de transition : pour chacune des 12 machines protégées, **tout couple (état, état)** est essayé ; il est accepté si et seulement s’il figure dans la table de transitions du Domain ; la table SQL est **générée** depuis le Domain et comparée.', 'O3', 'CON:T14 SM:S4 SM:1 SM:2 SM:3 SM:5 SM:6 SM:7 SM:8 SM:9 SM:10 SM:11 SM:12 SM:14 INV:C3'),
      ('DB-09', 'L2', '`VOID` refusé tant qu’un litige `OPEN` existe ; accepté dès sa résolution.', 'O3', 'CON:T15 SM:S5'),
      ('DB-10', 'L2', 'Clés étrangères composites : pour **chaque** FK composite, un enregistrement pointant vers une ligne d’une autre organisation est refusé ; `collection_actions`, `promises`, `priority_items` refusent un client différent de celui de la facture.', 'O4-G01', 'TAB:* INV:C2 ENG:X11'),
      ('DB-11', 'L2', 'Index uniques partiels : un litige `OPEN`, une promesse `ACTIVE` par portée, un contact principal actif par canal, une exécution non terminale par (automatisation, sujet), un run `RUNNING` et un run courant par triplet de trésorerie, un abonnement actif, clés de déduplication hors `CANCELLED`/`SUPPRESSED`.', 'O4-G10, O4-G11', 'AUT:AU6 RPC:RP17 SM:13 TAB:customer_contacts TAB:promises TAB:cashflow_runs TAB:subscriptions TAB:automation_executions TAB:collection_actions TAB:notifications'),
      ('DB-12', 'L2', 'Colonnes générées : `outstanding_minor`, `weighted_minor`, `automation_versions.trigger_type` ; `weighted_minor` égale le modèle de référence sur 20 000 valeurs aléatoires.', 'O1, O6', 'RPC:RP20 TAB:cashflow_lines TAB:automation_versions'),
      ('DB-13', 'L2', 'Chaque `CHECK` d’énumération et de cohérence (états, portées XOR, `is_current ⇒ COMPLETED`, dates) est refusé quand on le viole.', 'O9', 'TAB:*'),
      ('DB-14', 'L2', 'Exclusion des suspensions : chevauchement refusé, y compris pour la portée organisation (cible non nulle grâce au `coalesce`) ; extension `btree_gist` présente.', 'O4', 'TAB:collection_holds'),
      ('DB-15', 'L2', 'Partitions : `events` et `audit_logs` partitionnées par mois (clé `(id, occurred_at)`) ; le gestionnaire crée les trois prochaines partitions ; alerte si la partition par défaut reçoit une ligne ; le détachement d’une partition la conserve.', 'O4', 'JOB:PartitionManager INV:D8 TAB:events TAB:event_receipts TAB:idempotency_keys'),
      ('DB-16', 'L2', 'Row-Level Security : sans `app.organization_id`, aucune ligne n’est visible ; le rôle applicatif n’est pas propriétaire des tables ; le rôle de migration est distinct du rôle d’exécution.', 'O4-G01', 'INV:C2 ENG:X11'),
      ('DB-17', 'L2', '`ON DELETE RESTRICT` partout : la suppression d’une ligne parente référencée est refusée pour chaque FK.', 'O4', 'TAB:*'),
      ('DB-18', 'L2', 'Types : montants `bigint` en unité mineure, devise `char(3)` majuscule, tous les instants `timestamptz` UTC ; aucune colonne flottante monétaire.', 'O9', 'TAB:*'),
      ('DB-19', 'L0', '**Contrat ↔ schéma** : le schéma réel (colonnes, types, nullité, contraintes, index) est comparé au Data Contract ; tout écart fait échouer la CI.', 'O9', 'TAB:*'),
      ('DB-20', 'L2', 'Tables du domaine « import » et « organisation » : contraintes des lots (unicité du fichier, `approved_by` requis à partir de `APPROVED`), des réglages et des jours fériés.', 'O4', 'TAB:import_batches TAB:import_rows TAB:organizations TAB:users TAB:memberships TAB:org_settings TAB:org_holidays TAB:customers TAB:plans'),
      ('DB-21', 'L2', 'Tables des moteurs : contraintes de `risk_profiles`, `priority_items`, leurs snapshots, `approvals`, `automations`, `message_templates`, `notification_deliveries`.', 'O4', 'TAB:risk_profiles TAB:priority_items TAB:approvals TAB:automations TAB:message_templates TAB:notification_deliveries'),
  ])

# ------------------------------------------------------------------------------------------------ B
S('SM', 'B. Machines à états et cascades',
  'Pour chaque machine, deux familles de tests **générées** depuis la table de transitions : chaque transition permise réussit (garde satisfaite, historique écrit, événement émis) ; chaque couple non permis est refusé au Domain **et** en base (T14).',
  [
      ('SM-01', 'L3', 'Organisation : `ACTIVE ⇄ SUSPENDED`, `→ CLOSED` terminal ; suspension : exécutions en pause `ORG_INACTIVE`, aucune communication ; réactivation : reprise. Client : matrice `ACTIVE`/`INACTIVE`/`ARCHIVED` opération par opération ; archivage refusé avec facture ouverte ; réactivation jamais automatique.', 'O3, tableau §Customer', 'SM:1 SM:2 INV:N3 INV:D6 RSN:ORG_INACTIVE RSN:CUSTOMER_INACTIVE RSN:CUSTOMER_ARCHIVED'),
      ('SM-02', 'L3', 'Facture, cycle de vie : sauts permis, jamais de retour en arrière, gel quand `PAID`, recalcul à l’annulation du règlement, rattrapage à l’émission tardive, immuabilité de l’échéance, une seule transition par événement émis.', 'O3, O4-G04', 'SM:3 SM:S3 INV:N1 INV:C3'),
      ('SM-03', 'L3', 'Facture, règlement dérivé : chaque transition provoquée par une allocation ou un reversal produit le bon événement ; `PARTIALLY_PAID → PARTIALLY_PAID` n’en produit aucun ; `settled_on` posé et effacé ; `collection_cycle` incrémenté dans les deux cas prévus, jamais deux fois dans la même transaction ; annulation d’un règlement : cycle de vie recalculé en avant dans la transaction du reversal (B3-a), sans attendre le balayage.', 'O3, O4-G02', 'SM:4 INV:N12 SM:S11'),
      ('SM-04', 'L3', 'Litige : ouverture, résolution rejetée / fondée ; effet sur `collectible_minor` ; suspension seulement si le recouvrable est nul ; `VOID` refusé pendant un litige ouvert ; procédure V1 d’un litige fondé (reverser, annuler, ré-émettre).', 'O3', 'SM:5 INV:D1 SM:S5'),
      ('SM-05', 'L3', 'Paiement : allocation, reversal d’allocation, reversal du paiement (toutes les allocations reversées dans la même transaction), états dérivés, `REVERSED` terminal ; date de valeur non future dans le fuseau de l’organisation.', 'O3', 'SM:6 INV:N2 INV:C10'),
      ('SM-06', 'L3', 'Promesse : création (montant, date, unicité par portée), tenue, rupture après délai de grâce, annulation ; modification = annulation + création ; `FULFILLED` reste terminal après un reversal ; promesse client sans facture ouverte annulée.', 'O3', 'SM:7 INV:N5 INV:N6 INV:N11'),
      ('SM-07', 'L3', 'Action de recouvrement : toutes les transitions du tableau, dont `SCHEDULED → DONE` (tâche humaine, issue obligatoire), `PENDING_APPROVAL → SUPPRESSED`, retry `EXECUTING → SCHEDULED`, `SUPPRESSED` ≠ `CANCELLED` ; libération de la clé après suppression.', 'O3', 'SM:8 SM:S1 SM:S8 COL:C6 SM:S9'),
      ('SM-08', 'L3', 'Suspension manuelle et approbation : création, libération, expiration (lecture par dates, indépendante du balayage) ; approbation accordée / refusée / expirée / cible résolue (`TARGET_RESOLVED`).', 'O3', 'SM:9 SM:10'),
      ('SM-09', 'L3', 'Automatisation (`active_since` posé et effacé) et exécution (les 7 états, retry, reprise) : chaque cause de pause et sa levée.', 'O3', 'SM:11 SM:12 SM:S2 RSN:AUTOMATION_PAUSED RSN:AUTOMATION_DISABLED RSN:DISPUTED RSN:PROMISE_ACTIVE RSN:HOLD_ACTIVE RSN:IMPORT_HELD RSN:SUBJECT_PAID RSN:SUBJECT_VOIDED RSN:USER RSN:RECONCILIATION_PENDING'),
      ('SM-10', 'L3', 'Run de trésorerie : `RUNNING → COMPLETED / FAILED`, bascule de `is_current`, jamais courant si `FAILED`.', 'O3', 'SM:13'),
      ('SM-11', 'L3', 'Lot d’import : les 13 états, annulation possible seulement avant `COMMITTED`, jamais après.', 'O3', 'SM:14'),
      ('SM-12', 'L3', 'Machines compactes : notification, abonnement, utilisateur, adhésion (au moins un `OWNER` actif), gabarit de message.', 'O3', 'SM:15'),
      ('SM-13', 'L4', 'Les 17 cascades du tableau des couplages : chacune est déclenchée par son événement source et vérifiée ; celles « par événement » sont idempotentes et revalident ; celle de l’allocation est atomique.', 'O3, O4-G09', 'SMX:1 SMX:2 SMX:3 SMX:4 SMX:5 SMX:6 SMX:7 SMX:8 SMX:9 SMX:10 SMX:11 SMX:12 SMX:13 SMX:14 SMX:15 SMX:16 SMX:17'),
      ('SM-14', 'L1', 'Chaque `UPDATE … WHERE état = ancien` qui ne touche aucune ligne produit `INVALID_TRANSITION` ou `CONCURRENT_MODIFICATION` ; deux transitions concurrentes : une seule gagne.', 'O3', 'INV:C3 INV:C4'),
      ('SM-15', 'L3', 'Décisions d’état verrouillées : `DISPUTED` orthogonal, facture émise à zéro refusée, archivage refusé avec facture ouverte, une correction financière ne réactive jamais un client archivé.', 'O3', 'INV:D6 INV:N3'),
  ])

# ------------------------------------------------------------------------------------------------ C
S('EV', 'C. Événements, outbox et handlers',
  'Le socle de fiabilité : aucun effet sans événement, aucun événement perdu, aucun effet dupliqué.',
  [
      ('EV-01', 'L3', 'Atomicité de l’outbox : panne avant `COMMIT` = ni changement ni événement ; après `COMMIT` = les deux ; mutation, transition et demande produisent chacune leur événement dans la même transaction.', 'O4-G07', 'INV:C5 ENG:EC-01 ENG:EC1'),
      ('EV-02', 'L1', 'Charges utiles : liste blanche de champs par type ; aucune donnée personnelle (nom, téléphone, e-mail) dans `events`, `decision_snapshot`, traces du Rule Engine.', 'O5, O4-G08', 'INV:C9 ENG:X10 ERR:EVENT_SCHEMA_INVALID ERR:EVENT_PAYLOAD_NOT_WHITELISTED'),
      ('EV-03', 'L4', 'Handler : première livraison → `PROCESSED` ou `SKIPPED` ; deuxième livraison → `REPLAY` (compté, rien d’écrit) ; échecs répétés (10 s, 1 min, 5 min, 30 min, 2 h) → `DEAD` ; `DEAD` jamais retraité automatiquement, seul `ReplayDeadEvent` le relance ; `REPLAY` et `SKIPPED` distincts dans les métriques.', 'O4-G09', 'ENG:EC-02 ENG:EC2 ENG:P1 ENG:P2 ENG:X16 INV:C6 INV:C11 INV:N10'),
      ('EV-04', 'L6', 'Désordre : événements d’un même agrégat livrés dans le désordre, ou obsolètes (`aggregate_version` plus ancienne) → `SKIPPED` ; les handlers relisent l’état et ne supposent aucun ordre entre agrégats.', 'O8', 'ENG:X1 ENG:X14 ENG:X6'),
      ('EV-05', 'L4', 'Profondeur de causalité ≤ 20 ; au-delà, l’émission est refusée et alertée ; une chaîne Risk → Priority → Automation reste finie.', 'O4-G12', 'ENG:X7 AUT:AU9 ERR:CAUSATION_DEPTH_EXCEEDED'),
      ('EV-06', 'L0', 'Registre de schémas : chaque type d’événement et `Decision` ont un schéma versionné ; une évolution non additive (champ retiré, renommé) fait échouer la CI ; une rupture exige une double publication.', 'O5', 'ENG:EC6 ENG:EC-01'),
      ('EV-07', 'L4', 'Catégories : `REQUEST` a un seul destinataire et se regroupe ; `TRANSITION` correspond à une ligne d’historique ; `RESULT` seulement sur changement de niveau ; `MUTATION` pour les faits append-only.', 'O4-G07', 'INV:C5 INV:N9 ENG:EC-14'),
      ('EV-08', 'L4', 'Événements des lots d’import : `import_batch_id` propagé ; aucune automatisation ne les consomme avant `RELEASING`.', 'O4-G20', 'ENG:X9 AUT:AU10'),
      ('EV-09', 'L6', '**Rejeu global** : rejouer tout le journal d’événements sur une base vierge (ou rejouer chaque événement deux fois) aboutit au même état final (projections, actions, exécutions).', 'O8', 'ENG:X6 INV:C6'),
      ('EV-10', 'L0', 'Porte de couverture : **tout type d’événement du catalogue** a un test producteur, un test de schéma et, s’il a des consommateurs, un test de réaction ; le registre est généré et vérifié en CI.', 'O5', 'EVT:*'),
      ('EV-11', 'L3', 'Catalogue explicite : les événements d’organisation, de client, de facture, de paiement, de promesse, d’action, de suspension, d’approbation, d’automatisation, d’import, de notification et d’abonnement sont chacun observés dans un scénario de bout en bout (contrôle croisé de la porte).', 'O4-G07', 'EVT:INVOICE_ISSUED EVT:INVOICE_OVERDUE EVT:INVOICE_PAID EVT:PAYMENT_ALLOCATED EVT:PROMISE_BROKEN EVT:COLLECTION_ACTION_EXECUTED EVT:RISK_CHANGED EVT:PRIORITY_CHANGED EVT:CASHFLOW_UPDATED EVT:IMPORT_BATCH_RELEASED'),
  ])

# ------------------------------------------------------------------------------------------------ D
S('RE', 'D. Rule Engine',
  'Le Rule Engine est une fonction pure : ses tests sont des tables d’entrées et de décisions attendues.',
  [
      ('RE-01', 'L1', '**Les 52 scénarios d’or du Rule Engine §10.2**, exécutés à l’identique (une entrée, une décision complète : issue, exception primaire, trace, niveau).', 'O2', 'RE:01 RE:02 RE:03 RE:04 RE:05 RE:06 RE:07 RE:08 RE:09 RE:10 RE:11 RE:12 RE:13 RE:14 RE:15 RE:16 RE:17 RE:18 RE:19 RE:20 RE:21 RE:22 RE:23 RE:24 RE:25 RE:26 RE:27 RE:28 RE:29 RE:30 RE:31 RE:32 RE:33 RE:34 RE:35 RE:36 RE:37 RE:38 RE:39 RE:40 RE:41 RE:42 RE:43 RE:44 RE:45 RE:46 RE:47 RE:48 RE:49 RE:50 RE:51 RE:52'),
      ('RE-02', 'L1', 'Les 13 garde-fous, chacun en échec et en réussite ; **ordre fixe** ; toutes évaluées et consignées, une seule décide (`primary_exception`).', 'O2', 'EXC:ORG_INACTIVE EXC:CUSTOMER_ARCHIVED EXC:CUSTOMER_INACTIVE EXC:VOIDED EXC:PAID EXC:DISPUTED EXC:PROMISE_ACTIVE EXC:HOLD_ACTIVE EXC:IMPORT_HELD EXC:FREQUENCY_LIMIT EXC:NO_CONTACT EXC:NO_CONSENT RULE:R1 RULE:R2 EXC:RECONCILIATION_PENDING'),
      ('RE-03', 'L1', 'Déterminisme : mêmes entrées, même `decision_id` ; aucune lecture d’horloge ; permutation des termes d’un `all` / `any` sans effet ; ajouter une exception ne transforme jamais `SUPPRESS` en `PROCEED`.', 'O7', 'RULE:P1 RULE:P2 RULE:P3 COL:CP3 ENG:X12'),
      ('RE-04', 'L1', 'Logique à trois valeurs : table de vérité complète ; `UNKNOWN` jamais traité comme vrai ; racine inconnue ⇒ `SKIP`.', 'O7', 'RULE:R7'),
      ('RE-05', 'L1', 'Non-contournement : une définition ne peut ni retirer, ni réordonner, ni désactiver une exception intégrée ; les exceptions ajoutées s’évaluent après.', 'O2', 'RULE:P4 RULE:R1'),
      ('RE-06', 'L4', 'Barrière de fraîcheur : projection plus ancienne que l’événement → `DEFER` (30 s, 2 min, 10 min, 30 min) puis évaluation marquée `stale` ; égalité acceptée ; événement hors `refresh_events` → aucune barrière ; recalcul sans changement met `computed_at` à jour.', 'O2', 'RULE:R2 RULE:R13 RULE:P5'),
      ('RE-07', 'L1', 'Applicabilité et contournement : classes intégrité / métier / politique / livraison ; `OverrideGrant` typé produit par le domaine (jamais un booléen) ; rôles minimaux ; hold `LEGAL` jamais contournable.', 'O2', 'RULE:R3 RULE:R10 ERR:OVERRIDE_NOT_ALLOWED ERR:OVERRIDE_ROLE_INSUFFICIENT ERR:OVERRIDE_REASON_REQUIRED ERR:OVERRIDE_ORIGIN_NOT_MANUAL'),
      ('RE-08', 'L1', 'Temps : faits calculés depuis les dates, indépendants du retard du Scheduler ; fuseau de l’organisation, jours ouvrés, jours fériés, heure d’été.', 'O2', 'RULE:R4 RULE:P7 INV:C10'),
      ('RE-09', 'L0', 'Validateur de définitions : une définition invalide **par code d’erreur** (schéma, fait inconnu, type, action, niveau, complexité, retrait d’une exception, boucle, projection, canal désactivé, couple niveau/type, plage d’étape) ; fuzzing du schéma.', 'O2', 'RULE:R8 ERR:DEFINITION_SCHEMA_INVALID ERR:DEFINITION_UNKNOWN_FACT ERR:DEFINITION_TYPE_MISMATCH ERR:DEFINITION_ACTION_NOT_ALLOWED ERR:DEFINITION_VALUE_OUT_OF_RANGE ERR:DEFINITION_TOO_COMPLEX ERR:DEFINITION_BUILTIN_EXCEPTION_OVERRIDE ERR:DEFINITION_TRIGGER_LOOP ERR:DEFINITION_PROJECTION_TRIGGER_MISMATCH ERR:DEFINITION_CHANNEL_NOT_ENABLED ERR:DEFINITION_LEVEL_TYPE_INCOMPATIBLE ERR:DEFINITION_STEP_LEVEL_RANGE_INVALID ERR:DEFINITION_ACTION_SUBJECT_MISMATCH ERR:DEFINITION_NOT_FOUND'),
      ('RE-10', 'L6', 'Chaque fait SQL comparé à une implémentation naïve sur données aléatoires ; faits comportementaux (formules entières, demi-haut) ; `unallocated_payment_minor`.', 'O6', 'RULE:R5 RPC:RP8'),
      ('RE-11', 'L4', 'Persistance de la décision : trace complète dans `decision_snapshot` et `revalidation_result` ; `SKIP` et `DEFER` au niveau du déclencheur non persistés (compteurs) ; explication à la demande identique à la décision réelle.', 'O8', 'RULE:R6 COL:CP2'),
      ('RE-12', 'L1', 'Niveau : table ordonnée, premier appariement, niveau initial 0, plancher 3 dès `OVERDUE`, non-régression sur `SCHEDULED`/`EXECUTING`/`DONE` seulement, `SKIP` avec raison.', 'O2', 'RULE:R9 RULE:R15 RULE:R16 INV:N7'),
      ('RE-13', 'L2', 'Isolation : évaluer un sujet de l’organisation A avec le contexte de B → `SUBJECT_NOT_FOUND`, aucune ligne de A lue.', 'O4-G01', 'RULE:R11 RULE:R12 RULE:R14 RULE:P6 ERR:SUBJECT_NOT_FOUND ERR:FACT_UNKNOWN_NAME'),
  ])

# ------------------------------------------------------------------------------------------------ E
S('CO', 'E. Collection Engine',
  'De la décision à l’action : création, planification, exécution, retry, repli.',
  [
      ('CO-01', 'L5', '**Scénario de référence** (émission le 2026-09-28, échéance 2026-10-15) : chaque action attendue (date, niveau, type, statut) comparée à la table du Collection Engine §11 ; week-ends et jours fériés ; S6 sans effet à risque `MEDIUM` (REPLAY).', 'O2', 'COL:C10 COL:C3 COL:CP1'),
      ('CO-02', 'L5', 'Variantes du scénario : risque `HIGH` (niveau 5) ; règlement à J+7 ; promesse à J+5 ; litige partiel (montant recouvrable dans le message) ; client `INACTIVE` en cours de route.', 'O2', 'COL:C11'),
      ('CO-03', 'L3', 'Déduplication `{facture}:{type}:L{niveau}:C{cycle}:R{occurrence}` : `occurrence` lue dans l’exécution, jamais fournie ; `manual:{clé}` ; une action `SUPPRESSED` libère sa clé, une `DONE`/`FAILED` la garde ; rejet d’approbation → pas de re-proposition dans le cycle.', 'O4-G10', 'COL:C4 COL:C8 ERR:ACTION_LEVEL_REGRESSION'),
      ('CO-04', 'L3', 'Canaux : `EMAIL` (client), `IN_APP` (interne), `PHONE` (tâche humaine) ; `SMS` et `WHATSAPP` rejetés à la validation ; `IN_APP` ne joint jamais le client.', 'O2', 'COL:C1 ERR:CHANNEL_NOT_ENABLED'),
      ('CO-05', 'L3', 'Repli humain : `NO_CONTACT`, `NO_CONSENT`, `FAILED` → une seule tâche `FOLLOW_UP`, sans repli du repli ; consentement du contact de référence sans repli vers un autre contact.', 'O2', 'COL:C2 RULE:R11 INV:N4'),
      ('CO-06', 'L1', 'Matrice type × niveau (rappel 1–4, appel 3–5, suivi 3–5, escalade 4–5) et plages de niveaux par étape.', 'O2', 'COL:C3 INV:N8 ERR:ACTION_LEVEL_INVALID ERR:ACTION_LEVEL_BELOW_MINIMUM'),
      ('CO-07', 'L3', 'Pool de rôle : réclamation simultanée par deux membres (une seule gagne) ; pool jamais vide ; file de travail triée par priorité puis niveau puis échéance.', 'O6', 'COL:C5 ERR:CONCURRENT_MODIFICATION'),
      ('CO-08', 'L3', 'Tâches humaines : `SCHEDULED → DONE` avec issue obligatoire ; alerte de retard sans changement de statut ; issues suggérant promesse ou litige sans les créer.', 'O3', 'COL:C6 OUT:CONTACTED OUT:NO_ANSWER OUT:PROMISE_OBTAINED OUT:DISPUTE_RAISED OUT:REFUSED OUT:WRONG_CONTACT OUT:OTHER'),
      ('CO-09', 'L3', 'Issues d’une action en liste fermée : `SENT`, `BOUNCED`, annulations ; toute autre valeur refusée par la base.', 'O4', 'COL:C7 OUT:SENT OUT:BOUNCED OUT:USER_CANCELLED OUT:APPROVAL_REJECTED OUT:APPROVAL_EXPIRED'),
      ('CO-10', 'L3', 'Plafond de messages par client et par jour, lissage du débit, fenêtre de communication (report, pas erreur), consolidation **non** faite (un message par facture, répétition seulement si définie).', 'O2', 'COL:C9 ERR:ACTION_MAX_ATTEMPTS_REACHED'),
      ('CO-11', 'L3', 'Actions manuelles : mêmes garde-fous, même plancher, même non-régression ; override avec audit ; niveau dans la plage du type.', 'O2', 'COL:C11 ERR:ACTION_APPROVAL_REQUIRED'),
      ('CO-12', 'L3', 'Gabarits par défaut en `DRAFT` : l’activation d’une automatisation exige des gabarits `ACTIVE` ; gabarit introuvable à l’exécution → `FAILED` sans réessai.', 'O2', 'COL:C12 ERR:TEMPLATE_UNAVAILABLE'),
      ('CO-13', 'L4', 'Rebond : action `DONE`, issue `BOUNCED`, alerte et tâche de suivi ; rapport de livraison idempotent.', 'O2', 'COL:C13 ENG:EC-04'),
      ('CO-14', 'L4', 'Envoi : tentatives 5 min / 30 min / 2 h avec revalidation à chacune ; erreur permanente = `FAILED` immédiat ; `EXECUTING` bloqué > 15 min repris ; aucun envoi dans une transaction de base ; clé fournisseur `{notification_id}:{attempt_no}`.', 'O4-G13', 'ENG:X13 ENG:X3 ENG:EC8 COL:CP4 COL:CP5 COL:CP6 COL:CP7'),
      ('CO-16', 'L3', 'Alerte responsable : une **notification interne** `MANAGER_ALERT` (une par membre du pool), dédupliquée par `{action_id}:{user_id}` ; jamais un type d’action ; les escalades de niveau 4–5 la produisent.', 'O2', 'INV:D5'),
      ('CO-15', 'L1', 'Principes : le Collection Engine ne décide jamais si agir ; une action porte son snapshot ; revalidation à chaque frontière.', 'O4-G15', 'COL:CP1 COL:CP2 COL:CP3 ENG:EC-11'),
  ])

# ------------------------------------------------------------------------------------------------ F
S('AT', 'F. Automation Engine',
  'Exécutions longues et datées : la difficulté est le temps, la reprise et l’absence d’effets rétroactifs.',
  [
      ('AT-01', 'L5', 'Une exécution longue et datée par (automatisation, sujet) : le gabarit par défaut déroule ses six étapes aux bonnes dates ; chaque étape se revalide.', 'O2', 'AUT:AU1 AUT:AP1 AUT:AP2'),
      ('AT-02', 'L0', 'Schéma de définition : les huit types d’étapes ; branches vers l’avant seulement (terminaison) ; `PAUSE` n’est pas une étape ; déclencheurs autorisés et sujets ; pas de `CASHFLOW_UPDATED`.', 'O2', 'AUT:AU2 AUT:AU3 AUT:AP6 INV:D2'),
      ('AT-03', 'L3', 'Grammaire du `trigger_key` : chaque source (événement, temps unique, temps récurrent, inscription, import, reprise) ; `occurrence = n.k` ; répétition bornée.', 'O2', 'AUT:AU4'),
      ('AT-04', 'L5', 'Non-rétroactivité : événement antérieur à `active_since` ; facture émise tardivement ; balayeur arrêté 30 h (rattrapé) et 5 jours (écarté et compté) ; événement de plus de 72 h écarté.', 'O4-G21', 'AUT:AP5 AUT:AU5 SM:S6'),
      ('AT-05', 'L1', '`LATEST_ONLY` : dernière étape **applicable** d’une séquence continue ; remontée si la dernière n’est pas applicable ; les précédentes `SUPERSEDED` ; **jamais une autorisation d’exécution** (repasse par Rule et Collection) ; imposé à la reprise, à l’import, à la ré-inscription.', 'O2', 'ENG:X15 ENG:P3'),
      ('AT-06', 'L4', 'Pause et reprise : chaque cause levée par son événement ; deux causes simultanées (une seule levée) ; reprise à l’étape courante revalidée ; alerte à 180 jours sans annulation.', 'O2', 'AUT:AP7'),
      ('AT-07', 'L3', 'Une seule exécution non terminale par (automatisation, sujet) : déclenchement pendant une exécution active → `SKIPPED` ; les états terminaux coexistent.', 'O4-G11', 'AUT:AU6 ERR:EXECUTION_RATE_LIMITED'),
      ('AT-08', 'L5', 'Ré-inscription : règlement annulé après la fin du parcours → nouvelle exécution, nouveau cycle, nouvelles clés de déduplication ; reprise manuelle d’un échec (`retry:{id}`).', 'O2', 'AUT:AU7'),
      ('AT-09', 'L3', 'Activation : `enrollment_mode` obligatoire ; préconditions ; aperçu = simulation **sans effet** (aucune écriture, aucun événement, aucune notification) ; vérification atomique de l’empreinte ; `active_since = as_of` de l’aperçu ; empreinte différente → `ENROLLMENT_PREVIEW_STALE`, **aucune inscription partielle** ; aperçu identique à l’exécution réelle rejouée.', 'O8', 'AUT:AU8 ERR:AUTOMATION_PRECONDITIONS_NOT_MET ERR:ENROLLMENT_PREVIEW_STALE INV:N13 ENG:P4'),
      ('AT-10', 'L4', 'Anti-boucles : définition (branches, répétitions), **ensemble actif** (A ↔ B refusé à l’activation), exécution (profondeur ≤ 20, 10 démarrages par sujet et par jour).', 'O4-G12', 'AUT:AU9 ERR:AUTOMATION_SET_LOOP_DETECTED'),
      ('AT-11', 'L5', 'Libération d’un lot de 5 000 factures : les 5 000 exécutions **existent** dès la libération (`WAITING`) ; au plus `release_max_per_day` démarrent par jour, dans l’ordre de priorité ; pause / reprise ; `RELEASED` = toutes créées et planifiées.', 'O4-G20', 'AUT:AU10 INV:N14'),
      ('AT-12', 'L6', 'Au moins une fois, effets idempotents : panne entre l’effet et l’écriture de la ligne d’étape ; deux workers sur la même exécution ; `Reaper` ; nouvelles tentatives 1 / 5 / 30 min ; isolation d’une exécution défaillante ; équité entre organisations.', 'O8', 'AUT:AU11 AUT:AP3 AUT:AP4'),
      ('AT-13', 'L2', 'Amendements de contrat : `active_since` (⇔ `ACTIVE`), index d’exécution unique, index d’import, grammaire du `trigger_key`.', 'O9', 'AUT:AU12'),
      ('AT-14', 'L4', 'Approbations en attente : `WAITING` jusqu’à `expires_at` ; décision qui réveille ; cible résolue → `TARGET_RESOLVED` ; explicabilité de chaque étape (`revalidation_result`).', 'O4-G16', 'AUT:AP7 AUT:AP8 ENG:EC-13 ERR:APPROVER_NOT_ELIGIBLE ERR:APPROVAL_ALREADY_DECIDED ERR:SELF_APPROVAL_FORBIDDEN ERR:APPROVAL_COMMENT_REQUIRED ERR:APPROVAL_EXPIRED'),
  ])

# ------------------------------------------------------------------------------------------------ G
S('RP', 'G. Risk, Priority, Cashflow',
  'Le modèle de référence (`reference_model/`) est l’oracle ; l’implémentation SQL est comparée à lui.',
  [
      ('RP-01', 'L1', '**Cas d’or de risque** G1 à G5 reproduits chiffre pour chiffre ; score maximal 100 ; monotonie de chaque facteur ; historique insuffisant = 0.', 'O1, O2', 'GOLD:G1 GOLD:G2 GOLD:G3 GOLD:G4 GOLD:G5 RPC:RP3 RPC:RP1 RPC:PA RPC:PB RPC:PG'),
      ('RP-02', 'L1', '**Cas d’or de priorité** P1 à P7 ; domaine 0–95 ; plafonds après stabilisation ; un plafond ne relève jamais un niveau ; le niveau publié est la référence suivante ; le signal de rapprochement ne change ni score ni niveau mais change le hash.', 'O1, O2', 'GOLD:P1 GOLD:P2 GOLD:P3 GOLD:P4 GOLD:P5 GOLD:P6 GOLD:P7 RPC:RP4 RPC:RP15 RPC:RP16 RPC:RP23'),
      ('RP-03', 'L1', '**Cas d’or de trésorerie** C1 à C10 (scénarios, échue / non échue, litige, promesse, retard long, non-alloué FIFO, non-alloué qui couvre tout).', 'O1, O2', 'GOLD:C1 GOLD:C2 GOLD:C3 GOLD:C4 GOLD:C5 GOLD:C6 GOLD:C7 GOLD:C8 GOLD:C9 GOLD:C10 RPC:RP5 RPC:RP11'),
      ('RP-04', 'L6', 'Propriétés du Cashflow : conservation par facture **et par client** ; réserve ≤ non-alloué ; aucune ligne `REALIZED` dans une prévision ; `pondéré` = arrondi décimal demi-haut ; probabilités dans [0, 1] ; déterminisme.', 'O7', 'RPC:CF1 RPC:CF2 RPC:CF3 RPC:CF4 RPC:CF5 RPC:CF6 RPC:RP18 RPC:RP19 RPC:RP20'),
      ('RP-05', 'L6', '`input_hash` : stable dans une tranche (17 → 18 jours), distinct entre tranches, sensible au niveau précédent ; contenu du snapshot **identique** pour deux valeurs brutes d’une même tranche ; Cashflow haché sur des entrées **brutes**.', 'O7', 'RPC:RP6 RPC:RP14 ENG:X17'),
      ('RP-06', 'L6', 'Hystérésis : séquences aléatoires oscillant autour d’un seuil ; jamais plus de changements qu’en son absence ; `RESULT` seulement sur changement de niveau publié.', 'O7', 'RPC:RP3 RPC:RP15'),
      ('RP-07', 'L4', '`RISK_CHANGED` → une demande de portée client → traitement par lots de 200 factures, reprenables, chacun idempotent ; un client à 50 000 factures ne produit pas de transaction unique ; pas de cycle Risk ↔ Priority.', 'O4-G17', 'RPC:RP21 RPC:RP13 RPC:PE'),
      ('RP-08', 'L4', 'Fraîcheur : `ProjectionDailyRefresh` (05:00 local) et `ProjectionSafetyNet` (2 h) ; un événement de rafraîchissement supprimé est réparé ; SLO mesurés (99 % avant 08:00, p99 ≤ 26 h, alerte à 36 h).', 'O8', 'RPC:RP9 RPC:RP22 RPC:RP7 JOB:ProjectionDailyRefresh JOB:ProjectionSafetyNet'),
      ('RP-09', 'L4', 'Reconstruction et mise à niveau de modèle : `RebuildProjection` reproduit exactement les projections courantes ; aperçu du nombre de changements de niveau ; `cause = MODEL_UPGRADE` regroupé.', 'O8', 'RPC:RP10 RPC:PC RPC:PD'),
      ('RP-10', 'L3', 'Run de trésorerie : au plus un `is_current` par triplet ; promotion atomique et **monotone** (un run retardataire ne remplace pas un plus récent) ; même `input_hash` → `REPLAY` ; runs planifiés (10 par jour) et événementiels regroupés sur 5 min.', 'O1', 'RPC:RP17 RPC:RP11 ERR:CASHFLOW_RUN_CONFLICT ERR:CASHFLOW_HORIZON_INVALID ERR:CASHFLOW_SCENARIO_INVALID ERR:CASHFLOW_INPUT_INCONSISTENT'),
      ('RP-11', 'L4', 'Faits ajoutés au Rule Engine (compte de factures soldées, paiements annulés, tendance, non-alloué, jours depuis la dernière action) : formules entières ; refresh_events définitifs.', 'O6', 'RPC:RP8 RPC:RP7'),
      ('RP-12', 'L3', 'Rétention des runs de trésorerie : 13 mois, dernier run mensuel des horizons 30 et 90 jours conservé ; archive, jamais suppression.', 'O4', 'RPC:RP12 RPC:RP2 INV:D8'),
      ('RP-13', 'L1', 'Modèles versionnés et sans paramètre d’organisation (hors montant critique) ; `risk_level` est un indicateur d’attention, jamais une probabilité ; aucune donnée inventée.', 'O1', 'RPC:PD RPC:PH RPC:PG'),
      ('RP-14', 'L4', 'Erreurs des moteurs de projection : modèle inconnu, concurrence rejouée.', 'O2', 'ERR:RISK_MODEL_UNKNOWN ERR:PRIORITY_MODEL_UNKNOWN ERR:CASHFLOW_MODEL_UNKNOWN ERR:ENGINE_INTERNAL_ERROR'),
      ('RP-15', 'L1', 'Principes de projection : fonction pure des sources ; un seul sens de dépendance ; convergence par événements `RESULT`.', 'O4-G17', 'RPC:PC RPC:PE RPC:PF'),
  ])

# ------------------------------------------------------------------------------------------------ H
S('SE', 'H. Sécurité, tenant, données personnelles, audit',
  '',
  [
      ('SE-01', 'L3', 'Tenant : chaque cas d’usage et chaque contrat appelé avec un sujet d’une autre organisation → `NOT_FOUND` (jamais 403), aucune ligne lue ; deux organisations simultanées ne se voient jamais.', 'O4-G01', 'INV:C2 ENG:X11 ERR:INSUFFICIENT_ROLE'),
      ('SE-02', 'L3', 'Verrou optimiste : deux modifications de la même version → `CONCURRENT_MODIFICATION` ; rejeu par le client ; `SERIALIZATION_FAILURE` rejoué de façon bornée.', 'O6', 'INV:C4 ENG:EC10 ERR:SERIALIZATION_FAILURE'),
      ('SE-03', 'L3', 'Clés d’idempotence : même clé et même contenu → première réponse ; contenu différent → `IDEMPOTENCY_KEY_REUSED`.', 'O4-G09', 'INV:C6 ERR:IDEMPOTENCY_KEY_REUSED TAB:idempotency_keys'),
      ('SE-04', 'L3', 'Organisation non active : aucune automatisation ni communication (`ORG_NOT_ACTIVE`) ; réactivation : reprise.', 'O2', 'INV:C7 ERR:ORG_NOT_ACTIVE'),
      ('SE-05', 'L3', 'Corrections : une donnée financière immuable ne se corrige que par annulation + nouvelle saisie (paiement mal saisi, facture erronée).', 'O4-G06', 'INV:C8'),
      ('SE-06', 'L3', 'Anonymisation : nom, téléphone, e-mail, textes libres, payloads de notification et `audit_logs.before/after` nettoyés ; **aucune colonne financière, date ou état modifié** (vérifié par empreinte avant/après) ; ligne d’audit `PII_ANONYMIZED` sans donnée personnelle ; archives froides incluses.', 'O4-G23', 'INV:D7 INV:C9'),
      ('SE-07', 'L3', 'Audit : commandes utilisateur ou automatisation, configuration, droits, suspensions, approbations, actions sensibles écrites dans la transaction ; transitions temporelles du Scheduler **absentes** de l’audit.', 'O4-G19', 'INV:D3 INV:C13'),
      ('SE-08', 'L3', 'Rôles : approbation seulement `MANAGER`+ avec limite suffisante ; personne ne s’approuve soi-même si la politique l’exige ; au moins un `OWNER` actif ; activation réservée à `OWNER`/`ADMIN`.', 'O2', 'INV:N13 ERR:LAST_OWNER_REQUIRED'),
      ('SE-09', 'L3', 'Erreurs d’objets financiers et d’import : chaque code produit par au moins un test avec sa classe et son indicateur de nouvelle tentative (voir porte ERR).', 'O2', 'ERR:ALLOCATION_EXCEEDS_INVOICE_OUTSTANDING ERR:ALLOCATION_EXCEEDS_PAYMENT_AVAILABLE ERR:ALLOCATION_CUSTOMER_MISMATCH ERR:ALLOCATION_CURRENCY_MISMATCH ERR:ALLOCATION_INVOICE_NOT_PAYABLE ERR:ALLOCATION_PAYMENT_REVERSED ERR:REVERSAL_EXCEEDS_ORIGINAL ERR:REVERSAL_REASON_REQUIRED ERR:PAYMENT_DUPLICATE_REFERENCE ERR:PAYMENT_AMOUNT_INVALID ERR:PAYMENT_CURRENCY_MISMATCH ERR:PAYMENT_DATE_IN_FUTURE ERR:PAYMENT_ALREADY_REVERSED ERR:PAYMENT_REVERSAL_REASON_REQUIRED'),
      ('SE-10', 'L3', 'Erreurs de facture, client, organisation, promesse et suspension.', 'O2', 'ERR:INVOICE_EMPTY ERR:INVOICE_TOTAL_MUST_BE_POSITIVE ERR:INVOICE_NUMBER_TAKEN ERR:INVOICE_FIELD_LOCKED ERR:INVOICE_HAS_PAYMENTS ERR:INVOICE_DATES_INVALID ERR:CUSTOMER_CODE_TAKEN ERR:CUSTOMER_INACTIVE ERR:CUSTOMER_ARCHIVED ERR:CUSTOMER_HAS_OPEN_INVOICES ERR:CONTACT_PRIMARY_CONFLICT ERR:CONTACT_INVALID_VALUE ERR:ORG_SLUG_TAKEN ERR:ORG_CURRENCY_LOCKED ERR:ORG_TIMEZONE_INVALID ERR:PROMISE_ALREADY_ACTIVE ERR:PROMISE_AMOUNT_EXCEEDS_OUTSTANDING ERR:PROMISE_AMOUNT_INVALID ERR:PROMISE_DATE_IN_PAST ERR:PROMISE_INVOICE_NOT_OPEN ERR:PROMISE_NOT_ACTIVE ERR:HOLD_OVERLAP ERR:HOLD_REASON_REQUIRED ERR:HOLD_TARGET_MISMATCH ERR:HOLD_NOT_ACTIVE ERR:INVALID_TRANSITION'),
      ('SE-11', 'L3', 'Erreurs de lot d’import.', 'O2', 'ERR:IMPORT_APPROVAL_REQUIRED ERR:IMPORT_BATCH_COMMITTED ERR:IMPORT_BATCH_NOT_READY ERR:IMPORT_FILE_ALREADY_IMPORTED ERR:IMPORT_NORMALIZATION_FAILED ERR:IMPORT_RELEASE_MODE_INVALID ERR:IMPORT_VALIDATION_FAILED'),
      ('SE-12', 'L0', 'Porte de couverture des erreurs : **chaque code de l’Annexe A** est produit par au moins un test qui vérifie sa classe HTTP et son indicateur de nouvelle tentative ; le registre est généré et vérifié en CI.', 'O5', 'ERR:*'),
      ('SE-13', 'L3', 'Course de création dédupliquée (R-12) : violation de la contrainte **déclarée** → `REPLAY` de l’objet occupant relu dans l’unité de reprise ; occupant sorti de l’index avant la relecture → `DEDUP_REPLAY_UNAVAILABLE` (`CONFLICT`, retryable), rien d’écrit, clé de requête non consommée, Domain non rappelé ; autre contrainte : non traduite (R12-B, B11).', 'O6', 'TD:19 ERR:DEDUP_REPLAY_UNAVAILABLE'),
  ])

# ------------------------------------------------------------------------------------------------ I
S('JB', 'I. Jobs planifiés et temps',
  'Contrat commun : idempotent par construction, verrou consultatif, isolation par organisation, fuseau de l’organisation, rattrapage borné.',
  [
      ('JB-01', 'L4', 'Contrat commun des jobs : deux instances simultanées → une seule agit ; l’échec d’une organisation n’arrête pas les autres ; un job rejoué sans effet ; métriques de retard émises.', 'O4-G09', 'ENG:EC-03 ENG:EC7'),
      ('JB-02', 'L4', 'Publication des événements : arriéré traité dans l’ordre d’`occurred_at` ; `FOR UPDATE SKIP LOCKED` ; publication idempotente.', 'O8', 'JOB:OutboxPublisher'),
      ('JB-03', 'L4', 'Cycle de vie des factures : transitions dues rattrapées après arrêt (sauts permis), une seule fois, dans le fuseau de l’organisation ; heure d’été ; changement de date locale.', 'O3', 'JOB:InvoiceLifecycleScan INV:C10'),
      ('JB-04', 'L4', 'Promesses rompues, expirations de suspension et d’approbation : gardes d’état, rattrapage.', 'O3', 'JOB:PromiseBreachScan JOB:HoldExpiryScan JOB:ApprovalExpiryScan'),
      ('JB-05', 'L4', 'Déclencheurs temporels : fenêtre `(dernier balayage, as_of]`, tolérance de 48 h, aucune double exécution.', 'O2', 'JOB:TimeTriggerScanner'),
      ('JB-06', 'L4', 'Workers d’exécution et d’actions : sondage, verrouillage, équité par organisation, plafond de concurrence, reprise des tâches bloquées.', 'O6', 'JOB:ExecutionWorker JOB:ExecuteDueActions JOB:Reaper'),
      ('JB-07', 'L4', 'Import : libérateur et exécuteur d’inscription (étalement, pause, reprise).', 'O4-G20', 'JOB:ImportReleaser JOB:EnrollmentRunner'),
      ('JB-08', 'L4', 'Trésorerie planifiée : 05:00 local par organisation, regroupement des demandes.', 'O1', 'JOB:CashflowScheduler'),
      ('JB-09', 'L4', 'Purges techniques : `idempotency_keys` expirées, `event_receipts` de plus de 90 jours ; aucune donnée métier purgée.', 'O4', 'JOB:TechnicalPurge'),
  ])

# ------------------------------------------------------------------------------------------------ J
S('IM', 'J. Import historique',
  '',
  [
      ('IM-01', 'L5', 'Séquence complète : import → validation → lot prêt → approbation → engagement → normalisation → événements des moteurs → libération → exécution contrôlée ; 5 000 factures ≠ 5 000 relances immédiates.', 'O2', 'INV:N14 INV:D9 SM:14'),
      ('IM-02', 'L3', 'Deux chemins de création : `CreateInvoice` produit toujours un `DRAFT` ; `ImportHistoricalInvoice` reconstruit l’état historique avec son historique ; aucun autre chemin ne crée une facture hors brouillon.', 'O4-G04', 'INV:D9'),
      ('IM-03', 'L3', 'Normalisation tout ou rien : un échec ne laisse aucune donnée ; toutes les entités portent `import_batch_id` ; un lot engagé n’est jamais annulé ni supprimé ; le staging figé.', 'O4', 'INV:N14'),
  ])

# ------------------------------------------------------------------------------------------------ K
S('E2E', 'K. Scénarios de bout en bout (horloge virtuelle)',
  'Chaque scénario est rejoué avec **tous les vérificateurs globaux** (§4) exécutés à la fin et après chaque jour simulé.',
  [
      ('E2E-01', 'L5', 'Cycle de vie complet d’une facture sans incident : émission, rappels, paiement, projections, trésorerie.', 'O4-G*', 'INV:D4'),
      ('E2E-02', 'L5', 'Paiement partiel puis solde, puis annulation du règlement : nouveau cycle, nouvelles relances, priorité et risque recalculés, trésorerie recalculée.', 'O4-G*', 'EVT:INVOICE_PARTIALLY_PAID EVT:INVOICE_SETTLEMENT_REVERTED EVT:PAYMENT_ALLOCATION_REVERSED EVT:PAYMENT_REVERSED'),
      ('E2E-03', 'L5', 'Litige partiel puis résolu ; litige total ; procédure d’un litige fondé.', 'O4-G*', 'EVT:INVOICE_DISPUTED EVT:INVOICE_DISPUTE_RESOLVED EVT:INVOICE_VOIDED'),
      ('E2E-04', 'L5', 'Promesse créée, tenue, rompue ; suspension des relances puis reprise ; effet sur le risque.', 'O4-G*', 'EVT:PROMISE_CREATED EVT:PROMISE_FULFILLED EVT:PROMISE_CANCELLED'),
      ('E2E-05', 'L5', 'Suspension manuelle (`NEGOTIATION`, `LEGAL`) : pause, libération, expiration ; override refusé pour `LEGAL`.', 'O4-G*', 'EVT:COLLECTION_HOLD_PLACED EVT:COLLECTION_HOLD_RELEASED'),
      ('E2E-06', 'L5', 'Client désactivé puis archivé en cours de recouvrement ; reversal qui rouvre une facture d’un client archivé (alerte, aucune relance, aucune réactivation automatique).', 'O4-G*', 'EVT:CUSTOMER_DEACTIVATED EVT:CUSTOMER_ARCHIVED EVT:CUSTOMER_REACTIVATED'),
      ('E2E-07', 'L5', 'Approbation : accordée, refusée, expirée, cible payée pendant l’attente.', 'O4-G*', 'EVT:APPROVAL_REQUESTED EVT:APPROVAL_GRANTED EVT:APPROVAL_REJECTED'),
      ('E2E-08', 'L5', 'Envoi : succès, erreur transitoire puis succès, erreurs épuisées, erreur permanente, repli humain, rebond.', 'O4-G*', 'EVT:NOTIFICATION_CREATED EVT:NOTIFICATION_SENT EVT:NOTIFICATION_FAILED EVT:COLLECTION_ACTION_FAILED EVT:COLLECTION_ACTION_SUPPRESSED'),
      ('E2E-09', 'L5', 'Activation d’une automatisation sur 300 factures existantes : aperçu, empreinte, `FUTURE_ONLY` puis `LATEST_STEP`, aperçu périmé.', 'O4-G*', 'EVT:AUTOMATION_ACTIVATED EVT:AUTOMATION_EXECUTION_STARTED'),
      ('E2E-10', 'L5', 'Import de 5 000 factures dont 1 200 en retard, puis libération étalée sur plusieurs jours, avec pause et reprise.', 'O4-G*', 'EVT:IMPORT_BATCH_UPLOADED EVT:IMPORT_BATCH_NORMALIZED EVT:IMPORT_BATCH_COMMITTED'),
      ('E2E-11', 'L5', 'Automatisation mise en pause, désactivée, réactivée ; changement de version pendant des exécutions en vol ; retour arrière par nouvelle version.', 'O4-G*', 'EVT:AUTOMATION_PAUSED EVT:AUTOMATION_DISABLED EVT:AUTOMATION_EXECUTION_COMPLETED EVT:AUTOMATION_EXECUTION_CANCELLED'),
      ('E2E-12', 'L5', 'Panne du balayeur 30 h et 5 jours ; panne de worker au milieu d’une étape ; événements dupliqués, perdus, en désordre ; `DEAD` puis rejeu.', 'O4-G*', 'EVT:INVOICE_DUE_SOON EVT:INVOICE_DUE'),
      ('E2E-13', 'L5', 'Paiement non alloué : trésorerie (réserve FIFO), signal de rapprochement, allocation ultérieure ; aucune double prévision à aucun moment.', 'O4-G18', 'EVT:PAYMENT_CREATED'),
      ('E2E-14', 'L5', 'Cascade de projections : `INVOICE_OVERDUE` → risque → `RISK_CHANGED` → priorité par lots → `PRIORITY_CHANGED` → automatisations sensibles ; barrière de fraîcheur ; hystérésis.', 'O4-G17', ''),
      ('E2E-15', 'L5', 'Deux organisations en parallèle, mêmes numéros de facture et mêmes codes clients : aucune interférence, aucune fuite ; suspension de l’une sans effet sur l’autre.', 'O4-G01', 'EVT:ORGANIZATION_SUSPENDED EVT:ORGANIZATION_REACTIVATED'),
      ('E2E-16', 'L5', 'Anonymisation d’un contact et d’un client personne physique en plein recouvrement ; partition d’audit archivée.', 'O4-G23', 'EVT:CUSTOMER_CONTACT_UPDATED'),
      ('E2E-17', 'L5', 'Cycle de vie de l’organisation : création atomique (réglages, `OWNER`, abonnement d’essai, automatisations modèles en `DRAFT`), modification des réglages, création et modification de clients, abonnement expiré, membre retiré, dernier `OWNER` protégé, changement de plan.', 'O4-G*', 'EVT:SUBSCRIPTION_CHANGED EVT:ORGANIZATION_CREATED EVT:ORGANIZATION_UPDATED EVT:ORG_SETTINGS_CHANGED EVT:CUSTOMER_CREATED EVT:CUSTOMER_UPDATED'),
      ('E2E-18', 'L5', 'Facture émise en retard, impayée : rattrapage immédiat, exécution, niveau plancher 3, escalade.', 'O4-G*', 'EVT:INVOICE_CREATED EVT:INVOICE_DUE'),
      ('E2E-19', 'L5', 'Facture annulée avant émission (`CANCELLED`) et facture annulée après émission (`VOID`) ; effets sur promesses, actions, exécutions ; actions proposées, planifiées puis annulées.', 'O4-G*', 'EVT:INVOICE_CANCELLED EVT:COLLECTION_ACTION_PROPOSED EVT:COLLECTION_ACTION_SCHEDULED EVT:COLLECTION_ACTION_CANCELLED'),
      ('E2E-20', 'L5', 'Scénarios courts complémentaires qui produisent les événements du catalogue non déclenchés plus haut : création d’une automatisation et de ses versions, archivage, exécution échouée, lot d’import prêt, approuvé, en échec ou annulé, clôture d’une organisation, ajout d’un contact, demandes de recalcul regroupées.', 'O4-G*', 'EVT:RISK_RECALCULATION_REQUESTED EVT:PRIORITY_RECALCULATION_REQUESTED EVT:CASHFLOW_RECALCULATION_REQUESTED EVT:AUTOMATION_CREATED EVT:AUTOMATION_VERSION_CREATED EVT:AUTOMATION_ARCHIVED EVT:AUTOMATION_EXECUTION_FAILED EVT:IMPORT_BATCH_READY EVT:IMPORT_BATCH_APPROVED EVT:IMPORT_BATCH_FAILED EVT:IMPORT_BATCH_CANCELLED EVT:ORGANIZATION_CLOSED EVT:CUSTOMER_CONTACT_ADDED EVT:INVOICE_DISPUTED EVT:PAYMENT_CREATED EVT:PROMISE_BROKEN EVT:COLLECTION_ACTION_EXECUTED EVT:APPROVAL_REQUESTED EVT:COLLECTION_HOLD_RELEASED'),
  ])

# ------------------------------------------------------------------------------------------------ L
S('CH', 'L. Chaos et résilience',
  'Injection de fautes dans le harnais (§3) ; les vérificateurs globaux doivent rester verts.',
  [
      ('CH-01', 'L6', 'Événements dupliqués (1 à 5 fois), perdus (échantillon), retardés, réordonnés ; état final identique à la livraison parfaite après reprise.', 'O8', 'ENG:X6 ENG:X14'),
      ('CH-02', 'L6', 'Panne du processus entre chaque instruction d’un cas d’usage (transaction avortée) : tout ou rien, aucun événement orphelin.', 'O4-G07', 'INV:C5 ENG:X8'),
      ('CH-03', 'L6', 'Fournisseur d’envoi : délai dépassé, réponse perdue après acceptation, rapport de livraison en double.', 'O4-G13', 'ENG:EC-04'),
      ('CH-04', 'L6', 'Concurrence : deux allocations, deux réclamations de tâche, deux activations, deux promotions de run, deux recalculs du même client, verrous dans l’ordre global (aucun interblocage).', 'O4-G22', 'ENG:EC5 ENG:EC-05'),
      ('CH-05', 'L6', 'Base : échec de sérialisation, perte de connexion en milieu de lot, partition manquante.', 'O4', 'ENG:EC10'),
      ('CH-06', 'L6', 'Horloge : décalage entre serveurs, saut d’heure d’été, passage de minuit dans un fuseau ; aucune lecture d’horloge hors `Clock`.', 'O4-G24', 'ENG:EC3'),
      ('CH-07', 'L6', 'Charge : rafale de 10 000 événements pour une organisation pendant qu’une autre s’exécute ; équité, aucun effet sur l’autre.', 'O4', 'JOB:ExecutionWorker'),
  ])

# ------------------------------------------------------------------------------------------------ M
S('PF', 'M. Performance et volumétrie',
  'Les seuils chiffrés sont fixés au banc d’essai de l’architecture technique ; la matrice impose **les scénarios et les mesures**.',
  [
      ('PF-01', 'L7', 'Évaluation par lots : 5 000 factures évaluées par le Rule Engine ; nombre de requêtes par famille de faits (jamais une par facture) ; durée.', 'O6', 'RULE:P6'),
      ('PF-02', 'L7', 'Recalcul complet : 5 000 clients et 50 000 factures (risque, priorité) ; un client à 50 000 factures ouvertes ; taille et retard des lots.', 'O1', 'RPC:RP21'),
      ('PF-03', 'L7', 'Run de trésorerie et faits sur 12 mois glissants : index, plan d’exécution, durée.', 'O1', 'RPC:RP5'),
      ('PF-04', 'L7', 'Débit de l’outbox et des handlers ; retard de publication ; volume des partitions.', 'O4', 'JOB:OutboxPublisher'),
      ('PF-05', 'L7', 'File de travail des collecteurs sur 50 000 éléments (tri total, pagination).', 'O6', 'RPC:RP4'),
  ])

# ------------------------------------------------------------------------------------------------ N
S('AR', 'N. Architecture et contrats d’interface',
  '',
  [
      ('AR-04', 'L0', '**Exceptions à « un agrégat par transaction »** : analyse statique et journal des transactions : seules `AllocatePayment`, `ReverseAllocation`, `ReversePayment` et `NormalizeImportBatch` écrivent dans plusieurs agrégats (`CreateOrganization` n’en fait plus partie : TD59) ; toute autre écriture inter-agrégats passe par un événement.', 'O4', 'INV:C12 ENG:EC1'),
      ('AR-01', 'L0', '**Tests d’architecture** : règles DR1 à DR9 exprimées comme règles d’import ; le Domain n’importe ni Django, ni Redis, ni un fournisseur ; aucun module ne lit les tables d’un autre ; aucun appel ascendant ; aucun cycle ; une violation bloque la fusion.', 'O4', 'ENG:EC9 ENG:DR1 ENG:DR2 ENG:DR3 ENG:DR4 ENG:DR5 ENG:DR6 ENG:DR7 ENG:DR8 ENG:DR9 INV:C1'),
      ('AR-02', 'L4', 'Contrats d’interface EC-05 à EC-13 : chaque contrat testé sur entrée, sortie, préconditions, erreurs, idempotence, transaction, événements (tests pilotés par les consommateurs).', 'O5', 'ENG:EC-06 ENG:EC-07 ENG:EC-08 ENG:EC-09 ENG:EC-10 ENG:EC-12 ENG:EC4 ENG:EC8'),
      ('AR-03', 'L0', 'Invariants inter-moteurs X1 à X14 : chacun vérifié par au moins un vérificateur global ou une règle d’architecture.', 'O4', 'ENG:X2 ENG:X4 ENG:X5 ENG:X3'),
  ])

# ------------------------------------------------------------------------------------------------ O
S('RC', 'O. Rapprochement : paiement non alloué et barrière de recouvrement (Collection V1.2)',
  'La barrière ne présume rien : elle suspend les factures candidates pendant une fenêtre bornée. Ces tests s’appuient sur `reconciliation_state` du modèle de référence et sur les cas d’or `R1` à `R10`.',
  [
      ('RC-01', 'L1', 'Qualification Q1 à Q5 : paiement candidat, antérieur à l’émission, alloué, annulé, partiel (reliquat), jour férié dans la fenêtre, deux paiements, autre devise, facture fermée, paiement enregistré tard.', 'O1, O2', 'GOLD:R1 GOLD:R2 GOLD:R3 GOLD:R4 GOLD:R5 GOLD:R6 GOLD:R7 GOLD:R8 GOLD:R9 GOLD:R10 RCN:RN2 RCN:RN11'),
      ('RC-02', 'L1', 'Calendrier et fuseau (W1 à W7) : jours ouvrés, jours fériés ; départ = date **locale** d’enregistrement (pas la date UTC, pas la date de valeur : R11, R12) ; barrière active jusqu’à la fin du dernier jour local et périmée dès le jour local suivant (R13) ; changement d’heure (R14) ; résultat identique pour toute minute d’une journée locale ; le dernier jour de suspension est toujours un jour ouvré ; la barrière ne revient pas avec le seul temps.', 'O7', 'RCN:RN5 RCN:RN12 GOLD:R11 GOLD:R12 GOLD:R13 GOLD:R14'),
      ('RC-03', 'L1', 'Exception n° 13 `RECONCILIATION_PENDING` : suspension automatique ; action manuelle avec `OverrideGrant` `COLLECTOR` ; **jamais** contournable par une automatisation ; ordre avec `PAID` et `HOLD_ACTIVE` ; notifications internes exemptées ; fenêtre écoulée → `PROCEED` avec `reconciliation_stale` ; **grant revérifié à l’exécution** (G4 à G6) : acteur désactivé, rôle rétrogradé, organisation suspendue, hold `LEGAL` apparu, autre exception apparue.', 'O2', 'RCN:RN3 RCN:RN4 RPC:RP23'),
      ('RC-04', 'L4', '**Aucune présomption** : deux factures (100 000 et 500 000) et un paiement de 100 000 non alloué : **les deux** sont suspendues ; après allocation complète à l’une, l’autre est levée ; jamais de choix implicite.', 'O2', 'RCN:RN1 RCN:RN2'),
      ('RC-05', 'L4', 'États d’action : `SCHEDULED` suspendue à l’exécution ; `PENDING_APPROVAL` → `SUPPRESSED` ; `EXECUTING` non interrompue ; `DONE` inchangée ; clé de déduplication libérée puis nouvelle action créée à la levée.', 'O3', 'RCN:RN4 RCN:RN10'),
      ('RC-06', 'L4', 'Exécutions : `PAUSED` (`RECONCILIATION_PENDING`) à la revalidation ; reprise sur `PAYMENT_ALLOCATED`, `PAYMENT_REVERSED` et fin de fenêtre ; reste en pause si un second paiement qualifie ; exécution `WAITING` évaluée seulement à son réveil ; **une automatisation ne crée ni ne consomme jamais de grant** (G7).', 'O2', 'RCN:RN6'),
      ('RC-07', 'L4', 'Évolution : allocation partielle (barrière sur le reliquat), complète, allocation annulée (la barrière peut réapparaître), paiement annulé, nouveau paiement, deux paiements aux fenêtres différentes.', 'O2', 'RCN:RN6 RCN:RN2'),
      ('RC-08', 'L4', 'Job `ReconciliationWindowScan` : revue à +1 jour ouvré, alerte en fin de fenêtre, idempotence (notifications dédupliquées par paiement et par membre), rattrapage après un arrêt, isolation par organisation ; **même résultat quelle que soit l’heure du passage** (00:05 ou 23:55, W6).', 'O4-G09', 'RCN:RN7 RCN:RN5 JOB:ReconciliationWindowScan'),
      ('RC-09', 'L3', 'Auditabilité : `decision_snapshot` avec le bloc `reconciliation` (identifiants, montants, dates, sans donnée personnelle) ; audit d’un contournement manuel à la création **et** à chaque vérification à l’exécution (`decision_snapshot` immuable) ; aucune donnée personnelle dans les notifications de revue.', 'O4-G16', 'RCN:RN9'),
      ('RC-10', 'L4', 'Signal de Priority aligné sur le fait `invoice.reconciliation_pending` ; aucun effet sur score ni niveau ; hash modifié ; bascule à la fin de la fenêtre par le rafraîchissement quotidien.', 'O1', 'RCN:RN8'),
      ('RC-11', 'L5', 'Bout en bout : paiement le lundi, rappel prévu le mardi (suspendu), allocation le mercredi (reprise, nouveau rappel) ; cas sans rapprochement : fenêtre écoulée le vendredi, relance et alerte aux managers ; paiement importé historique sans barrière.', 'O4-G*', 'RCN:RN5 RCN:RN11'),
      ('RC-12', 'L6', 'Propriétés du modèle de référence (pas de présomption, montant en attente ≤ non alloué, fenêtre bornée) et test différentiel du fait SQL contre `reconciliation_state` sur données aléatoires.', 'O6', 'RCN:RN1 RCN:RN12'),
  ])

# ------------------------------------------------------------------------------------------------ P
S('BL', 'P. Réservé : abonnement et autorisations (Billing)',
  '',
  [
      ('BL-01', 'L4', '**(À spécifier avec le module Billing)** Lien entre l’état de l’abonnement (`PAST_DUE`, `EXPIRED`, `CANCELLED`) et les autorisations : automatisations, communications, création de données.', 'O2', 'SM:S7'),
  ])


# ------------------------------------------------------------------------------------------------ Q (générée depuis TECHNICAL_ARCHITECTURE_V1.md)
def _ta_rows():
    import io as _io
    import os as _os
    import re as _re
    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'TECHNICAL_ARCHITECTURE_V1.md')
    with _io.open(path, encoding='utf-8') as f:
        ta = f.read()
    extra = {'TA-07': 'ERR:TENANT_CONTEXT_MISSING', 'TA-08': 'ERR:DB_INVARIANT_VIOLATED', 'TA-12': 'ERR:LOCK_ORDER_VIOLATION',
             'TA-35': 'EVT:USER_CREATED EVT:USER_STATUS_CHANGED EVT:MEMBER_ADDED EVT:MEMBER_ROLE_CHANGED EVT:MEMBER_REMOVED',
             'TA-36': 'SM:S10'}
    rows = []
    for tid, level, content, refs in _re.findall(r'^\| \*\*(TA-\d+)\*\* \| (L\d) \| (.*) \| ([^|]*) \|$', ta, _re.M):
        tokens = set()
        for m in _re.finditer(r'\b(TD|TI)(\d+)(?:\s*à\s*(?:TD|TI)?(\d+))?', refs):
            a, b = int(m.group(2)), int(m.group(3) or m.group(2))
            tokens |= {'%s:%d' % (m.group(1), i) for i in range(a, b + 1)}
        for m in _re.finditer(r'AR-(\d+)(?:\s*à\s*AR-(\d+))?', refs):
            a, b = int(m.group(1)), int(m.group(2) or m.group(1))
            tokens |= {'AR:%02d' % i for i in range(a, b + 1)}
        toks = ' '.join(sorted(tokens, key=lambda t: (t.split(':')[0], int(t.split(':')[1])))) + (' ' + extra[tid] if tid in extra else '')
        rows.append((tid, level, content, 'O9' if level == 'L2' else 'O5', toks))
    return rows


S('TA', 'Q. Architecture technique (TD1 à TD59, registres, PostgreSQL réel)',
  'Famille **générée** depuis `TECHNICAL_ARCHITECTURE_V1.md` (tableau « Nouvelle famille TA ») : les décisions `TD`, les invariants `TI` et les règles `AR` de l’architecture technique sont des éléments de l’univers, couverts comme les autres. Les portes `AR-*` sont produites par `architecture_registry/build_registry.py` ; les expériences PostgreSQL par `pg_experiments.py`.',
  _ta_rows())
