# VERQIA — Collection Engine V1.2 : barrière de rapprochement (RP23)

Références : Data Contract V1.3, Invariants V1.2, State Machines V1, Rule Engine V1.1, Collection Engine V1.1, Automation Engine V1.1, Engine Contracts V1.1, Risk / Priority / Cashflow V1.1, Global Test Matrix V1.
Statut : **RN1 à RN12 validées** (RN3 et RN5 verrouillées avec deux précisions : §1.3 et §3.3). Les décisions sont regroupées en §12. Les amendements aux documents figés sont listés en §12.

Objet : définir la **machine de décision** qui répond à une seule question de recouvrement : *« VERQIA a-t-il le droit de contacter ou de relancer ce client pour cette facture, alors qu'un paiement reçu n'est pas encore affecté ? »*

**Vérification.** La détection, la qualification et la fenêtre de suspension sont implémentées dans `reference_model/verqia_models.py` (fonctions `reconciliation_state`, `window_last_day`, `add_business_days`). Les exemples de ce document sont la sortie de ce modèle (14 cas d'or `R1` à `R14` dans `golden_cases.json`, dont quatre à partir d'**instants** et de fuseaux) ; 10 tests de propriétés supplémentaires portent le modèle à **35 tests**, tous verts. Les cas à fuseau utilisent la base de fuseaux IANA (`zoneinfo`, paquet `tzdata` sous Windows).

---

## 0. Principes

| Responsabilité | Rôle |
|---|---|
| **Risk** | niveau de risque : inchangé par un paiement non alloué |
| **Priority** | urgence opérationnelle : ne change ni de score ni de niveau ; expose un **signal** |
| **Cashflow** | projection monétaire : **présume** (réserve FIFO) pour prévoir avec prudence |
| **Collection** | décision d'action : **ne présume pas** ; elle **suspend** |

> **Cashflow présume pour prévoir ; Collection ne présume pas pour agir.**

Un paiement non alloué **ne signifie pas** « facture payée ». Le moteur ne sait pas si l'argent concerne cette facture, une autre, ou une facture future. Il ne transforme donc pas cette **incertitude de rapprochement** en **conclusion métier** : il **suspend** les actions qui pourraient être inappropriées, le temps qu'un humain tranche, et il rend la situation **visible** et **bornée dans le temps**.

Trois notions à ne jamais confondre :

| Notion | Sens |
|---|---|
| `OUTSTANDING` | montant réellement dû selon la source de vérité (allocations confirmées) |
| `UNALLOCATED` | argent effectivement reçu, pas encore affecté |
| `RECONCILIATION_PENDING` | **problème opérationnel** à résoudre, qui peut suspendre certaines actions |

---

## 1. Détection et qualification

### 1.1 Qualification d'un paiement pour une facture

Un paiement est **potentiellement applicable** à une facture si **toutes** les conditions suivantes sont vraies :

