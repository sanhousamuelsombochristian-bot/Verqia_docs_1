"""Écrit `APPLICATION_CONTRACT_V1.md` : le contrat d'un cas d'usage, puis la table des 119 cas d'usage (16 colonnes), générée depuis les registres.

Usage : python architecture_registry/gen_application_doc.py [--check]
"""
import io
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_registry as B  # noqa: E402
import commands as K  # noqa: E402
import ap_catalogue as AP  # noqa: E402
import application_freeze as FZ  # noqa: E402
import gen_application as GA  # noqa: E402
import gen_contracts as G  # noqa: E402
import locks as L  # noqa: E402
import modules as M  # noqa: E402

DOC = os.path.abspath(os.path.join(HERE, '..', 'APPLICATION_CONTRACT_V1.md'))
SHORT_RETRY = {'command': 'TD30', 'handler': 'TD35', 'job': 'TD43', 'worker': 'TD31', 'service': 'appelant', 'system': 'garde'}
LOCK_ABBR = {}


def esc(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')


def lock_cell(s):
    if not s['lock_sequence']:
        return '—'
    return ' → '.join('%s:%s' % (r, m) for r, m in s['lock_sequence'])


def input_cell(s):
    if s['kind'] == 'handler':
        return 'événements'
    if s['input'].startswith('charge utile figée'):
        return 'figée : ' + s['input'].split(': ', 1)[1]
    return 'niveau C'


def tenant_cell(s):
    return {'REQUIRED': 'requise', 'EVENT': 'de l\'événement', 'ENUMERATOR': 'énumérée', 'RELAY': 'relais nommé (SYSTEM)', 'NONE': 'aucune (SYSTEM)', 'NEW': 'créée (NEW)'}[s['tenant']]


def audit_cell(s):
    return {'REQUIRED': 'requis', 'CONDITIONAL': 'conditionnel', 'NONE': '—'}[s['audit']]


ENTRY_LABEL = {'PUBLIC': 'publique', 'PROVISIONING_STEP': 'étape', 'INTERNAL': 'interne', 'REACTION': 'réaction', 'BACKGROUND': 'travail'}


def outcome_cell(s):
    return ', '.join(s['outcomes']) if s['outcomes'] else 'celles de l\'appelant'


def atomic_cell(s):
    if not s['phases']:
        return ' + '.join(s['atomic_effects']) or '—'
    return 'par phase : ' + ' → '.join('T%d %s%s' % (i, role.lower(), '' if role == 'EXTERNAL' else ' (' + ', '.join(mods) + ')') for i, (role, mods, calls, effs, what) in enumerate(s['phases'], 1))


def render():
    B.run()
    G.generate()
    specs = [GA.spec_for(c) for c in K.COMMANDS]
    per = {}
    for s in specs:
        per.setdefault(s['module'], []).append(s)
    w = []
    a = w.append
    kinds = Counter(s['kind'] for s in specs)
    named = sum(1 for s in specs if s['errors'])
    frozen_in = sum(1 for s in specs if s['input'].startswith('charge utile figée'))
    a('# VERQIA : Application Contract V1')
    a('')
    fz = FZ.read_freeze()
    if fz:
        a('> **Statut : V1 — GELÉ le %s** (empreinte `%s…`, %d fichiers). Corrections de revue RV1–RV8, D-AP1, O1 et O2 tranchées ; toute modification passe par le journal des amendements (§6). Généré par `architecture_registry/gen_application_doc.py` depuis les quatre registres gelés ; vérifié par `verify_application.py` (A1–A13) et `test_application.py`. Ne pas modifier à la main.' % (fz['frozen'], fz['sha256'][:12], fz['files']))
    else:
        a('> **Statut : en revue, non gelé.** Généré par `architecture_registry/gen_application_doc.py` ; vérifié par `verify_application.py` (A1–A13) et `test_application.py`. Ne pas modifier à la main.')
    a('> Aucun modèle, aucune migration, aucun point d\'entrée, aucun travailleur métier à cette étape. Les corrections de revue sont nommées **RV1–RV8** pour ne pas les confondre avec les propriétés de vérification A1–A13.')
    a('')
    a('## Corrections de revue')
    a('')
    a('| # | Correction | Où |')
    a('|---|---|---|')
    for r in [('RV1', '`CreateOrganization` : régime d\'organisation `NEW` (l\'organisation n\'existe pas encore), et non `REQUIRED`', '§3.2, A4'),
              ('RV2', 'AP-06 réconcilié : audit obligatoire pour les commandes **publiques** ; autres entrées seulement si nommées (D3) ; `CompleteProvisioning` : voir D-AP1', 'AP-06, §3.2, A6'),
              ('RV3', 'Commande publique et étape de provisioning distinguées (entrée dérivée et vérifiée)', 'AP-11, §3.2, A10'),
              ('RV4', '`OutboxPublisher` : réclamer / handlers dans leur transaction / poser publié (registre amendé A4, TD33)', '§3.3, A11'),
              ('RV5', '`CreateCollectionAction` : composition orchestrée (TD58), non « une transaction par module »', '§3.3, A11'),
              ('RV6', '`RunExecutionStep` : T1 réclame, T2 effet, T3 finalise ; AP-10', 'AP-10, §3.3, A11'),
              ('RV7', '`REPLAY` selon la nature ; issues par nature', 'AP-12, §3.1, A9'),
              ('RV8', 'AP-08 renforcé : cible, dépendance, sens du graphe, phase `own:`, possession de l\'état', 'AP-08, A8, A11')]:
        a('| %s | %s | %s |' % r)
    a('')
    a('### Décisions de gel (2026-09-19)')
    a('')
    a('| Point | Décision |')
    a('|---|---|')
    a('| RV1–RV8, AP-10, AP-12, phases | **validés** |')
    a('| D-AP1 | **acceptée** : `CompleteProvisioning` reste un cas d\'usage `system`, sans audit direct. Règle : audit obligatoire pour les commandes publiques ; pour les autres entrées, seulement si D3 ou un contrat l\'exige explicitement |')
    a('| O1 | **fixé au contrat** (AP-14) : `CreateOrganization` a une portée d\'idempotence `(acteur, clé, route)` ; la clé d\'idempotence n\'engendre jamais l\'identifiant d\'organisation |')
    a('| F1, F2 (2026-09-20) | **tranchés** : `TransactionScope` `TENANT` / `SYSTEM` (organisation obligatoire dans `CallContext`, `SystemContext` sans organisation) ; `IdempotencyScope` `ORGANIZATION` / `ACTOR`, typé ; amendements de noyau K1 et K2, amendement Application B1 |')
    a("| Frontières transactionnelles (2026-09-20) | **option 1, gel conservé** : `A → B.own:` = unités de travail SÉPARÉES ; la transaction de B est ouverte par le propriétaire de B ; l'appelant ne la couvre pas ; le tenant reste cohérent entre phases ; l'échec d'une phase n'annule pas les phases validées ; une phase rejouée est idempotente. TD58 et AP-13 inchangés ; aucun amendement |")
    a("| Phases sans verrou propre (2026-09-20) | **acceptée pour V1, sans amendement de TD27** : une unité secondaire d'un cas d'usage reprend la séquence de verrous de son opération, sans `K`. La séquence est DÉRIVÉE du Lock Registry généré (`Runner.unit_lock_sequence`) ; le coureur n'en détient aucune liste, et un test modifie le registre pour montrer que la dérivation le suit |")
    a('| O2 | **corrigé** : quatre rappels obsolètes (synthèse et justification de TD1 dans `TECHNICAL_ARCHITECTURE_V1.md`, DR3 dans `ENGINE_CONTRACTS_V1.md`, ligne `AR-04` de la matrice), sans rouvrir aucune décision |')
    a('')
    a('## 0. Où se situe cette couche')
    a('')
    a('| Couche | Répond à |')
    a('|---|---|')
    a('| Registry | ce qui existe |')
    a('| Contracts | ce qui est publiquement exposé |')
    a('| **Application** | **comment une opération traverse le système** |')
    a('| Domain | quelles règles métier sont vraies |')
    a('| PostgreSQL | comment l\'état est finalement persisté |')
    a('')
    a('Un cas d\'usage **n\'invente rien** : il ordonne. Il ne décide aucune règle métier (Domain) et ne connaît aucune table (infrastructure). Ses seize éléments sont de la **donnée** dérivée des registres, consommée par un seul coureur (à venir) : le pipeline n\'est pas recopié dans chaque cas d\'usage.')
    a('')
    a('## 1. Le pipeline d\'un cas d\'usage')
    a('')
    a('```')
    a('Command ─▶ CallContext ─▶ validation d\'entrée ─▶ clé d\'idempotence ─▶ transaction + TenantContext ─▶ verrous (échelle)')
    a('   ─▶ lectures par ports ─▶ Domain décide ─▶ appels inter-modules (contrats) ─▶ écritures + EventOutbox + Audit ─▶ COMMIT ─▶ résultat')
    a('```')
    a('')
    a('| # | Étape | Règle | Fondement |')
    a('|---|---|---|---|')
    steps = [
        ('P1', 'Réception (api)', 'traduit le transport en `Command` et `CallContext` ; aucune règle métier ; l\'organisation ne vient JAMAIS d\'un champ de la commande', 'K14, TD4'),
        ('P2', 'CallContext', 'organisation, acteur, corrélation, causalité et **`as_of` lu sur le port `Clock`** ; l\'heure de l\'hôte n\'est jamais du temps métier', 'TD23'),
        ('P3', 'Validation d\'entrée', 'structure seulement (types, présence, formats) ; sans lecture de base ; échec = `VALIDATION`', 'EC §0.3'),
        ('P4', 'Clé d\'idempotence', 'première ressource de l\'échelle ; un rejeu renvoie le résultat enregistré (`REPLAY`) sans aucun effet ; portée `(organisation, clé, route)`, sauf `CreateOrganization` : `(acteur, clé, route)`, consultée **avant** de générer l\'organisation (AP-14)', 'TD32, TD27, AP-14'),
        ('P5', 'Transaction + TenantContext', 'la transaction s\'ouvre, l\'organisation est posée **avant toute lecture** ; sans organisation, refus (fermé par défaut) ; **deux régimes distincts** : `NEW` (`CreateOrganization` : l\'identifiant est généré puis lié par `TenantContext.bind_new`, §3.2) et `SYSTEM` (aucune organisation, §3.4)', 'TD26, TD59, K1, K3'),
        ('P6', 'Verrous', 'la séquence du Lock Registry, rang strictement croissant ; jamais d\'ordre local', 'TD27'),
        ('P7', 'Lectures', 'par ports ; **après** les verrous ; une lecture n\'est jamais un cache de décision', 'X1, TD27'),
        ('P8', 'Domain', 'fonction pure de (état lu, commande, `as_of`) qui rend une décision ou lève une `DomainError` du catalogue ; aucune entrée-sortie', 'DR1'),
        ('P9', 'Inter-modules', 'par contrats uniquement ; appel simple = dans la transaction de l\'appelant ; `own:` = dans la transaction du propriétaire de l\'état', 'TD4, TD10, TD55, TD58'),
        ('P10', 'Écritures atomiques', 'états + `EventOutbox` + audit + résultat d\'idempotence (ou reçu du handler) dans **une même transaction**', 'TD25, TD32'),
        ('P11', 'Après COMMIT', 'seulement : publication par le relais, envois externes ; aucun effet externe dans la transaction', 'TD33, TD31'),
        ('P12', 'Résultat', 'une issue **propre à la nature du cas d\'usage** (§3.1), ou une erreur du catalogue ; jamais d\'erreur hors Annexe A ; `REPLAY` n\'est pas une issue universelle', 'EC §0.3, Annexe A'),
    ]
    for p, n, r, f in steps:
        a('| %s | %s | %s | %s |' % (p, n, r, f))
    a('')
    a('### 1.1 Les seize éléments d\'un cas d\'usage')
    a('')
    a('| Élément | Contenu | Source |')
    a('|---|---|---|')
    els = [
        ('Commande', 'la classe publique (`contracts/commands.py`) ; vide pour un handler', 'Contracts'),
        ('Use case', 'nom unique `module.Nom`', 'Command Registry'),
        ('Entrée', 'charge utile figée (EC-xx) ou « niveau C » : à figer avec le Domain', 'Contracts'),
        ('Transaction', 'une, par organisation, par pas, trois (automatisation)…', 'Command Registry'),
        ('Organisation', 'requise / de l\'événement / énumérée / relais nommé / aucune', 'TD26'),
        ('Idempotence', 'mécanisme propre au cas d\'usage', 'Command Registry'),
        ('Verrous', 'séquence ressource:mode dans l\'échelle générée', 'Lock Registry'),
        ('Lectures', 'requêtes publiées d\'un autre module (`module.Requête`)', 'Command Registry'),
        ('Domain', 'états écrits (clés d\'état), dont les seules exceptions C12', 'TD55'),
        ('Inter-modules', 'appels par contrats, `own:`, ports implémentés', 'TD10, TD58'),
        ('Événements', 'événements émis dans l\'outbox', 'Event Registry'),
        ('Audit', 'requis / conditionnel motivé / aucun', 'D3'),
        ('Erreurs', 'codes de l\'Annexe A nommés par les contrats d\'interface + classes possibles', 'Annexe A'),
        ('Résultat', 'issue et contenu renvoyé', 'EC-xx'),
        ('Reprise', 'TD30 commandes, TD35 handlers, TD43 travaux de niveau, TD31 travailleurs à bail', 'TD30, TD31, TD35, TD43'),
        ('Atomicité', 'l\'ensemble écritures + événements + audit + idempotence/reçu, indivisible', 'TD25'),
    ]
    for e, c, s in els:
        a('| %s | %s | %s |' % (e, c, s))
    a('')
    a('## 2. Invariants du contrat (AP)')
    a('')
    a('| Id | Invariant | Vérifié par |')
    a('|---|---|---|')
    inv = list(AP.INVARIANTS)
    for i, t, v in inv:
        a('| %s | %s | %s |' % (i, t, v))
    a('')
    a('## 3. Règles transversales')
    a('')
    a('- **Reprise.** Commande : rejeu borné (3) sur `40001`/`40P01`, avant tout effet externe (TD30). Handler : `RETRYING` à 10 s, 1 min, 5 min, 30 min, 2 h, puis `DEAD` (TD35). Travail : de niveau, le passage suivant rattrape (TD43). Travailleur : bail repris par le Reaper, livraison au moins une fois (TD31).')
    a('- **Audit (D3).** Requis pour toute commande et pour les actions sensibles : %s. Conditionnel : %s. Aucun pour handlers, travaux et services (historique et événements suffisent).' %
      (', '.join('`%s`' % x for x in sorted(GA.AUDIT_SENSITIVE)), '; '.join('`%s` (%s)' % (k, v) for k, v in GA.AUDIT_CONDITIONAL.items())))
    a('- **Erreurs.** Une classe possible ne veut pas dire un code : les codes nommés (%d cas d\'usage) sont ceux que les contrats d\'interface figent ; pour les autres, seule la classe est déclarée. Les codes manquants se figeront avec le Domain (niveau C).' % named)
    a('')
    a('### 3.1 Issues par nature (RV7)')
    a('')
    a('| Nature | Issues | Remarque |')
    a('|---|---|---|')
    a('| commande | `OK`, `REPLAY` ; `SKIPPED`, `DEFERRED` seulement si le contrat le prévoit (`CreateCollectionAction`, `CreateManualAction`, EC-11) | `REPLAY` : rejeu d\'une clé d\'idempotence |')
    a('| handler | `PROCESSED`, `SKIPPED`, `RETRYING`, `DEAD` | ce sont les issues du reçu ; un `REPLAY` de handler est compté, non stocké (EC-02) |')
    a('| travail | `OK`, `SKIPPED` | de niveau : le passage suivant rattrape |')
    a('| travailleur | `OK`, `RETRYING`, `DEFERRED` | l\'échec suit le contrat |')
    a('| système | `OK`, `SKIPPED` | garde d\'état |')
    a('| service | celles de l\'appelant | aucune issue propre |')
    a('')
    a('### 3.2 Entrées et provisioning (RV1, RV2, RV3)')
    a('')
    a('| Entrée | Nature | Règles |')
    a('|---|---|---|')
    a('| `PUBLIC` | commande | clé d\'idempotence, audit, transaction, Domain, événement |')
    a('| `PROVISIONING_STEP` | service implémentant `organizations.ProvisioningStep` | `(organisation, étape)`, transaction du module propriétaire, événement ; **pas d\'audit direct** ; jamais appelée par l\'API |')
    a('| `INTERNAL` | système ou service | appelée par un autre cas d\'usage ou un balayage ; garde d\'état ou transaction de l\'appelant ; audit seulement s\'il est nommé (D3) |')
    a('| `REACTION` | handler | reçu `(événement, handler)` ; jamais d\'audit direct |')
    a('| `BACKGROUND` | travail ou travailleur | de niveau ou à bail |')
    a('')
    a('`CreateOrganization` est **la seule** commande dont l\'organisation n\'existe pas encore : son régime est `NEW` (T1 pose l\'identifiant généré à la réception comme tenant), puis chaque étape et `CompleteProvisioning` sont des cas d\'usage `REQUIRED` de l\'organisation créée, à l\'état `PROVISIONING`. `CompleteProvisioning` est de nature **système** (State Machines §1 : acteur `SYSTEM`) : D3 réserve l\'audit aux commandes d\'un utilisateur ou d\'une automatisation ; l\'audit de la création est porté par `CreateOrganization`, et la transition est tracée par ses événements. Cette lecture est à confirmer (**décision D-AP1**).')
    a('')
    a('**Idempotence de création (AP-14).** `CreateOrganization` consulte `(acteur, clé, route)` **avant toute génération** ; sur rejeu il restitue le résultat mémorisé (`REPLAY`) et aucun identifiant n\'est généré ; sinon il génère `organization_id`, le lie par `TenantContext.bind_new`, crée l\'organisation `PROVISIONING`, enregistre l\'idempotence et rend le résultat. Après la création, `organization_id` est la référence de toutes les opérations suivantes. La portée `ACTOR` et le régime `NEW` vont **ensemble et seulement ensemble** (A12).')
    a('')
    a('**Clé de requête (AP-14).** Le texte libre d\'idempotence du registre décrit le mécanisme du cas d\'usage ; la **clé de requête d\'API** se lit dans son opération de verrous : une commande qui insère `K` la prend. Un cas d\'usage système ou service qui partage l\'opération d\'une commande (`ApplySettlement`, `AnonymizeUser`) hérite de la clé de son appelant.')
    a('')
    a('### 3.3 Cas d\'usage composés : phases ordonnées (RV4, RV5, RV6)')
    a('')
    a('Chaque phase est **une transaction, ordonnée, non interchangeable** ; une phase `EXTERNAL` n\'est dans aucune transaction (TD31). L\'état d\'un autre module n\'est écrit que dans sa transaction (`own:`, TD58).')
    a('')
    a('| Cas d\'usage | # | Rôle | Module(s) | Appel `own:` | Écrit lui-même | Contenu |')
    a('|---|---:|---|---|---|---|---|')
    for sp in specs:
        for i, (role, mods, calls, effs, what) in enumerate(sp['phases'], 1):
            a('| %s | %d | %s | %s | %s | %s | %s |' % ('`%s.%s`' % (sp['module'], sp['name']) if i == 1 else '', i, role, ', '.join(mods), ', '.join('`%s`' % x for x in calls) or '—',
                                                        ', '.join(effs) or '—', esc(what)))
    a('')
    a("**Exécution (démontrée par le coureur, étape 12).** Chaque phase à appel `own:` est une unité de travail distincte, dans la transaction du module propriétaire ; l'orchestrateur ne possède jamais l'état d'un autre module ; un `own:` n'a aucune porte dans une unité ouverte ; une clé de requête n'est prise que dans la première unité ; une phase rejouée reçoit la même clé déterministe.")
    a('')
    a('Trois précisions :')
    a('')
    a('- **`RunExecutionStep` (AP-10).** T1 réclame (`execution → RUNNING`) ; T2 exécute l\'effet dans le module propriétaire, idempotent, et n\'est autorisée que pour le porteur de T1 ; T3 finalise seulement l\'exécution dont la réclamation correspond. Sans réclamation valide, aucun effet ne peut atteindre le propriétaire.')
    a('- **`OutboxPublisher` (RV4, TD33).** Le relais ne fait **aucune** publication dans une transaction métier : T1 réclame par bail (courte, `SKIP LOCKED`) ; chaque handler s\'exécute ensuite **dans sa propre transaction** et écrit son propre reçu ; T3 pose `published_at` quand chaque handler a pris en charge l\'événement, quel qu\'en soit le résultat. Le registre le disait « une transaction » : amendement **A4** du registre (V1.2).')
    a('- **`CreateCollectionAction` (RV5, TD58).** Composition orchestrée, pas « une transaction par module » : `collection` crée l\'action `PROPOSED` ; `approvals` enregistre la demande dans **sa** transaction (`own:approvals.RequestApproval`, via `AdvanceProposedAction`) ; `collection` transitionne selon le résultat. Un balayage (`ResumeProposedActions`) reprend un processus interrompu.')
    a('')
    a('### 3.4 Portée de transaction (F1, K1)')
    a('')
    a('| Régime d\'organisation | Portée | Contexte | Cas d\'usage |')
    a('|---|---|---|---|')
    a('| `REQUIRED`, `EVENT`, `ENUMERATOR` | `TENANT` | `CallContext` : `organization_id` obligatoire, refus fermé si absent | tous, sauf ci-dessous |')
    a('| `NEW` | `NEW` | `CreationContext` : **aucun champ d\'organisation** ; liée par `TenantContext.bind_new` après la clé d\'idempotence et la génération de l\'identifiant | `CreateOrganization` |')
    a('| `RELAY`, `NONE` | `SYSTEM` | `SystemContext` : **aucun champ d\'organisation** | `OutboxPublisher`, `PartitionManager` |')
    a('')
    a('Le coureur a démontré le besoin : ces deux cas d\'usage n\'étaient pas exprimables par `TransactionManager.atomic(ctx)` sans rendre `organization_id` optionnel, ce qui aurait permis une opération tenant-scoped sans tenant. La portée est fixée par le contrat, pas par l\'appelant : une commande `REQUIRED` ne peut pas demander `SYSTEM`.')
    a('')
    a('## 4. Application Contract V1 : les 119 cas d\'usage')
    a('')
    a('Légende : verrous `ressource:mode` (A consultatif, K clé d\'idempotence, S FOR SHARE, U FOR NO KEY UPDATE, G UPDATE gardé, I INSERT) dans l\'ordre d\'acquisition ; reprise = fondement de la règle (TD30 commandes, TD35 handlers, TD43 travaux, TD31 travailleurs). Nature : %s.' % ', '.join('%d %s' % (v, k) for k, v in sorted(kinds.items())))
    a('')
    head = ['Commande', 'Use case', 'Entrée', 'Transaction', 'Organisation', 'Idempotence', 'Verrous', 'Lectures', 'Domain', 'Inter-modules', 'Événements', 'Audit',
            'Erreurs', 'Résultat', 'Reprise', 'Atomicité']
    n_mod = 0
    for m in M.MODULES:
        if m not in per:
            continue
        n_mod += 1
        a('### 4.%d `%s`' % (n_mod, m))
        a('')
        a('| ' + ' | '.join(head) + ' |')
        a('|' + '---|' * len(head))
        for s in per[m]:
            res = s['result']
            a('| ' + ' | '.join(esc(x) for x in [
                '`%s`' % s['command'] if s['command'] else '—', '`%s`' % s['name'] + ' (' + ENTRY_LABEL[s['entry']] + ')', input_cell(s), s['transaction'], tenant_cell(s), s['idempotency'], lock_cell(s),
                ', '.join(s['reads']) or '—', ', '.join(s['domain']) or '—', ', '.join(s['cross_module']) or '—', ', '.join(s['emits']) or '—', audit_cell(s),
                ('%d codes' % len(s['errors'])) if s['errors'] else 'classes', outcome_cell(s), SHORT_RETRY[s['kind']], atomic_cell(s)]) + ' |')
        a('')
    a('## 5. Ce que ce contrat ne fige pas encore')
    a('')
    a('- **Entrées** : %d cas d\'usage sur 119 ont une charge utile figée (EC-xx) ; les autres sont « niveau C ». Elles se figeront avec le Domain, cas d\'usage par cas d\'usage, sans toucher aux registres.' % frozen_in)
    a('- **Erreurs** : seuls %d cas d\'usage nomment des codes ; les autres n\'ont que leurs classes.' % named)
    a('- **Coureur et doubles en mémoire** : le pipeline §1 est décrit ici et non encore exécuté. Prochaine étape, avant Django : le coureur sans cadre logiciel avec des doubles en mémoire des ports du noyau, pour **exécuter** P1–P12 et faire échouer une échelle de verrous non respectée.')
    a('- **Persistance** : aucune table, aucune migration ; PostgreSQL n\'est décrit que par les registres.')
    a('')
    a('### 5.1 Ce que le coureur a démontré, et la suite')
    a('')
    a('- **F1 et F2 tranchés le 2026-09-20** : portée de transaction `SYSTEM` explicite (K1, AP-15) et portée d\'idempotence typée `ORGANIZATION` / `ACTOR` (K2, AP-14), sans rendre `organization_id` optionnel ni le remplacer par une valeur nulle. Amendements du noyau K1 et K2 (Module Contracts, §6.1) et amendement Application B1 (§6).')
    a('- **Défaut de dérivation corrigé (B1).** La portée d\'idempotence se lisait dans le texte libre du registre (11 commandes) ; elle se lit dans l\'opération de verrous, qui insère `K` : **38 commandes**. Le coureur l\'a révélé en exécutant les 119 cas d\'usage.')
    a('- **Schéma (étape PostgreSQL).** `idempotency_keys` devra accueillir l\'exception `ACTOR` de TD32 (consigné en §13.2 du document d\'architecture).')
    a('')
    a('## 6. Gel et amendements')
    a('')
    if fz:
        a('L\'empreinte SHA-256 de `kernel/application.py`, `kernel/lock_registry.py` et des `specs.py` de chaque module est conservée dans `architecture_registry/application_freeze.json` ; `verify_application.py` échoue si elle diffère. Une modification n\'est possible que par une ligne du journal ci-dessous et un `application_freeze.py --write` explicite.')
        a('')
        a('| # | Date | Objet | Nature | Validé |')
        a('|---|---|---|---|---|')
        if FZ.AMENDMENTS:
            for am in FZ.AMENDMENTS:
                a('| %s | %s | %s | %s | %s |' % am)
        else:
            a('| — | — | aucun amendement depuis le gel | — | — |')
        a('')
    return '\n'.join(w) + '\n'


def main():
    text = render()
    if '--check' in sys.argv:
        with io.open(DOC, encoding='utf-8', newline='') as f:
            if f.read() != text:
                print('APPLICATION_CONTRACT_V1.md diffère du générateur')
                sys.exit(1)
        print('APPLICATION_CONTRACT_V1.md à jour')
        return
    with io.open(DOC, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    print('écrit :', DOC, '(%d lignes)' % text.count('\n'))


if __name__ == '__main__':
    main()
