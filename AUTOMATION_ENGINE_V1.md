# VERQIA — Automation Engine V1

Références : Data Contract V1.3 (figé, amendé par Collection Engine V1.1), Invariants V1.2, State Machines V1, Rule Engine V1.1, Collection Engine V1.1.
Statut : **V1.1 — AU1 à AU12 VALIDÉES**, avec trois formulations normatives (AU5 §4.4, AU8 §10.2, AU10 §10.1). Les amendements sont appliqués au contrat V1.3 et aux State Machines (§17).

Périmètre : déclencheurs, `trigger_key`, non-rétroactivité, répétitions, exécutions, étapes, délais, branches, pause et reprise, approbations en attente, libération d'un lot d'import, inscription des factures existantes, prévention des boucles, versions et activation, ordonnancement et exécution.
Hors périmètre : scores (Risk / Priority), fournisseurs d'envoi (Intégrations).

---

## 0. Position et principes

```
Event / Time ─→ Trigger ─→ Execution ─→ Step ─→ (Rule Engine: revalidation) ─→ Collection Engine / Notification / Request ─→ Result ─→ Event
```

L'Automation Engine **orchestre** : il décide *quand* et *dans quel ordre*, jamais *si une action a le droit de partir* (Rule Engine) ni *comment elle devient une action* (Collection Engine).

| # | Principe |
|---|---|
| AP1 | **Une exécution est une longue vie datée** : une exécution par (automatisation, sujet), qui attend ses instants et se revalide à chaque étape. Ce n'est pas une minuterie. |
| AP2 | **Toute étape se revalide** (contextes A et B du Rule Engine) avant d'agir. |
| AP3 | **Étapes à effets idempotents, exécutées au moins une fois** : un rejeu ne duplique aucun effet (`dedup_key`, clés de notification, événements `REQUEST` regroupés). |
| AP4 | **Isolation des pannes** : une exécution défaillante n'arrête ni les autres exécutions, ni les autres organisations. |
| AP5 | **Aucun déclenchement rétroactif** : une automatisation n'agit pas sur un passé qu'elle n'a pas vu (§4). |
| AP6 | **Terminaison garantie** : les branches ne vont que vers l'avant ; les répétitions sont bornées ; les boucles sont détectées statiquement et limitées à l'exécution (§11). |
| AP7 | **Explicabilité** : chaque étape enregistre sa revalidation ; on peut toujours dire pourquoi une étape a agi, attendu, sauté ou suspendu. |
| AP8 | **Le tenant est une entrée** : l'organisation et le sujet sont vérifiés à chaque chargement. |

---

## 1. La définition (schéma JSON v1)

Une définition est un objet immuable stocké dans `automation_versions.definition`, validé **avant** insertion (§13 et Rule Engine §5). Structure :

| Clé | Contenu |
|---|---|
| `schema_version` | `"1"` |
| `trigger` | `{"type": <nom d'événement> \| "TIME", …}` (§2). `trigger.type` alimente la colonne générée `automation_versions.trigger_type` |
| `options` | `concurrency` (`SINGLE_PER_SUBJECT`, seule valeur V1), `catch_up` (`NONE` ou `LATEST_ONLY`, §4), `reenroll_on_settlement_revert` (booléen, défaut vrai, §9) |
| `conditions` | condition racine évaluée au déclenchement (langage du Rule Engine §4) |
| `exceptions` | exceptions supplémentaires (jamais de retrait, Rule Engine P4) |
| `levels` | table de niveaux (Collection Engine §3) |
| `steps` | liste ordonnée d'étapes (§5) |

Exemple abrégé (les deux premières étapes du gabarit par défaut) :

```json
{
  "schema_version": "1",
  "trigger": { "type": "INVOICE_ISSUED" },
  "options": { "concurrency": "SINGLE_PER_SUBJECT", "catch_up": "NONE",
               "reenroll_on_settlement_revert": true },
  "conditions": { "fact": "invoice.is_open", "op": "eq", "value": true },
  "levels": [ { "level": 5, "when": { "...": "..." } }, "..." ],
  "steps": [
    { "id": "s1", "kind": "ACTION",
      "at": { "anchor": "invoice.due_date", "offset_days": -14, "time_of_day": "09:00" },
      "action": { "type": "CREATE_REMINDER", "level_range": [1, 1], "channels": ["EMAIL"],
                  "template": "reminder_l1_preventive", "approval": "POLICY" } },
    { "id": "s2", "kind": "ACTION",
      "at": { "anchor": "invoice.due_date", "offset_days": "-due_soon_days", "time_of_day": "09:00" },
      "action": { "type": "CREATE_REMINDER", "level_range": [2, 2], "channels": ["EMAIL"],
                  "template": "reminder_l2_due_soon", "approval": "POLICY" } }
  ]
}
```

Le gabarit par défaut du Collection Engine (§3.2 de `COLLECTION_ENGINE_V1.md`) devient donc **un seul workflow** déclenché à l'émission de la facture, avec six étapes datées, et non six déclencheurs.

---

## 2. Déclencheurs