| # | Condition | Source |
|---|---|---|
| **Q1** | il reste un montant **non alloué** : `amount_minor − allocated_minor > 0` et `status` ∈ {`RECEIVED`, `PARTIALLY_ALLOCATED`} (donc aucune allocation existante ne l'épuise) | `payments.amount_minor`, `payments.allocated_minor`, `payments.status` |
| **Q2** | le paiement n'est **pas annulé** (`status ≠ REVERSED`) | `payments.status` |
| **Q3** | **même client** et **devise compatible** avec la facture | `payments.customer_id`, `payments.currency`, `invoices.currency` |
| **Q4** | **période compatible** : la facture est **ouverte** et a été émise au plus tard à la date de valeur du paiement (`invoices.issue_date <= payments.value_date`) : un paiement daté d'avant l'émission ne peut pas la régler | `invoices.issue_date`, `payments.value_date` |
| **Q5** | la **fenêtre de suspension** n'est pas écoulée (§1.3) | `payments.created_at`, calendrier de l'organisation |

Q3 est garanti à l'écriture pour toute allocation (clés étrangères composites) ; il est vérifié ici parce qu'un paiement d'un autre client ou d'une autre devise ne doit jamais suspendre une facture.

### 1.2 Faits produits (Rule Engine)

| Fait | Type | Définition |
|---|---|---|
| `invoice.reconciliation_pending` | bool `LIVE` | au moins un paiement satisfait Q1 à Q5 pour cette facture |
| `invoice.reconciliation_pending_minor` | money `LIVE` | somme des montants **non alloués** des paiements qualifiants (valeur brute : lue en direct par l'interface, jamais stockée dans un snapshot déterminant, RP14) |

Ces deux faits remplacent, pour la priorité, la définition provisoire `customer.unallocated_payment_minor > 0` du signal (§9).

### 1.3 Fenêtre de suspension (RN5, verrouillée)

**Règle unique** : la fenêtre est une fonction **de dates locales et du calendrier de l'organisation**, jamais d'une durée en heures ni de l'instant où un traitement s'exécute.

| # | Règle |
|---|---|
| **W1** | **Départ** : `payments.created_at` (instant UTC d'enregistrement dans VERQIA), **converti dans le fuseau de l'organisation**. On retient la **date locale** ; la date UTC n'est jamais utilisée. La date de valeur ne compte pas : un paiement saisi aujourd'hui avec la date de valeur du mois dernier reste un paiement que l'organisation vient de découvrir |
| **W2** | **Durée** : `N` **jours ouvrés** (défaut **3**, `org_settings.extra.reconciliation_hold_business_days`), comptés **uniquement** avec le calendrier de l'organisation (jours ouvrés et jours fériés). Aucun autre calendrier, aucun décalage en heures |
| **W3** | **Dernier jour de suspension** (inclus) = `ajouter_jours_ouvrés(date locale d'enregistrement, N)`. Si la date locale d'enregistrement n'est pas un jour ouvré, le compte part du premier jour ouvré qui la suit (cas d'or `R11`) |
| **W4** | **Barrière active jusqu'à la fin du dernier jour calculé**, en heure locale : elle existe pour tout instant dont la **date locale** est ≤ dernier jour |
| **W5** | **`stale` dès le jour local suivant** : la barrière est levée et le paiement est périmé à partir de **minuit local** qui suit le dernier jour, calendaire même si ce jour-là n'est pas ouvré. La levée décide seulement qu'aucune suspension ne subsiste ; elle ne décide pas du créneau d'envoi |
| **W6** | **Indépendance vis-à-vis du job** : l'état est calculé à partir de `(paiement, calendrier, fuseau, date locale de l'instant d'évaluation)`. Le fait est identique pour toute minute d'une même journée locale. Le job horaire **n'établit pas** l'état : il en **matérialise les conséquences** (notification, reprise) ; un passage à 00:05 ou à 23:55 produit la même décision. Les points de revalidation (création, exécution, réveil) appliquent la **même** fonction |
| **W7** | **Heure d'été et d'hiver** : la date locale vient de la base de fuseaux, jamais d'une addition de 24 heures ; la fin de la fenêtre peut donc tomber à 22:00 UTC un jour et à 23:00 UTC un autre (cas d'or `R14`) |
| **W8** | **Revue** : un jour ouvré après la date locale d'enregistrement, une notification de revue est due (§6) |

### 1.4 Cas particuliers (comportement voulu)

| Cas | Effet sur la décision |
|---|---|
| Paiement **≥** restant dû de la facture | suspension (la facture est **peut-être** réglée) ; pas de conclusion |
| Paiement **<** restant dû | suspension (paiement partiel possible) |
| **Plusieurs factures candidates** | **toutes** les factures candidates sont suspendues ; aucune n'est choisie à la place d'une autre |
| **Aucune facture candidate** (paiement d'avant toute émission, autre devise, factures fermées) | aucune suspension |
| Paiement **entièrement alloué**, **annulé** (`REVERSED`), ou **hors fenêtre** | aucune suspension ; hors fenêtre : marqué **périmé** (`stale`) et signalé (§6) |
| Allocation **partielle** | la barrière subsiste pour le **reliquat** non alloué |
| Plusieurs paiements non alloués | les montants s'additionnent ; chaque paiement a sa propre fenêtre |
| Paiement **importé** d'un historique ancien | hors fenêtre dès l'import : aucune barrière (l'import ne bloque pas le recouvrement) |

---

## 2. Portée : facture ou client ?

C'est la décision structurante de V1.2. Quatre options ont été comparées :

| Option | Principe | Fausse relance | Sur-blocage | Transparence |
|---|---|---|---|---|
| **A. Client entier** | tout paiement non alloué suspend **toutes** les actions du client | non | **fort** (un petit reliquat bloque tout) | simple |
| **B. Facture par FIFO** | on présume que le paiement règle la facture la plus ancienne et on ne suspend que celle-là | **oui** : si le paiement visait une autre facture, on relance la bonne facture réglée | faible | trompeuse (présomption cachée) |
| **C. Seuil de couverture** | on suspend seulement les factures que le paiement pourrait régler entièrement | oui pour un paiement partiel | faible | moyenne |
| **D. Candidature prudente** *(retenue)* | on suspend **chaque facture candidate** (Q1 à Q5), sans choisir laquelle, dans une **fenêtre bornée** | **non** | **borné** par la fenêtre et par Q4 | totale (chaque suspension nomme ses paiements) |

**Choix : D.** La barrière est **par facture** (chaque facture est évaluée avec ses propres candidats), mais la **détection** part du client (ses paiements non alloués) et la **candidature** est prudente. Elle ne présume rien, donc ne peut pas produire une relance sur une facture que le paiement visait ; et elle est bornée, donc ne peut pas geler le recouvrement d'un client indéfiniment (l'inconvénient de l'option A).

**Pourquoi Collection ne réutilise pas la réserve FIFO de Cashflow.** La réserve FIFO est une **présomption de prévision** : si elle est fausse, la prévision est prudente (sous-estimée). Une présomption de **contact** fausse a un coût différent : relancer un client qui vient de payer.

---

## 3. Décision

### 3.1 Où vit la règle

`RECONCILIATION_PENDING` devient une **exception intégrée du Rule Engine** (n° 13), pas une règle configurable et pas une barrière propre au Collection Engine :

- c'est une **protection** contre un contact inapproprié, donc L1 (non désactivable par une définition, P4) ;
- une barrière propre à Collection dupliquerait la fonction unique de garde-fous que Collection et Automation appellent déjà ;
- elle fournit une explication (`primary_exception`, trace, faits) par le même mécanisme que les 12 autres.

| Élément | Valeur |
|---|---|
| Code | `RECONCILIATION_PENDING` |
| Condition d'échec | `invoice.reconciliation_pending` |
| Classe | **métier** |
| Ordre | n° 13 (numéro ajouté à la fin pour ne pas renuméroter les 12 existants ; l'ordre ne fixe que le code retenu quand plusieurs exceptions échouent) |
| S'applique à | les quatre types d'action (`REMINDER`, `CALL_TASK`, `FOLLOW_UP`, `ESCALATION`), y compris manuels |
| Contournement | **manuel seulement**, avec `OverrideGrant` (rôle minimal `COLLECTOR`, motif obligatoire), **vérifié à la création puis de nouveau à l'exécution** (§3.3) ; **jamais** créé ni consommé par une automatisation |
| Exemptions | notifications **internes** (dont la revue de rapprochement) et demandes de recalcul, soumises à la seule exception 1 |

### 3.2 Correspondance avec les issues demandées

| Issue envisagée | Traitement retenu |
|---|---|
| `PROCEED` | aucun paiement potentiellement applicable (ou fenêtre écoulée) : la décision suit son cours |
| `DEFER` | **non utilisé** pour cette barrière : la levée dépend d'un acte humain (affectation), pas d'un créneau connu ; les autres exceptions métier n'utilisent pas `DEFER` non plus |
| `SUPPRESS` | **action** : `SUPPRESSED` avec `suppression_code = RECONCILIATION_PENDING` ; **exécution** : `PAUSED` avec la cause `RECONCILIATION_PENDING`. Même schéma que `DISPUTED`, `PROMISE_ACTIVE`, `HOLD_ACTIVE` |
| `REVIEW_REQUIRED` | **pas une issue du moteur de règles** : c'est un **élément de travail** distinct, réalisé par une **notification interne** `RECONCILIATION_REVIEW` (§6) et par la file « paiements à affecter » ; une cinquième issue se propagerait à tous les consommateurs du Rule Engine pour un besoin qui n'est pas une décision d'action |

### 3.3 Contournement manuel : vérifié à l'exécution (RN3, verrouillée)

`RECONCILIATION_PENDING` est une **exception métier**, pas une protection légale : un humain habilité peut décider de relancer malgré tout. La décision d'un humain **au moment de la création** ne vaut pas autorisation au moment où le message part : entre les deux, l'utilisateur peut avoir perdu son rôle, l'organisation peut être suspendue, un hold `LEGAL` peut être apparu.

| # | Règle |
|---|---|
| **G1** | **Origine** : seule une action `MANUAL`, portée par un **acteur humain** (utilisateur authentifié), peut recevoir un `OverrideGrant`. `AuthorizeOverride` refuse toute autre origine (`OVERRIDE_ORIGIN_NOT_MANUAL`) |
| **G2** | **Rattachement** : le grant est lié à **une action** et à **un code d'exception**. Il ne couvre ni une autre action, ni une autre facture, ni une exécution d'automatisation ; il n'est pas hérité ni réutilisé |
| **G3** | **Preuve, pas autorité** : `decision_snapshot.overrides[]` (immuable) est la **trace** de la décision initiale. L'autorité est **recalculée** à chaque évaluation |
| **G4** | **Revalidation à l'exécution** : avant de passer l'action à `EXECUTING` (contexte D), `ExecuteDueAction` **ré-autorise** le grant avec la situation courante : acteur toujours membre actif de l'organisation ; rôle **courant** ≥ rôle minimal de l'exception ; organisation `ACTIVE` ; motif présent ; exception toujours contournable ; action toujours `MANUAL` ; grant toujours rattaché à cette action. Le worker **ne fabrique rien** : il vérifie |
| **G5** | **Échec** : l'action passe `SUPPRESSED` avec le **code de l'exception** (`RECONCILIATION_PENDING`) ; aucun envoi. La cause du rejet (`ACTOR_INACTIVE`, `ROLE_INSUFFICIENT`, `ORG_INACTIVE`, `NOT_OVERRIDABLE`) figure dans l'audit. Ce n'est **pas** une erreur d'API : c'est une issue de décision |
| **G6** | **Autres exceptions** : le grant ne couvre que **l'exception nommée**. Si une autre exception échoue à l'exécution (litige ouvert entre-temps), elle s'applique normalement |
| **G7** | **Jamais par une automatisation** : aucune automatisation ne peut **créer** un grant (`AuthorizeOverride` exige un acteur humain) ni en **consommer** un (les contextes d'origine `AUTOMATIC` ignorent tout grant reçu, et le consignent). Un worker qui exécute une action manuelle n'est pas une automatisation : il ne fait que rejouer la vérification G4 |
| **G8** | **Audit** : écriture d'audit (D3) à la **création** du grant, puis à **chaque vérification à l'exécution** (résultat `OK` ou cause du rejet). `decision_snapshot` reste immuable ; aucune colonne nouvelle |
| **G9** | **Test d'architecture** (EC9) : `override_grants` n'est un paramètre d'entrée que des cas d'usage manuels et de la vérification G4 |

Portée : G1 à G9 valent pour **toutes** les exceptions contournables (`DISPUTED`, `PROMISE_ACTIVE`, `HOLD_ACTIVE` hors `LEGAL`, `FREQUENCY_LIMIT`, `RECONCILIATION_PENDING`), pas pour la seule n° 13 : les écrire pour une seule exception créerait deux régimes de contournement (amendements en §12).

---

## 4. États des actions et des exécutions

L'évaluation est **paresseuse** (RN6) : la barrière est vérifiée aux points de revalidation existants, pas par une suppression en cascade à chaque `PAYMENT_CREATED`. Un paiement créé puis alloué quelques secondes plus tard (saisie manuelle, rapprochement automatique) ne provoque donc aucune suspension : les handlers relisent la source de vérité, où l'allocation est déjà là.

| Objet | État | Effet de la barrière |
|---|---|---|
| Action | `PROPOSED` | à la création (contexte C) : créée `SUPPRESSED` avec le code |
| Action | `SCHEDULED` | à la **revalidation avant exécution** (contexte D) : `SUPPRESSED` ; la clé de déduplication est libérée. Une action `MANUAL` portant un `OverrideGrant` n'est suspendue que si la vérification G4 échoue |
| Action | `PENDING_APPROVAL` | à la décision ou au réveil : `SUPPRESSED` (transition `PENDING_APPROVAL → SUPPRESSED`, State Machines S8) ; l'approbation passe `EXPIRED` (`TARGET_RESOLVED`) par `approvals`, qui interroge la cible (Architecture technique, TD58) |
| Action | `EXECUTING` | **non interrompue** : l'envoi est en cours ; **limite connue** (fenêtre de quelques secondes, §10) |
| Action | `DONE` | **inchangée** : le message est parti, l'historique reste vrai |
| Exécution | `PENDING`, `RUNNING` | revalidation avant l'étape (contexte B) : `PAUSED` (cause `RECONCILIATION_PENDING`), ligne d'étape `SUSPENDED` |
| Exécution | `WAITING` | évaluée **à son réveil** (`resume_at`) par la revalidation ; aucune pause prématurée |
| Exécution | `PAUSED` (autre cause) | la cause de rapprochement s'ajoute à l'évaluation à la reprise ; l'exécution reste en pause tant qu'une cause subsiste |

---

## 5. Évolution : ce qui lève, maintient ou crée la barrière

| Événement | Effet |
|---|---|
| `PAYMENT_ALLOCATED` (complète) | le non-alloué tombe à zéro : la barrière est **levée** ; les exécutions `PAUSED` (cause rapprochement) sont réévaluées et reprennent (`LATEST_ONLY`) |
| `PAYMENT_ALLOCATED` (partielle) | la barrière **subsiste** pour le reliquat ; la cause reste ; `reconciliation_pending_minor` diminue |
| `PAYMENT_REVERSED` | le paiement n'est plus qualifiant : levée, réévaluation |
| `PAYMENT_ALLOCATION_REVERSED` | le montant revient **non alloué** : la barrière peut **réapparaître** (dans la fenêtre de ce paiement) |
| `PAYMENT_CREATED` | nouvelle candidate ; effet **au prochain point de revalidation** (paresseux) |
| Minuit **local** qui suit le dernier jour de la fenêtre (W5) | la barrière **tombe** pour toute évaluation, même sans passage du job ; alerte de retard (§6) et reprise des exécutions à la prochaine passe du job |
| Deux paiements | chacun a sa fenêtre ; la barrière dure tant qu'**un** paiement reste qualifiant |

Les factures sont évaluées **indépendamment** : une allocation à la facture A n'affecte la barrière de B que par le reliquat non alloué.

---

## 6. Fenêtre, revue et escalade

Chronologie (cas d'or `R1`, `N = 3`, calendrier lundi–vendredi) : paiement de 100 000 enregistré le **lundi 2026-10-19**, non alloué.

| Date | Situation | Effet |
|---|---|---|
| lun 2026-10-19 | jour 0 | barrière active ; aucune notification |
| mar 2026-10-20 | +1 jour ouvré | **revue due** : notification `RECONCILIATION_REVIEW` au pool `COLLECTOR` (facture(s) candidate(s), montant, ancienneté) ; dédupliquée par paiement |
| jeu 2026-10-22 | dernier jour de suspension (inclus) | barrière encore active |
| ven 2026-10-23 | fenêtre écoulée (00:00 local) | barrière **levée** ; paiement marqué `stale` ; notification `RECONCILIATION_OVERDUE` au pool `MANAGER` (au premier passage du job après minuit local) ; les exécutions reprennent |

Avec un jour férié (cas d'or `R6`, paiement enregistré le vendredi 2026-10-23, férié le lundi 26) : dernier jour de suspension **jeudi 2026-10-29** ; la revue est due le mardi 27 ; la barrière tombe le vendredi 30.

**Fuseau (cas d'or `R11` à `R14`).**

| Cas | Instant d'enregistrement (UTC) | Date locale | Dernier jour | Barrière levée à (UTC) |
|---|---|---|---|---|
| `R11` Paris | ven 2026-10-23 22:30 | **samedi** 2026-10-24 | mer 2026-10-28 | 2026-10-28 23:00 |
| `R12` New York | mar 2026-10-20 02:00 | **lundi** 2026-10-19 | jeu 2026-10-22 | 2026-10-23 04:00 |
| `R13` Paris, heure d'été | lun 2026-10-19 09:00 | lundi 2026-10-19 | jeu 2026-10-22 | 2026-10-22 22:00 |
| `R14` Paris, changement d'heure le 25 | ven 2026-10-23 08:00 | vendredi 2026-10-23 | mer 2026-10-28 | 2026-10-28 23:00 (heure d'hiver : +1 h) |

`R12` montre l'erreur évitée : avec la date UTC, la fenêtre se terminerait un jour trop tard (vendredi 23). `R13` : à 21:59:59 UTC le jeudi, la barrière est encore active ; à 22:00:00 UTC, il est minuit à Paris et elle tombe.

**Après la fenêtre**, les actions créées portent `reconciliation_stale = true` dans leur `decision_snapshot` : l'explication reste complète (« un paiement de X était non alloué depuis N jours ouvrés »). La relance reprend, mais **l'organisation en est alertée** : la situation n'est jamais silencieuse.

---

## 7. Auditabilité

| Élément | Contenu |
|---|---|
| **`decision_snapshot`** | `primary_exception = RECONCILIATION_PENDING`, `exceptions_trace[]`, et un bloc `reconciliation` : `{pending, payments: [identifiants], pending_minor, window_last_day, stale}` : identifiants, montants et dates seulement (aucune donnée personnelle, X10) |
| **Revalidation** | trace conservée dans `automation_execution_steps.revalidation_result` (ligne `SUSPENDED`) et dans l'action `SUPPRESSED` |
| **Événements** | `COLLECTION_ACTION_SUPPRESSED` (avec `suppression_code`) ; `NOTIFICATION_CREATED` pour la revue et l'alerte ; aucun **nouveau** type d'événement métier |
| **Audit (D3)** | un contournement manuel est audité **à la création** du grant et **à chaque vérification à l'exécution** (G8) ; les suspensions et reprises du système restent dans l'historique des étapes, sans doublon d'audit |
| **Explication à la demande** | le contexte E du Rule Engine restitue la même décision qu'à l'exécution |

---

## 8. Contrats

### 8.1 Rule Engine (extension)

Exception n° 13 (§3.1) ; deux faits (§1.2) ; scénarios d'or à ajouter (§11). Le contrat d'entrée/sortie d'`évaluer` ne change pas.

### 8.2 Job `ReconciliationWindowScan`

| Rubrique | Contrat |
|---|---|
| **Rôle** | envoyer la revue à +1 jour ouvré, lever les barrières périmées, alerter, reprendre les exécutions concernées |
| **Cadence** | horaire, par organisation dont la date locale a changé ou dont une fenêtre expire. **L'heure du passage n'influence aucun résultat** (W6) |
| **Entrée** | paiements `RECEIVED` / `PARTIALLY_ALLOCATED` de moins de `N + 1` jours ouvrés ; exécutions `PAUSED` avec la cause `RECONCILIATION_PENDING` |
| **Idempotence** | notifications dédupliquées par `reconciliation:{payment_id}:review` et `reconciliation:{payment_id}:overdue` ; reprise par garde d'état |
| **Rattrapage** | après un arrêt, tout ce qui est dû est traité au passage suivant : les dates se calculent (W6), elles ne dépendent pas de l'instant du passage ni d'un délai écoulé depuis le précédent |
| **Isolation** | par organisation ; fuseau de l'organisation ; verrou consultatif `(job, organisation)` |
| **Événements** | `NOTIFICATION_CREATED` ; reprises : `AUTOMATION_EXECUTION_*` habituels |

### 8.3 Notifications internes (types)

| Type | Destinataires | Moment | Déduplication |
|---|---|---|---|
| `RECONCILIATION_REVIEW` | pool `COLLECTOR` (une par membre) | +1 jour ouvré après l'enregistrement, si le paiement est toujours non alloué | `reconciliation:{payment_id}:review:{user_id}` |
| `RECONCILIATION_OVERDUE` | pool `MANAGER` | premier passage après la fin de la fenêtre | `reconciliation:{payment_id}:overdue:{user_id}` |

Ce sont des notifications **internes** (canal `IN_APP`), exemptées des exceptions de contact (comme `MANAGER_ALERT`).

### 8.4 Reprise (`ResumeReactor`)

La table des causes de pause de l'Automation Engine (§7) reçoit une ligne : `RECONCILIATION_PENDING` levée par `PAYMENT_ALLOCATED`, `PAYMENT_REVERSED`, ou par le passage du job à la fin de la fenêtre.

---

## 9. Interaction avec les autres moteurs

| Moteur | Effet |
|---|---|
| **Risk** | aucun |
| **Priority** | le signal `RECONCILIATION_PENDING` (§3.4 bis de la passe RPC) est **aligné sur le fait** `invoice.reconciliation_pending` et non plus sur `customer.unallocated_payment_minor > 0` : le signal affiché et la barrière appliquée sont la **même** information. Toujours aucun effet sur le score ni le niveau ; il reste dans le hash. Il change avec le temps (fin de fenêtre) sans événement : le rafraîchissement quotidien de 05:00 le rattrape |
| **Cashflow** | inchangé (réserve FIFO, CF3) |
| **Automation** | nouvelle cause de pause et de reprise (§8.4) |
| **Import** | les paiements historiques sont hors fenêtre : l'import ne déclenche aucune barrière |

---

## 10. Limites connues

1. **Action `EXECUTING`** : un paiement enregistré pendant l'envoi ne l'arrête pas ; la fenêtre de course est de quelques secondes.
2. **Pas de seuil de matérialité en V1** : tout montant non alloué supérieur à zéro suspend, dans la limite de la fenêtre courte. Un seuil relatif au restant dû pourra être ajouté sans changer le modèle.
3. **Mono-devise** : la compatibilité de devise (Q3) est vérifiée mais non exercée par des cas multi-devises.
4. **Avances et trop-perçus** : un argent réellement destiné à une facture future reste non alloué ; il suspend au plus `N` jours ouvrés les factures antérieures à sa date de valeur, puis alerte. Sans avoirs ni comptes d'avance (hors V1), c'est le comportement le plus prudent.
5. **Après la fenêtre**, la relance reprend même si le paiement reste non alloué : c'est un choix assumé (jamais de gel indéfini), compensé par l'alerte.
6. **Reprise décalée d'au plus un passage du job** : la barrière tombe à minuit local pour toute évaluation ; les exécutions `PAUSED` ne reprennent qu'au passage horaire suivant. Les actions créées ou revalidées entre-temps voient déjà la barrière levée.
7. **Notification d'un jour non ouvré** : une fenêtre qui se termine un vendredi lève la barrière le samedi local ; l'alerte aux managers est créée à ce moment et lue le jour ouvré suivant.

---

## 11. Tests (emplacement RC de la matrice)

| Test | Niveau | Contenu |
|---|---|---|
| **RC-01** | L1 | qualification Q1 à Q5 : les cas d'or `R1` à `R10` (paiement candidat, antérieur à l'émission, alloué, annulé, partiel, jour férié, deux paiements, autre devise, facture fermée, enregistré tard) |
| **RC-02** | L1 | calendrier et fuseau (W1 à W7) : jours ouvrés, jours fériés ; date locale et non date UTC (`R11`, `R12`) ; frontière de minuit local (`R13`) ; changement d'heure (`R14`) ; résultat identique pour toute minute d'une journée locale ; la fenêtre n'a jamais de jour non ouvré en dernier jour ; la barrière ne revient pas avec le seul temps |
| **RC-03** | L1 | exception n° 13 : suspension automatique ; action manuelle avec `OverrideGrant` `COLLECTOR` ; jamais contournable par une automatisation ; ordre avec `PAID` et `HOLD_ACTIVE` ; notifications internes exemptées ; fenêtre écoulée → `PROCEED` avec `reconciliation_stale` ; **grant revérifié à l'exécution** (G4 à G6) : acteur désactivé, rôle rétrogradé, organisation suspendue, hold `LEGAL` apparu, autre exception apparue |
| **RC-04** | L4 | **aucune présomption** : deux factures (100 000 et 500 000), un paiement de 100 000 : **les deux** sont suspendues ; après allocation complète à l'une, l'autre est levée |
| **RC-05** | L4 | états d'action : `SCHEDULED` suspendue à l'exécution ; `EXECUTING` non interrompue ; `DONE` inchangée ; `PENDING_APPROVAL` → `SUPPRESSED` ; clé de déduplication libérée puis nouvelle action |
| **RC-06** | L4 | exécutions : `PAUSED` (`RECONCILIATION_PENDING`) ; reprise sur `PAYMENT_ALLOCATED`, `PAYMENT_REVERSED`, fin de fenêtre ; reste en pause si un second paiement qualifie ; **une automatisation ne crée ni ne consomme jamais de grant** (G7) |
| **RC-07** | L4 | évolution : allocation partielle, complète, allocation annulée (barrière qui réapparaît), paiement annulé, nouveau paiement, deux paiements |
| **RC-08** | L4 | job `ReconciliationWindowScan` : revue à +1 jour ouvré, alerte en fin de fenêtre, idempotence, rattrapage après arrêt ; **même résultat quelle que soit l'heure du passage** (00:05 ou 23:55) |
| **RC-09** | L3 | auditabilité : `decision_snapshot` complet et immuable, sans donnée personnelle ; audit d'un contournement manuel à la création **et** à chaque vérification à l'exécution |
| **RC-10** | L4 | signal de Priority aligné sur le fait ; aucun effet sur score ni niveau ; hash modifié ; bascule à la fin de fenêtre par le rafraîchissement quotidien |
| **RC-11** | L5 | bout en bout : paiement le lundi, rappel prévu le mardi (suspendu), allocation le mercredi (reprise, nouveau rappel) ; et le cas sans rapprochement (fenêtre écoulée le vendredi, relance et alerte) |
| **RC-12** | L6 | propriétés du modèle de référence et test différentiel du fait SQL contre `reconciliation_state` |

---

## 12. Décisions à valider et amendements

| # | Décision | Statut |
|---|---|---|
| **RN1** | Principe : **Collection ne présume pas, elle suspend** ; Cashflow présume pour prévoir avec prudence | validée |
| **RN2** | Portée : **par facture**, avec **candidature prudente** (Q1 à Q5) ; aucune présomption FIFO ; toutes les factures candidates sont suspendues | validée |
| **RN3** | Exception intégrée n° 13 `RECONCILIATION_PENDING`, classe métier, applicable aux 4 types d'action, contournable **manuellement** (`COLLECTOR`, motif) par un `OverrideGrant` **revérifié à l'exécution** ; une automatisation ne le crée ni ne le consomme jamais | validée, **verrouillée** (G1 à G9) |
| **RN4** | Issue : `SUPPRESS` (actions) et `PAUSED` (exécutions) ; `DEFER` non utilisé ; `REVIEW_REQUIRED` = notification interne `RECONCILIATION_REVIEW`, pas une issue du moteur | validée |
| **RN5** | Fenêtre bornée : **3 jours ouvrés** depuis la **date locale** d'enregistrement (`created_at` converti dans le fuseau de l'organisation), calendrier de l'organisation uniquement, réglable (`extra`) ; barrière active jusqu'à la **fin du dernier jour**, `stale` dès le **jour local suivant** ; indépendante de l'heure du job ; fin de fenêtre : levée, `reconciliation_stale`, alerte `RECONCILIATION_OVERDUE` aux managers | validée, **verrouillée** (W1 à W8) |
| **RN6** | Évaluation **paresseuse** aux points de revalidation ; pas de suppression en cascade sur `PAYMENT_CREATED` ; reprise par événements (`PAYMENT_ALLOCATED`, `PAYMENT_REVERSED`) et par job | validée |
| **RN7** | Job horaire `ReconciliationWindowScan` (revue à +1 jour ouvré, fin de fenêtre, reprise) | validée |
| **RN8** | Faits `invoice.reconciliation_pending` et `invoice.reconciliation_pending_minor` ; le signal de Priority est aligné sur ce fait | validée |
| **RN9** | Auditabilité : bloc `reconciliation` du `decision_snapshot` (identifiants, montants, dates), sans donnée personnelle | validée |
| **RN10** | Actions `EXECUTING` non interrompues, `DONE` inchangées (limite documentée) | validée |
| **RN11** | Paiements importés hors fenêtre : aucune barrière | validée |
| **RN12** | Pas de seuil de matérialité en V1 | validée |

### Hors périmètre V1.2 (décidé)

Seuil de montant ; probabilité de rattachement paiement → facture ; affectation automatique intelligente ; FIFO dans Collection ; apprentissage automatique ; nouvelle issue `REVIEW_REQUIRED`. Aucun n'est nécessaire à la barrière ; chacun pourra s'ajouter sans changer le modèle (§10).

### Amendements à appliquer

| Document | Amendement |
|---|---|
| Rule Engine V1.1 | **§3.3** : le grant est une preuve, revérifiée à l'exécution (G1 à G9), pour toutes les exceptions contournables ; exception n° 13 (§3, §3.1, §3.2) ; faits `invoice.reconciliation_pending` et `_minor` (§2.2) ; scénarios d'or `RE-47` à `RE-52` ; le nombre « 12 exceptions » devient 13 |
| Data Contract V1.3 | `collection_actions.suppression_code` et `automation_executions.status_reason` : ajout de `RECONCILIATION_PENDING` ; types de notification `RECONCILIATION_REVIEW`, `RECONCILIATION_OVERDUE` ; clé `org_settings.extra.reconciliation_hold_business_days` |
| Automation Engine V1.1 | §7 : cause `RECONCILIATION_PENDING` et ses événements de levée ; §6.2 : traduction de l'exception |
| State Machines V1 | §12 : cause de pause ; §16 : cascade `PAYMENT_ALLOCATED` / `PAYMENT_REVERSED` → reprise |
| Collection Engine V1.1 | §2 (exceptions applicables), §12 (réactions) ; §4 : une action manuelle avec grant est revérifiée à l'exécution ; ce document en devient l'annexe V1.2 |
| Engine Contracts V1.1 | EC-03 : job `ReconciliationWindowScan` ; **EC-10** : l'audit du grant est écrit à la création **et** à chaque vérification à l'exécution ; **EC-11** : `ExecuteDueAction` revérifie les grants (G4) |
| Risk / Priority / Cashflow V1.1 | §3.4 bis : signal aligné sur le fait `invoice.reconciliation_pending` |
| Global Test Matrix V1 | famille O : lignes `RC-01` à `RC-12` ; l'emplacement Billing (S7) devient `BL-01` |
