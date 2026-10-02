# -*- coding: utf-8 -*-
"""Construit GLOBAL_TEST_MATRIX_V1.md et vérifie la couverture de l'univers de traçabilité.

    python build_matrix.py            # écrit le document, affiche le rapport
    python build_matrix.py --check    # code de sortie 1 si un élément de l'univers n'est couvert par aucun test (porte CI)
"""
import io
import os
import re
import sys
from collections import defaultdict

import universe
import matrix_rows

OUT = os.path.join(universe.DOCS, 'GLOBAL_TEST_MATRIX_V1.md')

# Éléments de l'univers qui ne sont pas des comportements testables : on les justifie au lieu de les ignorer.
EXEMPT = {
    'ENG:P5': 'décision d’ordre des passes de conception (Risk / Priority / Cashflow avant la matrice) : non testable',
}

CHECKERS = [
    ('G01', 'Isolation du tenant', 'aucune clé étrangère ni requête ne franchit une organisation ; RLS active ; aucune ligne d’une organisation dans le résultat d’un rôle scopé à une autre', 'CON:T14 INV:C2'),
    ('G02', 'Conservation de l’argent', '`paid_minor` = Σ allocations (par facture) ; `allocated_minor` = Σ allocations (par paiement) ; `outstanding_minor` = total − payé ; 0 ≤ Σ ≤ bornes (T1 à T6, T10)', ''),
    ('G03', 'Cohérence des états dérivés', 'règlement et statut de paiement égaux à la fonction de leurs montants ; `settled_on` ⇔ `PAID`', ''),
    ('G04', 'Cycle de vie et historique', 'le cycle de vie est monotone ; la chaîne de `invoice_state_history` se rejoue jusqu’à l’état courant ; aucune facture hors `DRAFT` créée hors import', ''),
    ('G05', 'Validité des transitions', 'toute transition enregistrée (historiques, exécutions, actions…) appartient à la table de transitions de sa machine', ''),
    ('G06', 'Immuabilité', 'empreinte des lignes append-only et des champs figés inchangée entre deux instants', ''),
    ('G07', 'Outbox', 'chaque transaction qui change un état ou un fait a son événement ; chaque événement `TRANSITION` correspond à une ligne d’historique ; `aggregate_version` croît par agrégat ; aucun événement sans transaction', ''),
    ('G08', 'Charges utiles sans donnée personnelle', 'aucun nom, téléphone, e-mail dans `events`, `decision_snapshot`, traces', ''),
    ('G09', 'Idempotence globale', 'rejouer chaque événement et chaque commande une seconde fois ne change pas l’état (reçus, clés, garde d’état)', ''),
    ('G10', 'Déduplication', 'aucune paire d’actions ou de notifications non annulées avec la même clé ; aucun `(automation_id, trigger_key, subject_id)` en double', ''),
    ('G11', 'Concurrence d’exécution', 'au plus une exécution non terminale par (automatisation, sujet)', ''),
    ('G12', 'Causalité bornée', '`causation_depth` ≤ 20 ; aucun cycle dans les chaînes de causalité', ''),
    ('G13', 'Aucun envoi dans une transaction', 'le journal du fournisseur ne contient aucun appel émis pendant une transaction de base ouverte', ''),
    ('G14', 'Niveaux de recouvrement', 'dans un (facture, cycle) le plus haut niveau `SCHEDULED`/`EXECUTING`/`DONE` ne décroît jamais ; niveau ≥ 3 dès `OVERDUE`', ''),
    ('G15', 'Garde-fous respectés', 'aucune action automatique n’a été planifiée ou exécutée alors qu’une exception intégrée s’appliquait à cet instant (audit des décisions enregistrées)', ''),
    ('G16', 'Décisions explicables', 'chaque action porte les niveaux de risque, de priorité et de recouvrement **séparés**, la version des règles, `primary_exception` ; chaque étape porte sa revalidation', ''),
    ('G17', 'Projections = modèle de référence', 'risque, priorité et trésorerie courants égalent le résultat du modèle de référence recalculé depuis les sources ; âge des projections dans les SLO', ''),
    ('G18', 'Conservation de la trésorerie', 'pour chaque run : somme des lignes ≤ restant dû par facture et par client (CF4) ; un seul `is_current` par triplet ; promotion monotone', ''),
    ('G19', 'Audit conforme', 'chaque commande sensible a sa ligne d’audit ; les transitions temporelles du Scheduler n’en ont pas', ''),
    ('G20', 'Lots d’import', 'aucune exécution issue d’un événement de lot avant `RELEASING` ; démarrages par jour ≤ `release_max_per_day` ; toutes les exécutions existent dès la libération', ''),
    ('G21', 'Non-rétroactivité', 'aucune exécution déclenchée par un événement antérieur à `active_since` ni par un instant antérieur à l’émission de la facture', ''),
    ('G22', 'Ordre des verrous', 'le journal des verrous respecte l’ordre global (paiements → factures par identifiant → promesses → actions → exécutions → notifications)', ''),
    ('G23', 'Anonymisation sans effet financier', 'après une anonymisation, l’empreinte de toutes les colonnes financières, dates et états est inchangée', ''),
    ('G24', 'Aucune lecture d’horloge dans le Domain', 'analyse statique : aucun appel à l’heure système hors du port `Clock` ; rejeu déterministe à `as_of` égal', ''),
]

