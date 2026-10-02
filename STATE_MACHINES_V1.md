# VERQIA — State Machines V1

Référence : Data Contract V1.3 (figé), Invariants V1.2.
Objet : pour chaque objet à état, les états, les transitions autorisées, leurs gardes, leurs effets et l'endroit où elles sont imposées.

## 0. Conventions

**Format d'une transition** : `De → Vers` · déclencheur (acteur) · garde · effets et événements.

**Trois niveaux d'application** (chaque machine indique lesquels s'appliquent) :
1. **Domain** : table de transitions unique dans le code ; toute transition passe par elle.
2. **Écriture atomique** (C3) : `UPDATE … WHERE état = ancien`.
3. **Base de données** : `CHECK` reliant l'état aux données, et, pour les machines marquées 🛡, un trigger de garde **T14** qui rejette tout couple `(ancien, nouveau)` absent de la table de transitions. **T14 est au contrat V1.3** ; il ne coûte presque rien et attrape les bugs qui contournent le Domain.

**États dérivés.** Certains « états » ne sont pas des machines autonomes mais des fonctions de données : `settlement_state` = f(`paid_minor`, `total_minor`) ; `payments.status` (sauf `REVERSED`) = f(`allocated_minor`, `amount_minor`). Ils ne se modifient jamais directement ; on les recalcule et on vérifie la cohérence (T4, T5).