| Type | Déclenchement | Sujet |
|---|---|---|
| **Événement** (`trigger.type` = nom d'événement) | à la consommation de l'événement par le répartiteur | selon le tableau ci-dessous |
| **Temps** (`trigger.type` = `TIME`) | instant `ancre + décalage` atteint, détecté par le balayeur temporel | facture ou promesse (l'ancre le détermine) |
| **Inscription** (interne) | activation avec inscription, libération d'un lot d'import, ré-inscription après annulation de règlement, reprise d'un échec | facture |

**Événements utilisables comme déclencheur (V1)** et sujet de l'exécution (`automation_executions.subject_type`) :

| Événements | Sujet |
|---|---|
| `INVOICE_ISSUED`, `INVOICE_DUE_SOON`, `INVOICE_DUE`, `INVOICE_OVERDUE`, `INVOICE_PARTIALLY_PAID`, `INVOICE_PAID`, `INVOICE_SETTLEMENT_REVERTED`, `INVOICE_DISPUTED`, `INVOICE_DISPUTE_RESOLVED`, `INVOICE_VOIDED`, `PRIORITY_CHANGED` | `INVOICE` |
| `PAYMENT_CREATED`, `PAYMENT_ALLOCATED`, `PAYMENT_ALLOCATION_REVERSED`, `PAYMENT_REVERSED` | `PAYMENT` |
| `PROMISE_CREATED`, `PROMISE_FULFILLED`, `PROMISE_BROKEN`, `PROMISE_CANCELLED` | `PROMISE` |
| `RISK_CHANGED` | `CUSTOMER` |

- Les événements de catégorie `REQUEST` ne déclenchent jamais une automatisation (ce sont des commandes à un moteur).
- **`CASHFLOW_UPDATED` n'est pas utilisable en V1** : l'exécution a besoin d'un sujet, et le contrat ne prévoit pas de sujet `ORGANIZATION` (AU3). Les alertes de trésorerie arriveront avec cet ajout.
- **Type d'action et sujet** : une action de recouvrement exige un sujet `INVOICE`. Un sujet `CUSTOMER`, `PAYMENT` ou `PROMISE` ne peut produire que des notifications, des alertes responsable et des demandes de recalcul (`DEFINITION_ACTION_SUBJECT_MISMATCH`).

**Déclencheur temporel** : `{"type":"TIME","anchor":"invoice.due_date","offset_days":-14,"time_of_day":"06:00"}` avec, en option, `every_days` et `max_occurrences` (≤ 12, `every_days` ≥ 3) pour une répétition. Ancres autorisées : `invoice.due_date`, `invoice.issue_date`, `promise.promised_date`.

---

## 3. Le `trigger_key` : identité d'un déclenchement

`UNIQUE (automation_id, trigger_key, subject_id)` (contrat §8.3) rend chaque déclenchement idempotent.

| Source | `trigger_key` | Indice d'occurrence `n` |
|---|---|---|
| Événement | `event:{event_id}` | 0 |
| Temps, unique | `time:{ancre}{±N}d:{sujet}#0` | 0 |
| Temps, récurrent | `time:{ancre}{±N}d:{sujet}#{n}` | n |
| Ré-inscription après annulation de règlement | `event:{event_id}` (l'événement `INVOICE_SETTLEMENT_REVERTED`) | 0 |
| Activation avec inscription | `enroll:{automation_version_id}:{sujet}` | 0 |
| Libération d'un lot d'import | `import-release:{batch_id}:{sujet}` | 0 |
| Reprise manuelle d'une exécution échouée | `retry:{execution_id}` | 0 |

**Occurrence** (C4 du Collection Engine) : elle est **produite ici**, jamais choisie ailleurs. `occurrence = "{n}.{k}"` où `n` est l'indice du déclencheur (colonne ci-dessus) et `k` l'indice de répétition de l'étape (§5). Elle vaut `0.0` par défaut. `k` se déduit des lignes `automation_execution_steps` déjà écrites pour cette étape (append-only, donc déterministe).

Deux automatisations qui aboutissent à la même action se **dédupliquent** par la `dedup_key` du Collection Engine (stratégie `DEDUPLICATE`, la seule en V1). Les stratégies `PRIORITIZE`, `MERGE`, `ESCALATE` de la Phase 6 ne sont pas retenues.

---

## 4. Non-rétroactivité (AP5)

Une automatisation ne doit pas agir sur un passé qu'elle n'a pas observé. Sans cela, activer « relance à J+10 » sur une organisation qui a déjà 300 factures en retard déclencherait tout d'un coup.

### 4.1 Référentiels

| Notion | Source |
|---|---|
| `active_since` | instant où l'automatisation est devenue `ACTIVE` avec sa version courante ; remis à jour à chaque passage à `ACTIVE` et à chaque changement de version courante (colonne `automations.active_since`). Avec une inscription, c'est l'`as_of` de l'aperçu (§10.2) |
| Instant d'émission d'une facture | `invoices.issued_at` |
| Âge d'un événement | `now − events.occurred_at` |

### 4.2 Règles

1. **Événements** : un événement dont `occurred_at < active_since` ne déclenche rien. Un événement de plus de 72 h au moment du traitement est écarté (compteur `trigger_dropped_stale`) : un retard d'outbox ne doit pas produire des actions tardives.
2. **Déclencheurs temporels** : un instant `t` ne se déclenche que si `t >= active_since`, `t >= invoices.issued_at` (pour une ancre de facture) et `now − t <= tolérance` (48 h par défaut : panne de balayeur). Il se déclenche **au plus une fois** (`trigger_key`).
3. **Étapes datées** (`at`) d'une exécution : quand l'exécution atteint une étape dont l'instant `t` est passé :
   - `now − t <= tolérance` → exécution normale (le retard s'explique par l'ordonnancement) ;
   - sinon l'étape est **PASSÉE** et la politique `catch_up` s'applique :

| `catch_up` | Effet |
|---|---|
| `NONE` (défaut) | l'étape est `SKIPPED` (`PAST_DEADLINE`) |
| `LATEST_ONLY` | seule la dernière étape **applicable** d'une séquence continue d'étapes échues est exécutée, maintenant (étalée) ; les précédentes sont `SKIPPED` (`SUPERSEDED`). Définition normative : §4.4 |

4. **Contextes où `LATEST_ONLY` s'impose** : reprise d'une exécution `PAUSED` (une exécution suspendue vingt jours ne doit pas perdre son escalade), libération d'un lot d'import, ré-inscription après annulation de règlement. **Enrôlement à l'activation** : choix explicite (§10).
5. `LATEST_ONLY` ne saute jamais une étape sans que la **non-régression** et les exceptions du Rule Engine soient réévaluées à l'exécution.

### 4.3 Illustration

| Situation | Résultat |
|---|---|
| Facture émise à J-3 ; gabarit par défaut (`NONE`) | S1 (J-14) et S2 (J-7) : `SKIPPED` `PAST_DEADLINE` ; S3 à S6 s'exécutent à leurs dates |
| Exécution suspendue 20 jours par un litige, reprise à J+30 | S3 (J+3) et S4 (J+10) : `SKIPPED` `SUPERSEDED` ; S5 (J+15) exécutée maintenant si les conditions le permettent ; S6 (J+30) à sa date |
| Balayeur arrêté 30 h | l'instant J-14 manqué se déclenche à la reprise (dans les 48 h) |
| Balayeur arrêté 5 jours | l'instant manqué est écarté, compté, signalé par alerte |

### 4.4 Définition normative de `LATEST_ONLY` (AU5)

> **Parmi les étapes datées devenues échues, on conserve uniquement la dernière étape applicable de la séquence continue ; les précédentes sont `SKIPPED` (`SUPERSEDED`). L'étape conservée repasse par le Rule Engine puis par le Collection Engine comme n'importe quelle étape : le rattrapage ne contourne jamais un garde-fou.**
>
> **Invariant : une sélection `LATEST_ONLY` n'est jamais une autorisation d'exécution** (Engine Contracts X15).

`LATEST_ONLY` ne veut jamais dire « prendre arbitrairement la dernière étape du workflow ». Précisions :

1. **Étapes concernées** : les étapes **datées** (`at` ou `after`) de type `ACTION`, `NOTIFY`, `REQUEST`, `APPROVAL`. Les étapes de contrôle sans instant (`BRANCH`, `STOP`) sont toujours évaluées ; un `WAIT` ou un `DELAY` dont l'instant est passé se franchit aussitôt.
2. **Séquence continue** : les étapes échues consécutives, à partir de `current_step`, jusqu'à la première dont l'instant est futur. Une étape future n'est jamais rattrapée.
3. **Applicable** : une étape est applicable si le niveau calculé avec les faits **courants** appartient à sa plage `level_range` (et si sa condition d'étape éventuelle est vraie). On part de la dernière étape échue et on remonte jusqu'à la première étape applicable. Si aucune n'est applicable, aucune ne s'exécute.
4. **Garde-fous** : la sélection faite, l'étape est évaluée normalement (contexte B). Si une exception s'applique (`PAID`, `DISPUTED`, `PROMISE_ACTIVE`, `HOLD_ACTIVE`…), elle suit la traduction du §6.2 (pause, annulation ou saut) : **il n'y a pas de repli sur l'étape précédente**. La non-régression du Rule Engine s'applique aussi.
5. **Répétitions** : les occurrences échues d'une étape répétée comptent chacune comme une étape échue ; seule la plus récente est candidate.
6. **Déterminisme** : la sélection ne dépend que de l'exécution, de `as_of` et des faits : deux évaluations identiques choisissent la même étape.
7. **Trace** : chaque étape écartée porte `SKIPPED` / `SUPERSEDED` et la référence de l'étape retenue.

Exemple : exécution suspendue vingt jours, reprise avec S3, S4 et S5 échues. Si le niveau courant est 4, S5 est applicable : seule S5 est candidate. Si le niveau courant est 3, S5 (plage 4) ne l'est pas : S4 (plage 3–4) est retenue. Si S5 est retenue mais que la facture est entre-temps `PAID`, l'exécution est annulée (`SUBJECT_PAID`) : S4 ne part pas à sa place.

---

## 5. Étapes

| `kind` | Rôle | Support du contrat |
|---|---|---|
| `ACTION` | crée une action de recouvrement (`CREATE_COLLECTION_ACTION`, `CREATE_REMINDER`, `CREATE_TASK`, `ASSIGN_TASK`, `ESCALATE`) | Collection Engine ; `automation_execution_steps.step_type = ACTION` |
| `NOTIFY` | `CREATE_NOTIFICATION`, `CREATE_MANAGER_ALERT` | notification interne ; `step_type = ACTION` |
| `REQUEST` | `REQUEST_RISK_RECALCULATION`, `REQUEST_PRIORITY_RECALCULATION`, `REQUEST_CASHFLOW_RECALCULATION` | événement `REQUEST` ; `step_type = ACTION` |
| `APPROVAL` | `REQUEST_APPROVAL`, `REQUEST_REVIEW` | `approvals` ; `step_type = APPROVAL` |
| `WAIT` | attend un instant (`at`) | `step_type = WAIT` |
| `DELAY` | attend une durée relative (`after`) | `step_type = WAIT` |
| `BRANCH` | saute vers une étape ultérieure selon une condition | `step_type = BRANCH` |
| `STOP` | termine l'exécution (`COMPLETED`) avec un motif | `step_type = STOP` |

- **Liste blanche** (contrat §8.2) : `UPDATE_PRIORITY` n'existe pas (D2).
- **`PAUSE`** figure dans la liste blanche de la Phase 6, mais ce n'est **pas une étape** : c'est un contrôle d'exécution (pause par un utilisateur ou par le système, §7).
- **`BRANCH`** : `{"kind":"BRANCH","if":<condition>,"then_goto":"s5","else_goto":"s6"}`. Un `goto` ne peut viser qu'une étape **postérieure** dans la liste. Ainsi l'exécution d'une définition termine toujours (AP6).
- **Instant d'une étape** : `at` (ancre, décalage en jours, heure locale) ou `after` (durée depuis la fin de l'étape précédente). Les décalages sont calculés à l'heure de l'organisation (C10).
- **Répétition d'une étape** : `repeat: {"every_days": 7, "max_occurrences": 4}`. `every_days ≥ 3`, `max_occurrences ≤ 12` ; la répétition s'arrête si la facture cesse d'être recouvrable. L'indice de répétition `k` alimente l'`occurrence` (§3).
- **Comportement par défaut** d'une étape supprimée par une exception : voir §6.2.

---

## 6. Déroulement d'une exécution

### 6.1 Boucle

```
choisir une exécution (PENDING, ou WAITING dont resume_at <= maintenant) — verrou sans blocage
  → RUNNING
  répéter :
    étape = étapes[current_step]
    si l'étape a un instant :
        t > maintenant           → WAITING (resume_at = t) ; fin du passage
        t passé au-delà de la tolérance → politique catch_up (§4.2)
    revalider (Rule Engine, contexte B) → décision
        SUPPRESS  → traduction §6.2
        SKIP      → étape SKIPPED (raison), étape suivante
        DEFER     → WAITING (resume_at = retry_at)
        PROCEED   → effectuer l'étape (Collection Engine, notification, demande, approbation, branche, arrêt)
    écrire la ligne de l'étape (avec revalidation_result), avancer current_step
    dernière étape terminée → COMPLETED
```

**Trois transactions par étape** (Architecture technique, TD31 et TD58) : (1) **réclamer** l'exécution (`PENDING`/`WAITING` → `RUNNING`, qui sert de bail) ; (2) l'**effet**, dans la transaction du module propriétaire (action par `collection`, notification par `notifications`, approbation par `approvals`), idempotent ; (3) **enregistrer** la ligne d'étape et le nouvel état de l'exécution. Une panne entre deux temps laisse un état repris par le `Reaper` ; une étape rejouée ne duplique rien, parce que chaque effet est idempotent (AP3, AU11). Une même transaction ne verrouille jamais l'exécution puis crée l'action : c'est l'ordre inverse de l'échelle des verrous.

### 6.2 Traduction d'une exception (Rule Engine §3.2)

| Exception | Effet sur l'exécution |
|---|---|
| `ORG_INACTIVE`, `CUSTOMER_INACTIVE`, `CUSTOMER_ARCHIVED`, `DISPUTED`, `PROMISE_ACTIVE`, `HOLD_ACTIVE`, `IMPORT_HELD`, `RECONCILIATION_PENDING` | `PAUSED` avec `status_reason` = le code |
| `PAID` | `CANCELLED` (`SUBJECT_PAID`) |
| `VOIDED` | `CANCELLED` (`SUBJECT_VOIDED`) |
| `FREQUENCY_LIMIT`, `NO_CONTACT`, `NO_CONSENT` | étape `SKIPPED` ; le Collection Engine applique le repli humain (Collection §10) ; l'exécution continue |

### 6.3 Statuts d'une ligne d'étape

`COMPLETED` (effet réalisé) · `SKIPPED` (rien à faire, raison enregistrée) · `SUSPENDED` (exécution mise en pause) · `STOPPED` (exécution annulée) · `FAILED` (échec technique).

---

## 7. Pause et reprise

Une exécution `PAUSED` porte la **cause** (`status_reason`). Elle reprend **uniquement quand la cause est levée**, jamais au bout d'un délai.

| Cause | Levée par |
|---|---|
| `DISPUTED` | `INVOICE_DISPUTE_RESOLVED`, ou passage à un montant recouvrable > 0 |
| `PROMISE_ACTIVE` | `PROMISE_FULFILLED`, `PROMISE_BROKEN`, `PROMISE_CANCELLED` |
| `HOLD_ACTIVE` | `COLLECTION_HOLD_RELEASED` (y compris par expiration) |
| `CUSTOMER_INACTIVE` | `CUSTOMER_REACTIVATED` |
| `CUSTOMER_ARCHIVED` | `CUSTOMER_REACTIVATED` (jamais automatique, D6) |
| `ORG_INACTIVE` | `ORGANIZATION_REACTIVATED` |
| `IMPORT_HELD` | `IMPORT_BATCH_RELEASED` ou reprise de la libération |
| `RECONCILIATION_PENDING` | `PAYMENT_ALLOCATED` (plus aucun paiement qualifiant), `PAYMENT_REVERSED`, ou **fin de fenêtre** constatée par le job `ReconciliationWindowScan` (minuit local qui suit le dernier jour de suspension) |
| `AUTOMATION_PAUSED` | `AUTOMATION_ACTIVATED` (reprise de l'automatisation) |
| `USER` | reprise explicite par un utilisateur autorisé |

*Amendement Collection V1.2 : `RECONCILIATION_PENDING` est une cause de pause ; `PAYMENT_ALLOCATION_REVERSED` peut la recréer dans la fenêtre du paiement. Une automatisation ne crée ni ne consomme jamais de contournement (`OverrideGrant`).*

**Réaction à la levée** (`ResumeReactor`, idempotent) : pour chaque exécution `PAUSED` concernée, réévaluer les garde-fous ; si une **autre** cause subsiste, la mettre à jour (`status_reason`) et rester `PAUSED` ; sinon `PAUSED → PENDING` avec `catch_up = LATEST_ONLY` (§4.2). La reprise se fait **à l'étape courante, revalidée**.

Une exécution `PAUSED` depuis plus de 180 jours déclenche une alerte interne ; elle n'est pas annulée automatiquement.

**`PAUSED` n'est pas `WAITING`** : `WAITING` = attente prévue (instant, approbation, nouvelle tentative) avec `resume_at` ; `PAUSED` = suspension sur cause, sans échéance.

---

## 8. Approbations en attente

Une étape `APPROVAL` crée l'approbation (Collection §6 pour les actions de recouvrement, cette étape pour les autres) et place l'exécution en `WAITING` avec `resume_at = approbation.expires_at`.
- La décision (`APPROVAL_GRANTED` ou `_REJECTED`) réveille l'exécution tout de suite (`resume_at = maintenant`).
- Accordée : suite de l'étape, **revalidée**. Refusée ou expirée : l'exécution suit la branche `on_rejected` de l'étape si elle existe, sinon `CANCELLED` avec le motif `USER`. *(À préciser avec les branches de refus en passe UX.)*
- Si la cible est résolue pendant l'attente : l'approbation passe en `EXPIRED` (`TARGET_RESOLVED`) et l'exécution est annulée pour `SUBJECT_PAID` ou `SUBJECT_VOIDED`.

---

## 9. Concurrence, ré-inscription, reprise d'un échec

**Concurrence (AU6).** Une seule exécution non terminale par (automatisation, sujet) : `SINGLE_PER_SUBJECT`. Un nouveau déclenchement pendant qu'une exécution est active est écarté (`SKIPPED`, `EXECUTION_IN_PROGRESS`, compteur). Imposé par la base : index unique partiel (amendement AU12).

**Ré-inscription (AU7).** Quand `INVOICE_SETTLEMENT_REVERTED` survient, toute automatisation active de sujet `INVOICE` qui a déjà inscrit cette facture (une exécution existe, quel que soit son statut) et dont `options.reenroll_on_settlement_revert` est vrai crée une **nouvelle exécution** (`trigger_key = event:{event_id}`, `catch_up = LATEST_ONLY`). Sans cela, une facture soldée puis rouverte après la fin du parcours ne serait plus jamais relancée. Le nouveau `collection_cycle` ouvre de nouvelles clés de déduplication.

**Reprise d'un échec.** Une exécution `FAILED` est terminale. Un utilisateur `MANAGER` ou plus peut en lancer une nouvelle (`trigger_key = retry:{execution_id}`, `catch_up = LATEST_ONLY`) ; la déduplication empêche tout doublon d'effet.

---

## 10. Import par lots et inscription des factures existantes

### 10.1 Libération d'un lot (`import_batches`)

Le répartiteur ignore les événements portant `import_batch_id` tant que le lot n'est pas au moins `RELEASING` (contrat §12.6). À la libération, `ImportReleaser` (travail **composé par `jobs`** : `automation.ReleaseImportTranche`, puis `imports.CompleteImportRelease`, chacun dans sa transaction) :
1. sélectionne les factures ouvertes du lot ;
2. les trie par **priorité** (`priority_items.rank_score` décroissant, puis échéance croissante) ;
3. crée, pour chaque automatisation active de sujet `INVOICE`, une exécution `trigger_key = import-release:{batch_id}:{sujet}`, `catch_up = LATEST_ONLY` ;
4. leur attribue des `resume_at` **étalés** : au plus `import_batches.release_max_per_day` exécutions **démarrent** par jour, dans l'ordre de priorité ;
5. passe le lot à `RELEASED` quand toutes les exécutions sont **créées et planifiées**.

**Normatif (AU10) : `release_max_per_day` limite le démarrage des exécutions, jamais leur création.** Les N exécutions d'un lot existent dès la libération, au statut `WAITING` avec `resume_at` = créneau de démarrage ; le plafond ne détermine que les `resume_at`. `RELEASED` signifie « toutes créées et planifiées », pas « toutes démarrées ». Le système sait ainsi, à tout moment, combien de factures du lot sont planifiées, démarrées, terminées, suspendues ou en échec (comptage des exécutions par statut, préfixe de `trigger_key` `import-release:{batch_id}:`).

Pause de la libération (`RELEASE_PAUSED`) : les exécutions du lot qui n'ont pas démarré passent `PAUSED` (`IMPORT_HELD`) ; à la reprise, elles repartent avec des créneaux recalculés. Le mode `HOLD` du lot laisse tout en attente jusqu'à une commande explicite.

### 10.2 Activation avec inscription

Activer une automatisation ne touche que les événements **futurs**. Pour gérer aussi les factures déjà ouvertes, la commande d'activation porte un **`enrollment_mode` obligatoire** (pas de valeur par défaut, pour forcer un choix) :

| Mode | Effet |
|---|---|
| `NONE` | aucune facture existante inscrite |
| `FUTURE_ONLY` | inscription des factures ouvertes ; seules leurs étapes futures s'exécutent (`catch_up = NONE`) |
| `LATEST_STEP` | inscription des factures ouvertes ; la dernière étape applicable et échue de chacune s'exécute (`catch_up = LATEST_ONLY`, §4.4), étalée |

`trigger_key = enroll:{automation_version_id}:{sujet}`. Étalement : `org_settings.extra.enroll_max_per_day` (défaut 100) limite le **démarrage**, comme pour un lot d'import (§10.1).

**Aperçu (AU8, normatif).** Pour `FUTURE_ONLY` et `LATEST_STEP`, l'activation exige un aperçu, qui est une **simulation sans effet** :

1. **`as_of` explicite**, enregistré avec l'aperçu, pour que la simulation soit reproductible ; l'aperçu expire au bout de 15 minutes.
2. **Même logique de décision que l'exécution réelle** : faits, Rule Engine, Automation Engine, Collection Engine, en mode sans écriture. **Aucune** écriture, aucun événement métier, aucune notification, aucune action, aucune exécution.
3. **Résultat** : `as_of`, nombre de factures, répartition par étape et par jour, et une **empreinte** (SHA-256 de la version, du mode, de `as_of` et de la liste triée des sujets inscrits). L'empreinte est plus forte que le simple nombre : 143 factures peuvent devenir 143 *autres* factures.
4. **Vérification atomique** : la commande d'activation porte `(as_of, nombre attendu, empreinte)`. Dans **une seule transaction** à instantané stable, le moteur recalcule l'inscription avec le même `as_of` ; si l'empreinte diffère, il **n'écrit rien** et renvoie `ENROLLMENT_PREVIEW_STALE` (aussi pour un aperçu expiré) ; **aucune inscription partielle n'est jamais conservée** : l'activation est tout ou rien. Sinon, dans la même transaction : création des exécutions, `active_since = as_of` de l'aperçu, passage à `ACTIVE`.
5. **Pourquoi `active_since = as_of`** : une facture émise entre l'aperçu et l'activation n'est pas dans l'inscription (postérieure à `as_of`) mais son événement l'est aussi : il déclenche normalement. Aucune facture n'est perdue ni inscrite deux fois.
6. **Test différentiel** : pour tout jeu de données, l'aperçu doit coïncider avec l'exécution réelle rejouée en horloge virtuelle.

Sans inscription (`NONE`), `active_since` = instant de la transaction d'activation.

---

## 11. Prévention des boucles (AU9, AP6)

| Niveau | Mécanisme |
|---|---|
| **Définition** | branches vers l'avant seulement ; répétitions bornées ; validation statique (`DEFINITION_TRIGGER_LOOP` : une action émet l'événement qui la déclenche) |
| **Ensemble actif** | à l'**activation**, graphe des automatisations actives de l'organisation : une arête relie une action `REQUEST_x_RECALCULATION` à l'événement de résultat correspondant (`RISK_CHANGED`, `PRIORITY_CHANGED`, `CASHFLOW_UPDATED`) qui peut déclencher une autre automatisation ; un **cycle** refuse l'activation (`AUTOMATION_SET_LOOP_DETECTED`). Exemple : A (sur `RISK_CHANGED`, demande un recalcul de priorité) et B (sur `PRIORITY_CHANGED`, demande un recalcul de risque) |
| **Exécution** | `events.causation_depth ≤ 20` ; au plus **10 exécutions démarrées par sujet et par 24 h** et par automatisation (`EXECUTION_RATE_LIMITED`) ; événements `REQUEST` regroupés |
| **Alerte** | toute limite atteinte génère une alerte |

---

## 12. Versions et activation

**Versions.** Toute modification crée une version immuable (`version_no` suivant). Une exécution en cours reste liée à **sa** version ; les nouvelles exécutions utilisent la version courante. Pas de migration d'une exécution en vol. Un retour arrière = une **nouvelle version** copiant l'ancienne définition.

**Préconditions d'activation** (N13, `DRAFT → ACTIVE` ou `PAUSED → ACTIVE`). Échec : `AUTOMATION_PRECONDITIONS_NOT_MET` avec la liste des codes suivants.

| Code | Précondition |
|---|---|
| `PRECOND_ROLE` | l'auteur est `OWNER` ou `ADMIN` |
| `PRECOND_ORG_ACTIVE` | organisation `ACTIVE` ; abonnement qui autorise les automatisations *(lien Billing, S7)* |
| `PRECOND_DEFINITION_VALID` | version courante conforme au schéma, faits, actions, canaux activés, plages de niveaux |
| `PRECOND_TEMPLATES_ACTIVE` | gabarits `ACTIVE` pour chaque canal et gabarit utilisés, dans la langue par défaut de l'organisation |
| `PRECOND_CHANNEL_READY` | expéditeur `EMAIL` disponible *(fourni par les Intégrations ; en V1, expéditeur de plateforme)* |
| `PRECOND_COMM_SETTINGS` | fenêtre de communication valide, au moins un jour ouvré |
| `PRECOND_APPROVER_EXISTS` | si une étape utilise l'approbation : au moins un membre `MANAGER` ou plus avec une limite d'approbation |
| `PRECOND_NO_LOOP` | aucun cycle dans l'ensemble actif (§11) |
| `PRECOND_ENROLLMENT_CHOSEN` | `enrollment_mode` renseigné (§10.2) |

Tant qu'elle n'est pas `ACTIVE`, une automatisation ne produit **aucune exécution**. `automations.active_since` est fixé à l'activation (§4.1) ; avec inscription, c'est l'`as_of` de l'aperçu (§10.2).

---

## 13. Exécutable

| Composant | Rôle |
|---|---|
| `EventDispatcher` | consomme l'outbox ; trouve les automatisations actives par `trigger_type` ; applique la non-rétroactivité et les conditions racines ; crée les exécutions (`trigger_key`) |
| `TimeTriggerScanner` | à intervalle régulier, détecte les instants atteints (requêtes par date d'ancre, index `(organization_id, due_date)` du contrat) ; crée les exécutions |
| `ExecutionWorker` | boucle du §6.1 ; verrou `FOR UPDATE SKIP LOCKED` sur `(status, resume_at)` |
| `ResumeReactor` | §7 |
| `ImportReleaser`, `EnrollmentRunner` | §10 |
| `Reaper` | reprend une exécution `RUNNING` depuis plus de 10 minutes (panne de worker) : retour en `WAITING`, `retry_count + 1` |
| `DefinitionValidator` | Rule Engine §5, plus §11 |
| `ActivationService` | préconditions, `active_since`, inscription |

**Équité entre organisations.** Chaque passage du worker prend les exécutions **à tour de rôle par organisation**, avec un plafond de traitement concurrent par organisation (20 par défaut) : une organisation qui inscrit 5 000 factures ne retarde pas les autres.

**Nouvelles tentatives d'étape.** Échec technique transitoire d'une étape : `RUNNING → WAITING` (`retry_count + 1`, attente de 1 min, 5 min, 30 min) ; au-delà de 3 tentatives, `FAILED` avec `failure_reason` et alerte. Les exécutions défaillantes n'empêchent jamais le traitement des autres (AP4).

**Limite du `Reaper`.** Une exécution reprise par le `Reaper` n'apporte **aucune preuve** que l'effet externe de l'étape n'a pas eu lieu : un e-mail peut avoir été accepté par le fournisseur alors que le worker est tombé avant d'écrire le résultat. La garantie finale contre un doublon repose sur l'idempotence côté fournisseur (clé `{notification_id}:{attempt_no}`, passe Intégrations) ; l'Automation Engine garantit seulement des effets idempotents (`dedup_key`, clés de notification).

**Explicabilité (historique d'exécution).** Chaque ligne de `automation_execution_steps` affiche : étape, instant prévu, raison d'un saut, faits utilisés, exceptions évaluées, décision, résultat. L'interface les présente sous la forme de la Phase 6 (« Conditions ✓ … Décision : exécution autorisée … Actions ✓ … »).

**Audit (D3).** Sont audités : activation, pause et reprise **par un utilisateur**, désactivation, inscription (avec le nombre annoncé), reprise d'un échec, libération d'un lot. Les pauses et reprises **systèmes** restent dans l'historique des étapes.

---

## 14. Testable

| Famille | Contenu |
|---|---|
| **Simulation à horloge virtuelle** | une définition et une chronologie d'événements sont rejouées jour par jour ; on compare exécutions, étapes et actions à un résultat attendu |
| **Scénario de référence** | la chronologie du Collection Engine (§11), rejouée de bout en bout avec le gabarit par défaut |
| **Non-rétroactivité** | activation avec des factures anciennes ; émission tardive ; événement antérieur à `active_since` ; balayeur arrêté 30 h et 5 jours |
| **`catch_up`** | `NONE` et `LATEST_ONLY` ; reprise après pause de 20 jours ; libération d'import |
| **Idempotence** | chaque événement rejoué deux fois donne le même état final ; deux workers concurrents sur la même exécution ; panne entre l'effet et l'écriture de la ligne |
| **Pause et reprise** | chaque cause et sa levée ; deux causes simultanées ; levée d'une seule |
| **Concurrence** | déclenchement pendant une exécution active ; ré-inscription après règlement annulé ; reprise d'un échec |
| **Terminaison** | toute définition valide termine (branches vers l'avant) ; répétitions bornées |
| **Boucles** | A/B en cycle refusées à l'activation ; profondeur de causalité ; limite par sujet |
| **Import** | 5 000 factures : au plus `release_max_per_day` démarrages par jour, ordre de priorité, pause et reprise |
| **Isolation** | une exécution qui échoue ne bloque pas les autres ; deux organisations ne se voient jamais ; équité entre organisations |
| **Validateur** | une définition invalide par code d'erreur ; ensemble d'automatisations cyclique |

---

## 15. Observable

| Signal | Contenu |
|---|---|
| **Compteurs** | exécutions par statut ; déclenchements par type ; sauts par raison (`PAST_DEADLINE`, `SUPERSEDED`, `EXECUTION_IN_PROGRESS`) ; pauses par cause ; reprises ; déclenchements écartés (obsolètes, hors tolérance, limités) |
| **Retards** | `resume_at` dépassé (retard du worker) ; retard du balayeur temporel ; âge de l'événement le plus ancien non consommé |
| **Files** | exécutions `PENDING` et `WAITING` échues ; exécutions `PAUSED` par cause et par ancienneté ; lots d'import en cours de libération |
| **Santé** | taux de `FAILED` ; exécutions `RUNNING` reprises par le `Reaper` ; approbations expirées |
| **Sécurité** | limites de boucle atteintes ; refus d'activation pour boucle |
| **Journaux** | un enregistrement par étape : `organization_id`, `correlation_id`, `execution_id`, `step_id`, issue, durée ; jamais de donnée personnelle |
| **Alertes** | retard du balayeur > 1 h ; instants manqués hors tolérance ; taux d'échec anormal ; exécutions `PAUSED` de plus de 180 jours ; boucle détectée |

---

## 16. Ce que reçoivent les passes suivantes

- **Engine Contracts** : la chaîne complète Event → Trigger → Execution → Step → Rule Engine → Collection Engine, avec ses clés d'idempotence (`trigger_key`, `dedup_key`, `event_receipts`) et son barème de non-rétroactivité.
- **Risk / Priority** : la liste finale des `refresh_events` ; le tri des libérations d'import par `rank_score`.
- **Intégrations** : `PRECOND_CHANNEL_READY`, l'adaptateur d'envoi.
- **Architecture technique** : ordonnancement (balayeur, worker, reaper), équité par organisation, index.

---

## 17. Décisions (V1.1)

**AU1 à AU12 : VALIDÉES.** Trois formulations normatives ont été ajoutées à la demande de la revue :

| # | Formulation normative | Où |
|---|---|---|
| **AU5** | `LATEST_ONLY` : dernière étape **applicable** d'une séquence continue d'étapes datées échues ; jamais un contournement du Rule Engine | §4.4 |
| **AU8** | Aperçu : simulation **sans effet**, `as_of` explicite, même logique que l'exécution, puis **vérification atomique** de l'empreinte avant inscription | §10.2 |
| **AU10** | `release_max_per_day` limite le **démarrage** des exécutions, **pas leur création** ; `RELEASED` = toutes créées et planifiées | §10.1 |

Précision **AU11** : le `Reaper` ne prouve pas que l'effet externe n'a pas eu lieu (§13). La garantie finale contre un doublon d'envoi repose sur l'idempotence du fournisseur, spécifiée par la passe Intégrations.
Précision **AU12** : l'index sur `trigger_key` d'import est une **optimisation opérationnelle** ; la garantie d'idempotence reste `UNIQUE (automation_id, trigger_key, subject_id)`.

**Amendements appliqués** (contrat V1.3 et documents liés) :

| Amendement | Où |
|---|---|
| `automations.active_since` (`status = 'ACTIVE' ⇔ active_since IS NOT NULL`) | Contrat §8.1 ; State Machines §11 |
| Index unique partiel `(automation_id, subject_id) WHERE status IN ('PENDING','RUNNING','WAITING','PAUSED')` | Contrat §8.3 |
| Index d'exploitation sur `trigger_key` d'import | Contrat §8.3 |
| Grammaire du `trigger_key` | Contrat §8.3 |
| Note sur `PAUSE` (contrôle, pas étape) | Contrat §8.2 |
| Clés documentées de `org_settings.extra` (dont `enroll_max_per_day`) | Contrat §1.4 |
| Création d'exécutions étalées en `WAITING` | State Machines §12 |