ORACLES = [
    ('O1', 'Modèle de référence exécutable', '`reference_model/verqia_models.py` : risque, priorité, trésorerie ; arithmétique entière, sans horloge. L’implémentation de production est comparée à lui.'),
    ('O2', 'Cas d’or', 'Tables d’entrées et de résultats attendus : `golden_cases.json` (22 cas chiffrés), scénarios d’or du Rule Engine (46), scénario de référence du Collection Engine, exemples des passes.'),
    ('O3', 'Table de transitions générée', 'La table des transitions du Domain (source unique) sert à générer les tests positifs et négatifs de chaque machine, et le trigger T14.'),
    ('O4', 'Vérificateurs globaux', 'Les 24 vérificateurs du §4, exécutés à la fin de chaque scénario et après chaque jour simulé. Ils portent des invariants du système entier, pas d’un module.'),
    ('O5', 'Registres de schémas et de couverture', 'Schémas versionnés des événements et de `Decision` ; registres générés des types d’événement, des codes d’erreur et des tables.'),
    ('O6', 'Implémentations naïves', 'Pour chaque calcul SQL ou concurrent : une version simple et lente en Python, comparée sur données aléatoires.'),
    ('O7', 'Relations métamorphiques et propriétés', 'Relations qui doivent tenir quelle que soit l’entrée (monotonie, conservation, stabilité du hash, hystérésis, permutation).'),
    ('O8', 'Rejeu et reconstruction', 'Rejouer le journal, ou reconstruire une projection, doit redonner exactement l’état observé.'),
    ('O9', 'Contrat ↔ schéma', 'Le Data Contract est l’oracle du schéma réel : tout écart est une erreur.'),
]

LEVELS = [
    ('L0', 'Statique / CI', 'architecture, contrat ↔ schéma, registres, portes de couverture'),
    ('L1', 'Domain pur', 'fonctions pures sans base : Rule Engine, modèles, calcul de créneau'),
    ('L2', 'PostgreSQL', 'contraintes, triggers, index, rôles, partitions'),
    ('L3', 'Cas d’usage intégré', 'un cas d’usage avec base et outbox, dans une transaction'),
    ('L4', 'Flux entre moteurs', 'événement → handler → moteur → événement'),
    ('L5', 'Scénario de bout en bout', 'horloge virtuelle, plusieurs jours simulés, tous les vérificateurs'),
    ('L6', 'Propriétés, différentiel, chaos', 'génération aléatoire, comparaison à une version naïve, injection de fautes'),
    ('L7', 'Non fonctionnel', 'performance, volumétrie, exploitation'),
]


def expand(tokens, universe_by_family):
    """Retourne (explicites, portes) : portes = familles couvertes par un jeton `FAMILLE:*`."""
    explicit, gates = set(), set()
    for t in tokens.split():
        if t.endswith(':*'):
            gates.add(t[:-2])
        else:
            explicit.add(t)
    return explicit, gates


def compress(tokens):
    by = defaultdict(list)
    for t in tokens.split():
        fam, _, rest = t.partition(':')
        by[fam].append(rest)
    out = []
    for fam, items in by.items():
        if items == ['*']:
            out.append('**%s:\\***' % fam)
        elif len(items) > 6:
            out.append('%s ×%d' % (fam, len(items)))
        else:
            out.append(' '.join('%s:%s' % (fam, i) for i in items))
    return ' · '.join(out)