**Terminal** = aucune transition sortante. **Actor** : `USER` (avec rôle), `SYSTEM` (Scheduler, handler d'événement), `AUTOMATION`.

**Événements** : les noms renvoient au catalogue `INVARIANTS_V1.md` §10.

---

## 1. Organization (`organizations.status`) 🛡

États : `PROVISIONING`, `ACTIVE`, `SUSPENDED`, `CLOSED` (terminal).

| Transition | Déclencheur | Garde | Effets |
|---|---|---|---|
| (création) `→ PROVISIONING` | `USER` | slug libre ; devise, fuseau et pays valides | organisation et `org_settings` écrits ; aucun événement |
| `PROVISIONING → ACTIVE` | `SYSTEM` (`CompleteProvisioning`) | **toutes** les étapes du plan de provisioning sont faites (membre `OWNER`, abonnement d'essai, automatisations modèles) | `ORGANIZATION_CREATED` |
| `PROVISIONING → CLOSED` | plateforme | abandon d'un provisioning qui ne peut aboutir | `ORGANIZATION_CLOSED` |
| `ACTIVE → SUSPENDED` | `OWNER`/plateforme | motif obligatoire | `ORGANIZATION_SUSPENDED` ; exécutions d'automatisation en `PAUSED` (`ORG_INACTIVE`) ; communications sortantes arrêtées |
| `SUSPENDED → ACTIVE` | plateforme/`OWNER` | — | `ORGANIZATION_REACTIVATED` ; exécutions `PAUSED` (`ORG_INACTIVE`) reprennent en `PENDING`, revalidées |
| `ACTIVE/SUSPENDED → CLOSED` | `OWNER` | confirmation ; abonnement clos | `ORGANIZATION_CLOSED` ; lecture et export seulement ; **aucune donnée supprimée** |

Interdit : `CLOSED → *`.

## 2. Customer (`customers.status`) 🛡

États : `ACTIVE`, `INACTIVE`, `ARCHIVED`.

| Transition | Déclencheur | Garde | Effets |
|---|---|---|---|
| `ACTIVE → INACTIVE` | `ADMIN`/`MANAGER` | — | `CUSTOMER_DEACTIVATED` ; actions planifiées → `SUPPRESSED` (`CUSTOMER_INACTIVE`) ; exécutions `PAUSED` (`CUSTOMER_INACTIVE`) |
| `INACTIVE → ACTIVE` | `ADMIN`/`MANAGER` | — | reprise des exécutions `PAUSED` (`CUSTOMER_INACTIVE`), revalidées |
| `ACTIVE/INACTIVE → ARCHIVED` | `ADMIN` | aucune facture `DRAFT/ISSUED/DUE_SOON/DUE/OVERDUE` avec règlement ≠ `PAID` (D6) ; promesses client `ACTIVE` annulées (`NO_OPEN_INVOICE`) ; motif | `CUSTOMER_ARCHIVED` ; `archived_at` renseigné |
| `ARCHIVED → ACTIVE` | `ADMIN` | motif obligatoire ; audit | `CUSTOMER_REACTIVATED` ; **jamais automatique** |

Interdit : `ARCHIVED → INACTIVE`.
Cas particulier (D6) : un reversal peut rouvrir une facture d'un client `ARCHIVED` ; aucune transition du client, recouvrement `SUPPRESSED` (`CUSTOMER_ARCHIVED`) et notification aux `ADMIN`.

---

## 3. Invoice — cycle de vie (`invoices.lifecycle_state`) 🛡

États : `DRAFT`, `ISSUED`, `DUE_SOON`, `DUE`, `OVERDUE`, `CANCELLED` (terminal), `VOID` (terminal).

| Transition | Déclencheur | Garde | Effets |
|---|---|---|---|
| `DRAFT → ISSUED` | `USER` | ≥ 1 ligne ; total > 0 ; T9 ; `due_date >= issue_date` ; client `ACTIVE` ; organisation `ACTIVE` | `INVOICE_ISSUED` ; `issued_at` ; T13 s'active. **Rattrapage immédiat** : dans la même transaction, les transitions temporelles applicables à la date courante sont appliquées (une facture émise en retard n'attend pas le Scheduler) |
| `DRAFT → CANCELLED` | `USER` | — | `INVOICE_CANCELLED` ; `cancelled_at`, `cancel_reason` |
| `ISSUED → DUE_SOON` | `SYSTEM` (Scheduler) | `due_date − due_soon_days <= aujourd'hui` ; règlement ≠ `PAID` | `INVOICE_DUE_SOON` |
| `ISSUED / DUE_SOON → DUE` | `SYSTEM` | `due_date = aujourd'hui` ; règlement ≠ `PAID` | `INVOICE_DUE` |
| `ISSUED / DUE_SOON / DUE → OVERDUE` | `SYSTEM` | `due_date < aujourd'hui` ; règlement ≠ `PAID` | `INVOICE_OVERDUE` ; `collection_cycle + 1` |
| `ISSUED / DUE_SOON / DUE / OVERDUE → VOID` | `USER` (`MANAGER`+) | `paid_minor = 0` ; **aucun litige `OPEN`** ; motif | `INVOICE_VOIDED` ; promesses → `CANCELLED` ; actions → `SUPPRESSED` (`VOIDED`) ; exécutions → `CANCELLED` (`SUBJECT_VOIDED`) |
| recalcul après annulation de règlement | `SYSTEM`, dans la transaction du reversal (B3-a) | règlement `PAID → ≠ PAID` | le cycle de vie « gelé » est recalculé depuis `due_date`, uniquement vers l'avant (§ ci-dessous) |

Propriétés :
- **Monotone** : `ISSUED < DUE_SOON < DUE < OVERDUE`. Jamais de retour en arrière (possible grâce à l'immuabilité de `due_date`, T13).
- **Sauts autorisés** : `ISSUED → OVERDUE`, `DUE_SOON → OVERDUE`, etc. Seule la transition réellement effectuée émet un événement : un saut n'émet pas les événements des états sautés.
- **Gel** : une facture `PAID` ne reçoit plus de transition temporelle ; à l'annulation du règlement, elle est recalculée.
- **Import** : `ImportHistoricalInvoice` crée directement l'état reconstruit (INSERT, T13 non concerné) avec ses lignes d'historique.
- Aucun déclencheur temporel **rétroactif** : à l'activation d'une automatisation ou à l'émission tardive d'une facture, les décalages dont l'instant est déjà passé ne se déclenchent pas (à préciser dans la passe Automation Engine).

Interdit : `DRAFT → VOID`, `CANCELLED → *`, `VOID → *`, `OVERDUE → DUE/DUE_SOON/ISSUED`, `ISSUED… → DRAFT`, `ISSUED… → CANCELLED` (utiliser `VOID`).

## 4. Invoice — règlement (`invoices.settlement_state`) — **dérivé**

États : `UNPAID`, `PARTIALLY_PAID`, `PAID`. Fonction : `paid = 0 → UNPAID` ; `0 < paid < total → PARTIALLY_PAID` ; `paid = total > 0 → PAID`.

| Transition (résultat d'une allocation ou d'un reversal) | Événement |
|---|---|
| `UNPAID → PARTIALLY_PAID` | `INVOICE_PARTIALLY_PAID` |
| `UNPAID / PARTIALLY_PAID → PAID` | `INVOICE_PAID` ; `settled_on` = `value_date` du paiement soldant |
| `PAID → PARTIALLY_PAID / UNPAID`, `PARTIALLY_PAID → UNPAID` | `INVOICE_SETTLEMENT_REVERTED` ; `settled_on` effacé ; si le cycle de vie est déjà `OVERDUE` : `collection_cycle + 1` |
| `PARTIALLY_PAID → PARTIALLY_PAID` | aucun événement de facture |

Effets du passage à `PAID` : promesses de la facture → `FULFILLED` ; actions en attente → `SUPPRESSED` (`PAID`) ; exécutions → `CANCELLED` (`SUBJECT_PAID`) ; priorité → `NONE`.
Garde : règlement toujours `UNPAID` tant que le cycle de vie est `DRAFT`, `CANCELLED` ou `VOID` (CK + T6).

## 5. Invoice — litige (`invoice_disputes.status`) 🛡

États : `OPEN`, `RESOLVED_VALID` (terminal), `RESOLVED_REJECTED` (terminal).

| Transition | Déclencheur | Garde | Effets |
|---|---|---|---|
| (création) `→ OPEN` | `USER` | facture `ISSUED…OVERDUE`, règlement ≠ `PAID` ; aucun autre litige `OPEN` ; motif | `INVOICE_DISPUTED` ; si `collectible_minor = 0` : actions `SUPPRESSED` (`DISPUTED`), exécutions `PAUSED` (`DISPUTED`) |
| `OPEN → RESOLVED_REJECTED` | `MANAGER`+ | note de résolution | `INVOICE_DISPUTE_RESOLVED` ; le recouvrement reprend (exécutions `PAUSED` → `PENDING`, revalidées) |
| `OPEN → RESOLVED_VALID` | `MANAGER`+ | note de résolution | `INVOICE_DISPUTE_RESOLVED` ; procédure V1 : reverser les allocations, `VOID`, ré-émettre (pas d'avoirs) |

Un litige `OPEN` ne modifie **pas** `lifecycle_state` ni `settlement_state`. `VOID` est refusé tant qu'un litige est `OPEN`.

---

## 6. Payment (`payments.status`) 🛡

États : `RECEIVED`, `PARTIALLY_ALLOCATED`, `ALLOCATED`, `REVERSED` (terminal). Hors `REVERSED`, l'état est dérivé de `allocated_minor`.

| Transition | Déclencheur | Garde | Effets |
|---|---|---|---|
| `RECEIVED → PARTIALLY_ALLOCATED / ALLOCATED` | `USER`/`SYSTEM` (rapprochement) | T1, T2, T10 ; client, devise (FK composites) | `PAYMENT_ALLOCATED` ; événements de facture (§4) dans la même transaction |
| `PARTIALLY_ALLOCATED → ALLOCATED` | idem | idem | idem |
| `ALLOCATED / PARTIALLY_ALLOCATED → PARTIALLY_ALLOCATED / RECEIVED` | `USER` (`COLLECTOR`+) | reversal d'allocation ; motif ; T3 | `PAYMENT_ALLOCATION_REVERSED` ; événements de facture |
| `* → REVERSED` | `USER` (`MANAGER`+) | motif et `reason_code` ; aucun autre reversal en cours | `PAYMENT_REVERSED` ; **toutes** les allocations actives reversées dans la même transaction ; ligne `payment_reversals` |

Interdit : `REVERSED → *`, toute allocation positive sur un paiement `REVERSED` (T10).

## 7. Promise (`promises.status`) 🛡

États : `ACTIVE`, `FULFILLED`, `BROKEN`, `CANCELLED` (tous terminaux sauf `ACTIVE`).

| Transition | Déclencheur | Garde | Effets |
|---|---|---|---|
| (création) `→ ACTIVE` | `USER` | voir Invariants §6 (montant ≤ solde ou encours éligible, date ≥ aujourd'hui, aucune autre `ACTIVE` sur la portée) | `PROMISE_CREATED` ; relances standard suspendues (exécutions `PAUSED` `PROMISE_ACTIVE`, actions `SUPPRESSED` `PROMISE_ACTIVE`) |
| `ACTIVE → FULFILLED` | `SYSTEM` (sur allocation, sur `INVOICE_PAID`, balayage quotidien) | montant constaté ≥ montant promis, ou facture `PAID` | `PROMISE_FULFILLED` ; `resolved_amount_minor` ; reprise des exécutions `PAUSED` |
| `ACTIVE → BROKEN` | `SYSTEM` (Scheduler) | `date courante > promised_date + grace_days` et non `FULFILLED` | `PROMISE_BROKEN` ; `resolved_amount_minor` ; reprise des exécutions ; risque pénalisé |
| `ACTIVE → CANCELLED` | `USER`, ou `SYSTEM` (facture `VOID`/`CANCELLED`, client archivé, plus de facture ouverte) | motif | `PROMISE_CANCELLED` |

Modifier montant ou date = `CANCELLED` + nouvelle promesse (N11). `FULFILLED` reste terminal après un reversal (N6).

## 8. Collection Action (`collection_actions.status`) 🛡

États : `PROPOSED`, `SCHEDULED`, `PENDING_APPROVAL`, `EXECUTING`, `DONE`, `FAILED`, `CANCELLED`, `SUPPRESSED`. Terminaux : `DONE`, `FAILED`, `CANCELLED`, `SUPPRESSED`.

| Transition | Déclencheur | Garde | Effets |
|---|---|---|---|
| (création) `→ PROPOSED` | Collection Engine ou `USER` | dedup_key libre ; niveau valide, ≥ 3 si facture `OVERDUE`, non régressif (N7) | `COLLECTION_ACTION_PROPOSED` |
| `PROPOSED → SCHEDULED` | Collection Engine | **revalidation** (ordre : organisation, client, facture, litige, promesse, hold, fréquence, contact, consentement) ; approbation non requise ; `scheduled_for` dans la fenêtre de communication, sinon reprogrammée | `COLLECTION_ACTION_SCHEDULED` |
| `PROPOSED → PENDING_APPROVAL` | Collection Engine | approbation requise par la politique | ligne `approvals` `PENDING` ; `APPROVAL_REQUESTED` |
| `PENDING_APPROVAL → SCHEDULED` | `SYSTEM` (approbation `APPROVED`) | revalidation | `COLLECTION_ACTION_SCHEDULED` |
| `PENDING_APPROVAL → CANCELLED` | `SYSTEM` (approbation `REJECTED`/`EXPIRED`) | — | `COLLECTION_ACTION_CANCELLED` |
| `SCHEDULED → EXECUTING` | worker | `scheduled_for <= maintenant` ; **revalidation complète** ; tentatives < `max_attempts` | ligne d'essai ouverte |
| `EXECUTING → DONE` | worker | envoi accepté | `COLLECTION_ACTION_EXECUTED` ; `executed_at` ; notification créée si applicable |
| `EXECUTING → SCHEDULED` | worker | échec, tentatives restantes | `next_retry_at` ; essai enregistré |
| `EXECUTING → FAILED` | worker | tentatives épuisées | `COLLECTION_ACTION_FAILED` ; alerte au responsable |
| `SCHEDULED → DONE` | `USER` (assigné ou membre du pool) | **tâche humaine uniquement** (`CALL_TASK`, `FOLLOW_UP`, `ESCALATION`) ; issue obligatoire (liste fermée) ; revalidation non requise (l'action humaine est déjà accomplie) | `COLLECTION_ACTION_EXECUTED` ; `executed_at` ; les issues `PROMISE_OBTAINED` et `DISPUTE_RAISED` suggèrent la promesse ou le litige à l'interface, sans les créer |
| `PROPOSED / SCHEDULED / PENDING_APPROVAL → SUPPRESSED` | Collection Engine ou `SYSTEM` | une exception métier s'applique ; `suppression_code` obligatoire | `COLLECTION_ACTION_SUPPRESSED` ; si l'action était `PENDING_APPROVAL`, l'approbation liée passe en `EXPIRED` avec `decision_comment = TARGET_RESOLVED` |
| tout état non terminal `→ CANCELLED` | `USER` | motif | `COLLECTION_ACTION_CANCELLED` |

Sémantique : `SUPPRESSED` = le système constate qu'une exception métier s'applique ; `CANCELLED` = décision d'un acteur.
**Clé de déduplication** : l'unicité de `dedup_key` ne porte que sur les actions **non `CANCELLED` et non `SUPPRESSED`** (contrat V1.3, correction issue de cette passe). Sans cela, une action supprimée (par exemple par une promesse active) bloquerait pour toujours la création d'une nouvelle action équivalente une fois la promesse rompue. Une action `DONE` ou `FAILED` continue de bloquer un doublon dans le même cycle.

## 9. Collection Hold (`collection_holds.status`) 🛡

États : `ACTIVE`, `RELEASED` (terminal), `EXPIRED` (terminal).

| Transition | Déclencheur | Garde | Effets |
|---|---|---|---|
| (création) `→ ACTIVE` | `MANAGER`+ | motif ; portée cohérente ; pas de chevauchement (EXCLUDE) | `COLLECTION_HOLD_PLACED` ; audit ; actions concernées `SUPPRESSED` (`HOLD_ACTIVE`) ; exécutions `PAUSED` (`HOLD_ACTIVE`) |
| `ACTIVE → RELEASED` | `MANAGER`+ | `release_reason` | `COLLECTION_HOLD_RELEASED` (`cause`=`RELEASED`) ; exécutions reprises |
| `ACTIVE → EXPIRED` | `SYSTEM` (Scheduler) | `ends_at <= maintenant` | `COLLECTION_HOLD_RELEASED` (`cause`=`EXPIRED`) |

Un hold est **en vigueur** d'après `starts_at`/`ends_at`, indépendamment du balayage `EXPIRED`.

## 10. Approval (`approvals.status`) 🛡

États : `PENDING`, `APPROVED`, `REJECTED`, `EXPIRED` (tous terminaux sauf `PENDING`).

| Transition | Déclencheur | Garde | Effets |
|---|---|---|---|
| (création) `→ PENDING` | moteur | destinataire (utilisateur ou rôle) ; `expires_at` | `APPROVAL_REQUESTED` |
| `PENDING → APPROVED` | `USER` éligible | rôle `MANAGER`+ ; `approval_limit_minor >=` montant ; ≠ demandeur si politique | `APPROVAL_GRANTED` ; action → `SCHEDULED` / exécution → reprise |
| `PENDING → REJECTED` | `USER` éligible | commentaire obligatoire | `APPROVAL_REJECTED` ; action → `CANCELLED` / exécution → `CANCELLED` |
| `PENDING → EXPIRED` | `SYSTEM` | `expires_at <= maintenant` | action → `CANCELLED` ; exécution → `CANCELLED` |
| `PENDING → EXPIRED` (cible résolue) | `SYSTEM` | l'action ou l'exécution liée n'a plus d'objet (facture payée, annulée…) | `decision_comment = TARGET_RESOLVED` ; l'action liée passe en `SUPPRESSED` avec le code correspondant |

---

## 11. Automation (`automations.status`) 🛡

États : `DRAFT`, `ACTIVE`, `PAUSED`, `DISABLED`, `ARCHIVED` (terminal).

| Transition | Déclencheur | Garde | Effets |
|---|---|---|---|
| `DRAFT → ACTIVE` | `OWNER`/`ADMIN` | version courante valide au schéma ; **préconditions d'activation** (N13) | `AUTOMATION_ACTIVATED` ; audit ; aucun déclenchement rétroactif ; `active_since` fixé (avec inscription : `as_of` de l'aperçu) |
| `ACTIVE → PAUSED` | `MANAGER`+ | motif | `AUTOMATION_PAUSED` ; nouveaux déclencheurs ignorés ; exécutions en vol : à leur réveil → `PAUSED` (`AUTOMATION_PAUSED`) ; `active_since` effacé |
| `PAUSED → ACTIVE` | `MANAGER`+ | préconditions | `AUTOMATION_ACTIVATED` ; exécutions `PAUSED` (`AUTOMATION_PAUSED`) → `PENDING`, revalidées ; `active_since` fixé à la reprise (nouvelle référence de non-rétroactivité) |
| `ACTIVE / PAUSED → DISABLED` | `ADMIN` | motif | `AUTOMATION_DISABLED` ; exécutions non terminales → `CANCELLED` (`AUTOMATION_DISABLED`) |
| `DISABLED → ARCHIVED` | `ADMIN` | aucune exécution non terminale | `AUTOMATION_ARCHIVED` ; `archived_at` |
| `DRAFT → ARCHIVED` | `ADMIN` | — | `AUTOMATION_ARCHIVED` |

Interdit : `DISABLED → ACTIVE` (une pause réversible se fait par `PAUSED`), `ARCHIVED → *`.
Changement de version courante d'une automatisation `ACTIVE` : pas une transition d'état ; les exécutions en vol restent liées à **leur** version.

## 12. Automation Execution (`automation_executions.status`) 🛡

États : `PENDING`, `RUNNING`, `WAITING`, `PAUSED`, `COMPLETED`, `FAILED`, `CANCELLED`. Terminaux : `COMPLETED`, `FAILED`, `CANCELLED`.

| Transition | Déclencheur | Garde | Effets |
|---|---|---|---|
| (création) `→ PENDING` | répartiteur d'événements ou Scheduler | UQ `(automation_id, trigger_key, subject_id)` ; automatisation `ACTIVE` ; lot d'import non retenu | `AUTOMATION_EXECUTION_STARTED` au premier passage en `RUNNING` ; création étalée (libération d'un lot, inscription) : statut `WAITING`, `resume_at` = créneau de démarrage |
| `PENDING → RUNNING` | worker | automatisation `ACTIVE` ; organisation `ACTIVE` ; **revalidation** | étape enregistrée avec `revalidation_result` |
| `RUNNING → WAITING` | worker | étape `WAIT`/`DELAY` ou approbation en attente ; ou échec avec nouvelle tentative | `resume_at` renseigné ; `retry_count` incrémenté pour une nouvelle tentative |
| `WAITING → RUNNING` | worker | `resume_at <= maintenant` ou approbation décidée ; **revalidation** | — |
| `RUNNING → COMPLETED` | worker | dernière étape réussie | `AUTOMATION_EXECUTION_COMPLETED` |
| `RUNNING → FAILED` | worker | échec et tentatives épuisées | `AUTOMATION_EXECUTION_FAILED` ; `failure_reason` |
| `RUNNING / WAITING → PAUSED` | `USER` ou `SYSTEM` | cause : `DISPUTED`, `PROMISE_ACTIVE`, `HOLD_ACTIVE`, `CUSTOMER_INACTIVE`, `CUSTOMER_ARCHIVED`, `ORG_INACTIVE`, `AUTOMATION_PAUSED`, `IMPORT_HELD`, `RECONCILIATION_PENDING`, `USER` | `status_reason` obligatoire |
| `PAUSED → PENDING` | `SYSTEM` (cause levée) ou `USER` | revalidation ; la cause n'existe plus | reprise à l'étape courante, **revalidée** |
| tout état non terminal `→ CANCELLED` | `USER` ou `SYSTEM` | cause : `SUBJECT_PAID`, `SUBJECT_VOIDED`, `AUTOMATION_DISABLED`, `USER` | `AUTOMATION_EXECUTION_CANCELLED` |

Règle de pause/reprise : les causes de pause sont les **mêmes exceptions métier** que les codes de suppression des actions. Une exécution `PAUSED` pour une cause reprend uniquement quand cette cause est levée.
Chaque exécution porte la version d'automatisation avec laquelle elle a démarré.

## 13. Cashflow Run (`cashflow_runs.status`, `is_current`)

États : `RUNNING`, `COMPLETED`, `FAILED` (tous terminaux sauf `RUNNING`). Drapeau : `is_current`.

| Transition | Déclencheur | Garde | Effets |
|---|---|---|---|
| (création) `→ RUNNING` | Cashflow Engine | au plus un `RUNNING` par `(organisation, horizon, scénario)` ; sinon `CASHFLOW_RUN_CONFLICT` ou REPLAY | — |
| `RUNNING → COMPLETED` | Cashflow Engine | lignes écrites ; contrôles de cohérence | `computed_at` ; puis bascule `is_current` |
| `RUNNING → FAILED` | Cashflow Engine | erreur | run jamais `is_current` |
| `is_current : false → true` | Cashflow Engine | run `COMPLETED` ; l'ancien est d'abord désactivé, dans la même transaction | `CASHFLOW_UPDATED` |

Un run `COMPLETED` est immuable ; un nouveau calcul crée un nouveau run.

## 14. Import Batch (`import_batches.status`) 🛡

États : `UPLOADED`, `VALIDATING`, `VALIDATION_FAILED` (terminal), `READY`, `APPROVED`, `COMMITTED`, `NORMALIZING`, `NORMALIZED`, `FAILED` (terminal), `RELEASING`, `RELEASE_PAUSED`, `RELEASED` (terminal), `CANCELLED` (terminal).

| Transition | Déclencheur | Garde | Effets |
|---|---|---|---|
| (création) `→ UPLOADED` | `ADMIN`+ | `file_hash` libre | `IMPORT_BATCH_UPLOADED` |
| `UPLOADED → VALIDATING` | `SYSTEM` | — | staging chargé |
| `VALIDATING → READY` | `SYSTEM` | aucune erreur bloquante | `IMPORT_BATCH_READY` |
| `VALIDATING → VALIDATION_FAILED` | `SYSTEM` | erreurs bloquantes | `failure_reason` ; `IMPORT_BATCH_FAILED` |
| `READY → APPROVED` | `ADMIN`+ | relecture ; `release_mode` choisi | `IMPORT_BATCH_APPROVED` ; audit |
| `APPROVED → COMMITTED` | `ADMIN`+ | confirmation explicite | `IMPORT_BATCH_COMMITTED` ; staging **figé** ; audit ; irréversible |
| `COMMITTED → NORMALIZING` | `SYSTEM` | — | — |
| `NORMALIZING → NORMALIZED` | `SYSTEM` | toutes les lignes normalisées (défaut V1 : tout ou rien) | `IMPORT_BATCH_NORMALIZED` ; événements des moteurs émis avec `import_batch_id` |
| `NORMALIZING → FAILED` | `SYSTEM` | erreur | aucune donnée créée ; `IMPORT_BATCH_FAILED` |
| `NORMALIZED → RELEASING` | `SYSTEM` (`PACED`) ou `ADMIN`+ (`HOLD`) | — | libération étalée des exécutions |
| `RELEASING ⇄ RELEASE_PAUSED` | `ADMIN`+ | — | audit |
| `RELEASING → RELEASED` | `SYSTEM` | plus rien à libérer | `IMPORT_BATCH_RELEASED` |
| `UPLOADED / VALIDATING / READY / VALIDATION_FAILED / APPROVED → CANCELLED` | `ADMIN`+ | **avant** `COMMITTED` | `IMPORT_BATCH_CANCELLED` |

Interdit : annuler ou supprimer un lot `COMMITTED` ou au-delà.

## 15. Autres machines (compactes)

| Objet | États | Transitions notables |
|---|---|---|
| **Notification** | `PENDING`, `SENT`, `FAILED`, `CANCELLED` | `PENDING → SENT` (livraison acceptée) ; `PENDING → FAILED` (essais épuisés) ; `PENDING → CANCELLED` (action source annulée ou supprimée, destinataire anonymisé). `SENT`, `FAILED`, `CANCELLED` terminaux. Déduplication (`dedup_key`) : unique parmi les notifications non `CANCELLED`. |
| **Subscription** | `TRIALING`, `ACTIVE`, `PAST_DUE`, `CANCELLED`, `EXPIRED` | `TRIALING → ACTIVE / EXPIRED` ; `ACTIVE → PAST_DUE → ACTIVE` ; `ACTIVE/PAST_DUE → CANCELLED` ; `CANCELLED → EXPIRED` en fin de période. Le lien avec les autorisations (que reste-t-il permis en `PAST_DUE`/`EXPIRED`) est à spécifier dans le module Billing. |
| **User** | `ACTIVE`, `INVITED`, `DISABLED` | `INVITED → ACTIVE` ; `ACTIVE ⇄ DISABLED` ; anonymisation seulement depuis `DISABLED`. |
| **Membership** | `ACTIVE`, `SUSPENDED`, `REMOVED` (terminal) | `ACTIVE ⇄ SUSPENDED` ; `→ REMOVED`. Garde : au moins un `OWNER` actif. |
| **Message template** | `DRAFT`, `ACTIVE`, `ARCHIVED` (terminal) | `DRAFT → ACTIVE → ARCHIVED`. Un gabarit `ACTIVE` est immuable : modifier = nouvelle version. |

---

## 16. Couplages entre machines (cascades)

Une transition dans une machine en force d'autres. Les colonnes « même transaction » et « par événement » distinguent ce qui est atomique de ce qui est réactif (C12).

| Transition source | Effets | Mode |
|---|---|---|
| Allocation / reversal | règlement de la facture ; `paid_minor`, `allocated_minor`, `settled_on` ; états `PAID` et cycle de vie gelé/recalculé ; `collection_cycle` | **même transaction** (exception C12) |
| `INVOICE_PAID` | promesses → `FULFILLED` ; actions → `SUPPRESSED` (`PAID`) ; exécutions → `CANCELLED` (`SUBJECT_PAID`) ; priorité `NONE` | par événement |
| `INVOICE_SETTLEMENT_REVERTED` | risque, priorité, cashflow (le recalcul du cycle de vie et le nouveau cycle de recouvrement sont faits **dans la transaction de l'allocation ou du reversal**, ligne « Allocation / reversal » ; B3-a) | par événement |
| `INVOICE_VOIDED` / `_CANCELLED` | promesses → `CANCELLED` ; actions → `SUPPRESSED` (`VOIDED`) ; exécutions → `CANCELLED` (`SUBJECT_VOIDED`) | par événement |
| `INVOICE_DISPUTED` | si `collectible_minor = 0` : actions → `SUPPRESSED` (`DISPUTED`), exécutions → `PAUSED` (`DISPUTED`) | par événement |
| `INVOICE_DISPUTE_RESOLVED` | reprise des exécutions `PAUSED` (`DISPUTED`) | par événement |
| `PROMISE_CREATED` | relances standard suspendues (`PROMISE_ACTIVE`) | par événement |
| `PROMISE_BROKEN` / `_FULFILLED` / `_CANCELLED` | levée de la suspension, reprise | par événement |
| `COLLECTION_HOLD_PLACED` / `_RELEASED` | suspension / reprise (`HOLD_ACTIVE`) | par événement |
| `CUSTOMER_DEACTIVATED` / `_ARCHIVED` | actions → `SUPPRESSED` ; exécutions → `PAUSED` ; promesses client annulées | par événement |
| `ORGANIZATION_SUSPENDED` / `_CLOSED` | actions → `SUPPRESSED` (`ORG_INACTIVE`) ; exécutions → `PAUSED` (`ORG_INACTIVE`) ; communications arrêtées | par événement |
| `PAYMENT_REVERSED` | reversals d'allocations (§6), puis effets d'un reversal ci-dessus ; le paiement cesse d'être qualifiant : exécutions `PAUSED` (`RECONCILIATION_PENDING`) réévaluées | même transaction pour les allocations ; le reste par événement |
| `PAYMENT_ALLOCATED` (Collection V1.2) | le non-alloué diminue ; si plus aucun paiement qualifiant : exécutions `PAUSED` (`RECONCILIATION_PENDING`) réévaluées et reprises (`LATEST_ONLY`) ; **aucune** suppression en cascade sur `PAYMENT_CREATED` (évaluation paresseuse) | par événement |
| `PAYMENT_ALLOCATION_REVERSED` (Collection V1.2) | le montant redevient non alloué : la barrière peut réapparaître dans la fenêtre du paiement ; effet au prochain point de revalidation | par événement |
| Fin de fenêtre de rapprochement (Collection V1.2) | minuit local qui suit le dernier jour : barrière levée ; exécutions `PAUSED` (`RECONCILIATION_PENDING`) reprises par le job `ReconciliationWindowScan` ; alerte `RECONCILIATION_OVERDUE` | job |
| `APPROVAL_*` | reprise ou annulation de l'action ou de l'exécution ; l'expiration d'une approbation dont la cible est résolue est constatée par `approvals` (port `ApprovalTargetReader`), au plus une cadence de balayage plus tard | par événement |
| `IMPORT_BATCH_NORMALIZED` | libération étalée des exécutions | par événement |

Chaque cascade « par événement » est **idempotente** (`event_receipts`) et **revalide** l'état courant avant d'agir.

---

## 17. Décisions et corrections issues de cette passe

| # | Sujet | Statut |
|---|---|---|
| S1 | **`dedup_key` des actions** : unicité limitée aux actions non `CANCELLED` et non `SUPPRESSED` (sinon une action supprimée bloque à jamais sa remplaçante). Même règle pour `notifications.dedup_key` (hors `CANCELLED`). | **Correction appliquée au contrat V1.3** |
| S2 | `automation_executions.status_reason` : liste fermée de codes (voir §12), alignée sur les codes de suppression des actions. | **Appliqué au contrat V1.3** |
| S3 | Rattrapage à l'émission : une facture émise en retard reçoit immédiatement ses transitions temporelles, dans la même transaction. | **VALIDÉ, au contrat V1.3** |
| S4 | Trigger de garde **T14** (couples `(ancien, nouveau)` autorisés) sur les machines marquées 🛡. | **VALIDÉ, au contrat V1.3** |
| S5 | `VOID` refusé tant qu'un litige est `OPEN` (T15). | **VALIDÉ, au contrat V1.3** |
| S6 | Aucun déclencheur temporel rétroactif à l'activation d'une automatisation (à traiter dans la passe Automation Engine). | À traiter |
| S7 | Lien abonnement → autorisations (Billing). | À spécifier |
| S10 | Provisioning : état `PROVISIONING` de l'organisation, transitions `PROVISIONING → ACTIVE` et `PROVISIONING → CLOSED` ; `ORGANIZATION_CLOSED` traité comme `ORGANIZATION_SUSPENDED` par `collection` et `automation` ; expiration des approbations par interrogation de la cible. La table générée pour T14 gagne trois couples. | **VALIDÉ (Architecture technique, TD59), appliqué** |
| S8 | Amendements C6 (Collection Engine) : `SCHEDULED → DONE` pour les tâches humaines, `PENDING_APPROVAL → SUPPRESSED`, approbation `EXPIRED` avec `TARGET_RESOLVED`. Couples à ajouter à la table générée pour T14. | **VALIDÉ, appliqué** |
| S9 | `RECONCILIATION_PENDING` : nouvelle cause de pause d'exécution (§12) et nouvelle ligne de cascade (§16) ; aucune nouvelle machine ni transition d'action (`SCHEDULED → SUPPRESSED` existe déjà) : la table générée pour T14 ne change pas. | **VALIDÉ (Collection V1.2), appliqué** |
| S11 | **B3-a** : le recalcul du cycle de vie après annulation d'un règlement se fait dans la transaction du reversal (Invariants §3.1, Contrat §3.1), non « par événement » ni au prochain balayage ; le balayage reste un filet de sécurité. Corrige l'incohérence entre les deux premières lignes de §16 et `ApplySettlement`. | **VALIDÉ (Domain V1, tranche 1, 2026-09-21), appliqué** |