def main():
    U = universe.build()
    all_tokens = {t: f for f, ts in U.items() for t in ts}
    cover_explicit = defaultdict(set)
    cover_gate = defaultdict(set)
    ids = []
    bad_ref = []
    unknown_tokens = set()
    rows_by_level = defaultdict(int)
    for sec in matrix_rows.SECTIONS:
        for (tid, lvl, what, oracle, covers) in sec['rows']:
            ids.append(tid)
            rows_by_level[lvl] += 1
            ex, gates = expand(covers, U)
            for t in ex:
                if t not in all_tokens:
                    unknown_tokens.add((tid, t))
                cover_explicit[t].add(tid)
            for fam in gates:
                if fam not in U:
                    unknown_tokens.add((tid, fam + ':*'))
                for t in U.get(fam, []):
                    cover_gate[t].add(tid)
            for g in re.findall(r'G\d\d', oracle):
                if g not in {c[0] for c in CHECKERS}:
                    bad_ref.append((tid, g))
    # couverture explicite supplémentaire : un code d'erreur ou un événement cité dans le texte d'un test
    text_cov = defaultdict(set)
    for sec in matrix_rows.SECTIONS:
        for (tid, lvl, what, oracle, covers) in sec['rows']:
            for t in re.findall(r'`([A-Z][A-Z0-9_]{3,})`', what):
                for fam in ('ERR', 'EVT'):
                    if fam + ':' + t in all_tokens:
                        text_cov[fam + ':' + t].add(tid)

    stats = {}
    uncovered = []
    for fam, toks in U.items():
        ex = [t for t in toks if t in cover_explicit or t in text_cov]
        gate_only = [t for t in toks if t not in cover_explicit and t not in text_cov and t in cover_gate]
        un = [t for t in toks if t not in cover_explicit and t not in text_cov and t not in cover_gate and t not in EXEMPT]
        stats[fam] = (len(toks), len(ex), len(gate_only), len(un))
        uncovered += un

    dup = [i for i in set(ids) if ids.count(i) > 1]

    # ------------------------------------------------------------------ rapport console
    print('%-5s %5s %9s %9s %9s' % ('FAM', 'total', 'explicite', 'porte', 'sans test'))
    tot = [0, 0, 0, 0]
    for fam, (n, e, g, u) in stats.items():
        print('%-5s %5d %9d %9d %9d' % (fam, n, e, g, u))
        for k, v in enumerate((n, e, g, u)):
            tot[k] += v
    print('%-5s %5d %9d %9d %9d' % ('TOTAL', *tot))
    print('tests :', len(ids), '| identifiants dupliqués :', dup, '| jetons inconnus :', sorted(unknown_tokens), '| vérificateurs inconnus :', bad_ref)
    print('sans test :', uncovered)

    # ------------------------------------------------------------------ document
    L = []
    w = L.append
    w('# VERQIA — Global Test Matrix V1')
    w('')
    w('Références : Data Contract V1.3, Invariants V1.2, State Machines V1, Rule Engine V1.1, Collection Engine V1.1, Automation Engine V1.1, Engine Contracts V1.1, Risk / Priority / Cashflow V1.1 et `reference_model/`.')
    w('Statut : **V1.1** — famille O complétée par Collection Engine V1.2 (proposition à valider). Ce document est **généré** par `test_matrix/build_matrix.py` à partir de `matrix_rows.py` ; la couverture est vérifiée contre un univers extrait des documents figés (`universe.py`).')
    w('')
    w('## 0. Objet')
    w('')
    w('La matrice est l’**oracle d’intégration** de VERQIA. Elle ne juxtapose pas les tests de chaque module : elle croise le Data Contract, les Invariants, les machines à états, les trois moteurs, les contrats d’interface et les projections, avec deux idées directrices :')
    w('')
    w('1. **Des vérificateurs globaux** (§4) qui portent des invariants du *système entier* et s’exécutent après **chaque** scénario, chaque jour simulé.')
    w('2. **Une traçabilité vérifiée par machine** (§7) : chaque invariant, règle, machine, contrat, erreur, événement et table est couvert par au moins un test ; un élément sans test fait échouer la porte de CI.')
    w('')
    w('Elle ne contient **aucun seuil de performance chiffré** : ils seront fixés au banc d’essai de l’architecture technique. Elle en fixe les scénarios et les mesures (§5, famille M).')
    w('')
    w('## 1. Niveaux de test')
    w('')
    w('| Niveau | Nom | Contenu | Tests |')
    w('|---|---|---|---:|')
    for code, name, desc in LEVELS:
        w('| %s | %s | %s | %d |' % (code, name, desc, rows_by_level.get(code, 0)))
    w('')
    w('## 2. Oracles')
    w('')
    w('Un test n’est utile que si l’on sait **comment** le résultat attendu est déterminé.')
    w('')
    w('| Oracle | Nom | Principe |')
    w('|---|---|---|')
    for o in ORACLES:
        w('| %s | %s | %s |' % o)
    w('')
    w('## 3. Harnais de simulation')
    w('')
    w('| Élément | Contrat |')
    w('|---|---|')
    w('| **Horloge virtuelle** | seule source de temps, injectée par le port `Clock` ; avance par jours ou par instants ; fuseaux et heure d’été simulables |')
    w('| **Identifiants déterministes** | générateur d’UUID seedé ; deux exécutions d’un scénario avec la même graine produisent les mêmes identifiants |')
    w('| **Bus d’événements instrumenté** | publie l’outbox ; peut **dupliquer, retarder, réordonner, perdre** des événements selon un plan de fautes |')
    w('| **Fournisseur d’envoi simulé** | acceptations, erreurs transitoires et permanentes, réponses perdues, rapports en double ; journalise chaque appel avec l’état des transactions |')
    w('| **Scénario en langage déclaratif** | une chronologie d’ordres (créer, émettre, payer, annuler…) et d’attentes ; rejouable |')
    w('| **Plan de fautes** | pannes de processus entre instructions, échecs de sérialisation, partitions absentes, décalages d’horloge ; chaque faute est reproductible par sa graine |')
    w('| **Instantané et différence d’état** | l’état du monde (toutes les tables métier) est capturé avant et après pour comparer deux exécutions ou deux ordres de livraison |')
    w('| **Isolation** | chaque scénario s’exécute dans sa propre organisation (et certains dans deux organisations simultanées) |')
    w('')
    w('## 4. Vérificateurs globaux (post-conditions)')
    w('')
    w('Exécutés **à la fin de chaque scénario de niveau L4 à L6** et **après chaque jour simulé** des scénarios L5. Un seul rouge invalide le scénario.')
    w('')
    w('| # | Vérificateur | Ce qu’il garantit |')
    w('|---|---|---|')
    for g in CHECKERS:
        w('| %s | %s | %s |' % (g[0], g[1], g[2]))
    w('')
    w('## 5. Tests par famille')
    w('')
    w('Colonne « Couvre » : jetons de l’univers de traçabilité (`CON` contrat, `TAB` tables, `INV` invariants et décisions, `SM`/`SMX` machines et cascades, `RULE`/`EXC`/`RE` Rule Engine, `COL` Collection, `AUT` Automation, `ENG` Engine Contracts, `JOB` jobs, `RPC` Risk/Priority/Cashflow, `GOLD` cas d’or, `ERR` erreurs, `EVT` événements, `OUT` issues, `RSN` causes). `FAM:*` = **porte de couverture** (registre vérifié en CI). La liste complète par test est en Annexe B.')
    w('')
    for sec in matrix_rows.SECTIONS:
        w('### %s' % sec['title'])
        w('')
        if sec['intro']:
            w(sec['intro'])
            w('')
        w('| ID | Niv. | Ce que le test prouve | Oracle | Couvre |')
        w('|---|---|---|---|---|')
        for (tid, lvl, what, oracle, covers) in sec['rows']:
            w('| %s | %s | %s | %s | %s |' % (tid, lvl, what.replace('|', '\\|'), oracle, compress(covers)))
        w('')
    w('## 6. Ordonnancement en intégration continue')
    w('')
    w('| Étape | Contenu | Déclencheur |')
    w('|---|---|---|')
    w('| 1. Statique | L0 : architecture, contrat ↔ schéma, registres, portes de couverture, `build_matrix.py --check` | chaque commit |')
    w('| 2. Rapide | L1 (Domain pur) et `reference_model` | chaque commit |')
    w('| 3. Base | L2 (PostgreSQL) et L3 | chaque demande de fusion |')
    w('| 4. Flux | L4 et scénarios L5 courts (un à sept jours simulés) | chaque demande de fusion |')
    w('| 5. Complet | L5 longs, L6 (propriétés, différentiel, chaos avec plusieurs graines) | chaque nuit |')
    w('| 6. Mesure | L7 (banc d’essai) | avant chaque version, et sur alerte |')
    w('')
    w('## 7. Traçabilité : couverture vérifiée')
    w('')
    w('Univers extrait des documents figés par `universe.py`. « Explicite » : le jeton figure dans un test (ou son code figure dans le texte du test) ; « porte » : couvert uniquement par une porte de couverture de niveau L0 ; « sans test » : **doit être nul**.')
    w('')
    w('| Famille | Sens | Éléments | Explicite | Porte seule | Sans test |')
    w('|---|---|---:|---:|---:|---:|')
    meaning = {'CON': 'contraintes T1–T15', 'TAB': 'tables', 'OUT': 'issues d’action', 'RSN': 'causes de pause / annulation', 'INV': 'règles communes, décisions D et N', 'SM': 'machines à états et décisions S', 'SMX': 'cascades entre machines', 'RULE': 'décisions et principes du Rule Engine', 'EXC': 'garde-fous', 'RE': 'scénarios d’or du Rule Engine', 'COL': 'décisions et principes du Collection Engine', 'AUT': 'décisions et principes de l’Automation Engine', 'ENG': 'décisions, contrats, invariants, règles de dépendance', 'JOB': 'jobs planifiés', 'ERR': 'codes d’erreur', 'RPC': 'décisions, principes, règles de conservation', 'GOLD': 'cas d’or chiffrés', 'EVT': 'types d’événement', 'RCN': 'décisions de Collection V1.2 (rapprochement)'}
    for fam, (n, e, g, u) in stats.items():
        w('| `%s` | %s | %d | %d | %d | %d |' % (fam, meaning.get(fam, ''), n, e, g, u))
    w('| **Total** | | **%d** | **%d** | **%d** | **%d** |' % tuple(tot))
    w('')
    w('**Tests définis : %d.** Identifiants dupliqués : %d. Jetons inconnus : %d.' % (len(ids), len(dup), len(unknown_tokens)))
    w('')
    w('**Éléments exemptés** (non testables, justifiés) : ' + '; '.join('`%s` — %s' % (k, v) for k, v in EXEMPT.items()) + '.')
    w('')
    w('## 8. Points ouverts')
    w('')
    w('| # | Point | Traitement |')
    w('|---|---|---|')
    w('| M1 | **Barrière de recouvrement du non-alloué (RP23)** : la famille O est écrite d’après Collection Engine V1.2 (proposition) ; elle devient définitive à la validation de V1.2 | vérifier l’alignement après validation |')
    w('| M2 | Seuils de performance chiffrés | fixés au banc d’essai de l’architecture technique |')
    w('| M3 | Implémentation du harnais (§3) | architecture technique |')
    w('| M4 | Couverture **explicite** des codes d’erreur et des événements : certains ne sont couverts que par la porte L0 | à réduire à mesure que les scénarios sont écrits ; l’Annexe C liste les éléments concernés |')
    w('')
    # Annexe B : traçabilité inverse
    w('## Annexe A · Univers')
    w('')
    for fam, toks in U.items():
        w('- `%s` (%d) : %s' % (fam, len(toks), ', '.join(t.split(':', 1)[1] for t in toks) if fam not in ('ERR', 'EVT', 'TAB') else 'voir Annexe C'))
    w('')
    w('## Annexe B · Tests par jeton (traçabilité inverse)')
    w('')
    w('| Jeton | Tests |')
    w('|---|---|')
    for fam, toks in U.items():
        if fam in ('ERR', 'EVT', 'TAB'):
            continue
        for t in toks:
            tests = sorted(cover_explicit.get(t, set()) | text_cov.get(t, set()) | cover_gate.get(t, set()))
            w('| `%s` | %s |' % (t, ', '.join(tests) if tests else '**aucun**'))
    w('')
    w('## Annexe C · Familles couvertes en partie par une porte')
    w('')
    for fam in ('ERR', 'EVT', 'TAB'):
        toks = U[fam]
        gate_only = [t for t in toks if t not in cover_explicit and t not in text_cov and t in cover_gate]
        expl = [t for t in toks if t in cover_explicit or t in text_cov]
        w('- `%s` : %d éléments, **%d** couverts explicitement, **%d** par la porte seule.' % (fam, len(toks), len(expl), len(gate_only)))
    w('')
    io.open(OUT, 'w', encoding='utf-8').write('\n'.join(L))
    print('document écrit :', OUT)
    if '--check' in sys.argv and (uncovered or unknown_tokens or dup or bad_ref):
        sys.exit(1)


if __name__ == '__main__':
    main()
