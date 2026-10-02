"""Gel d'Application Contract V1 : empreinte des fichiers générés (données), journal des amendements.

L'empreinte couvre tout ce que la couche Application expose : `kernel/application.py`, `kernel/lock_registry.py` et chaque `specs.py`.
Toute modification, même légitime, change l'empreinte : elle doit donc passer par une ligne du journal `AMENDMENTS` et un nouveau
`--write-freeze` explicite. Rien ne se gèle ni ne se dégèle par accident.

Usage : python architecture_registry/application_freeze.py [--write DATE]
"""
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FREEZE_FILE = os.path.join(HERE, 'application_freeze.json')

# Journal des amendements d'Application Contract V1 depuis son gel : (id, date, objet, nature, validé). Vide au gel.
AMENDMENTS = [
    ('B1', '2026-09-20', "`UseCaseSpec.transaction_scope` (`TENANT` / `SYSTEM`, déduit du régime d'organisation, `SCOPE_OF_TENANT`) ; `idempotency_scope` typé `IdempotencyScope | None` (type déplacé au noyau, K2) et dérivé de la présence du verrou `K` : 38 commandes, non 11 ; clé d'idempotence dans la première phase des cas d'usage composés",
     "donnée générée ; le coureur a démontré F1 (relais et partitions inexprimables), F2 (`CreateOrganization`) et l'erreur de dérivation de l'idempotence ; noyau K1 et K2", 'oui, 2026-09-20'),
    ('B2', '2026-09-20', "`CreateOrganization` : `transaction_scope` `NEW` (et non `TENANT`) ; `SCOPE_OF_TENANT[NEW]` = `NEW`",
     "donnée générée ; étape 11 du coureur : le régime `NEW` est distinct de `TENANT` et de `SYSTEM` ; noyau K3", 'oui, 2026-09-20'),
    ('B3', '2026-09-21', "**B3-a** `ApplySettlement`, `ReverseAllocation` et `ReversePayment` écrivent `invoices.lifecycle` ; `ApplySettlement` émet `INVOICE_DUE_SOON` / `_DUE` / `_OVERDUE` : recalcul immédiat du cycle de vie après annulation d'un règlement (Invariants §3.1) ; **B3-b** lectures déclarées : `OrgStatus`, `CustomerFacts`, `InvoiceFacts` pour `CreateInvoice`, `IssueInvoice`, `InvoiceLifecycleScan`, `ApplySettlement`, `CreatePayment`, `AllocatePayment`, `ReverseAllocation`, `ReversePayment` ; **B3-c** erreurs déclarées de la tranche Facture / Paiement ; catalogue : 4 codes de litige (Invariants §3.3) et `INVOICE_HAS_OPEN_DISPUTE` (T15), soit 109 codes",
     "donnée générée ; Domain V1 tranche 1 (§11, V1 à V3) : les gardes gelées exigeaient des écritures, des lectures et des codes que les registres ne déclaraient pas. Aucune règle métier nouvelle ; défaut du générateur d'Annexe A corrigé", 'oui, 2026-09-21'),
    ('B4', '2026-09-21', "**B4-a** `IssueInvoice` et `InvoiceLifecycleScan` écrivent `invoices.collection_cycle` (règle (a) des Invariants §3.1 bis : `+ 1` dans la transaction de la transition vers `OVERDUE`) ; **B4-b** `ReverseAllocation` et `ReversePayment` ne déclarent plus la lecture `invoices.InvoiceFacts` (DD23 : un reversal est autorisé quel que soit l'état de la facture)",
     "donnée générée ; Domain V1 tranche 1 (§13, DV1-1 et DV1-2) : le Domain a révélé un état écrit non déclaré et une lecture déclarée inutilisée. Aucune règle métier, aucune modification de C12, des verrous ni des machines à états", 'oui, 2026-09-21'),
    ('B5', '2026-09-22', "`RecomputeRisk` déclare ses 7 lectures (RD2.3/RD2.4) : `organizations.CalendarReader`, `organizations.OrgSettings` (nouvellement consommée par `risk`), "
     "`invoices.OpenInvoicesOfCustomer` (premier consommateur), `invoices.SettledInvoicesOfCustomer` et `invoices.EverIssuedOfCustomer` (nouvelles requêtes, module `invoices`), "
     "`payments.ReversedPaymentsOfCustomer` (nouvelle, module `payments`), `promises.BrokenPromisesOfCustomer` (nouvelle, module `promises`) ; retrait de `customers` des dépendances de `risk` "
     "(`risk-1.0` ne lit aucun fait client)",
     "donnée générée ; Risk Domain V1 (RISK_DOMAIN_V1.md, DV2-1 à DV2-5, confirmées par `reference_model/risk_ref.py`) : les lectures déclarées correspondent exactement à la signature de "
     "`evaluate_risk`, ni plus ni moins. Aucune règle métier, aucune modification de `risk-1.0`, des seuils, de l'hystérésis ni de l'agrégation validée par la référence", 'oui, 2026-09-22'),
    ('B6', '2026-09-23', "`RecomputePriority` déclare ses 5 lectures (PD2.2/PD2.3) : `organizations.OrgSettings` (`critical_amount_minor`, sans `CalendarReader` : `prio-1.0` ne calcule aucune "
     "fenêtre temporelle, PD2.3), `invoices.InvoiceFacts`, `risk.RiskLevel` (réutilisation pure de Risk, RP-E), `promises.PromiseFacts` (§ DV3-1, fournisseur potentiellement STUB), "
     "`collection.CollectionFacts` (§ DV3-2, idem) ; retrait de `customers` des dépendances de `priority` (`prio-1.0` ne lit aucun fait client, comme `risk` en B5) ; `payments` et `rules` "
     "restent déclarés (abonnement de `RequestPriorityRecalc` aux événements `payments.*` ; `priority` fait partie de `FACT_PROVIDERS`), bien qu'aucun des deux ne soit lu par "
     "`RecomputePriority` elle-même",
     "donnée générée ; Priority Domain V1 (PRIORITY_DOMAIN_V1.md, PD2.2 à PD2.4, DV3-8, confirmé par `reference_model/priority_ref.py`) : les lectures déclarées correspondent exactement à "
     "la signature de `evaluate_priority`, ni plus ni moins. Aucune règle métier, aucune modification de `prio-1.0`, du barème, de l'hystérésis ni des plafonds validés par la référence", 'oui, 2026-09-23'),
    ('B7', '2026-09-26', "`SuppressOnInvoiceDisputed` déclare la lecture `invoices.InvoiceFacts`, absente jusqu'ici (`reads=()`)",
     "donnée générée ; passe Collection Domain V1 (matrice des 19 cas d'usage, DV4-8) : la règle de suspension (`COLLECTION_ENGINE_V1.md §12`, D1 — suspendre SSI `collectible_minor = 0`) "
     "dépend d'une donnée absente du payload de l'événement `INVOICE_DISPUTED` (`dispute_id`, `disputed_amount_minor?` seulement, `INVARIANTS_V1.md §10`) ; aucune dérivation locale n'est "
     "possible (`outstanding_minor` est également absent du payload). `invoices.InvoiceFacts` était déjà un module-level dependency déclaré de `collection` (`modules.py`, `deps`/`READS`) : "
     "seul `commands.py` (le `calls=` de ce cas d'usage précis) manquait. Aucune règle métier nouvelle, aucune modification du contrat `InvoiceFacts` (`collectible_minor` y existait déjà)", 'oui, 2026-09-26'),
    ('B8', '2026-09-26', "Ajout de trois cas d'usage `collection` absents du registre malgré leur exigence par le corpus gelé (AUDIT-01) : "
     "`ClaimTask` (`assigned_to` renseigné, réclamation gardée `UPDATE … WHERE assigned_to IS NULL`), `CompleteTask` (`SCHEDULED → DONE`, "
     "acteur `USER` assigné ou membre du pool, `COLLECTION_ACTION_EXECUTED`), `RescheduleAction` (`scheduled_for` recalculé par `SlotCalculator`, "
     "garde `status ∈ {PROPOSED, SCHEDULED}`) ; conséquences techniques nécessaires, sans règle métier nouvelle : deux opérations de verrou "
     "ajoutées à `locks.py` (`ClaimTask`, `RescheduleAction`, mode `G` déjà existant sur la ressource déjà déclarée `collection_actions`) et une "
     "exception nominative et fermée à la convention de nommage `Complete*` dans `build_registry.py` (`CompleteTask` est un command `USER`, "
     "jamais un system/job, contrairement aux deux seuls précédents `CompleteProvisioning`/`CompleteImportRelease`)",
     "donnée générée ; passe Collection Domain V1 (AUDIT-01, Phase 6B) : `ENGINE_CONTRACTS_V1.md §EC-11`, `STATE_MACHINES_V1.md §7/§8`, "
     "`COLLECTION_ENGINE_V1.md §7/§8.2/§13/§14`, `INVARIANTS_V1.md §7.1` exigeaient ces trois cas d'usage, absents de `commands.py` et de "
     "`verqia/collection/application/specs.py` ; aucune trace d'un report explicite (`COLLECTION_ENGINE_V1.md §17`). Réserves documentées et "
     "non closes par cet amendement (traçabilité, pas de règle inventée) : événement éventuel de `ClaimTask`/`RescheduleAction`, audit dédié "
     "au-delà du régime générique D3 des commands, erreur de créneau cible invalide pour `RescheduleAction` (AUDIT-01.a/.b/.c/.e/.f)", 'oui, 2026-09-26'),
    ('B9', '2026-09-29', "`AdvanceProposedAction` (A2) et `RescheduleAction` (A12) déclarent les deux lectures qu'exige le `SlotCalculator` : "
     "`organizations.CalendarReader` (jours ouvrés et fériés, `org.is_business_day`) et `organizations.OrgSettings` (fenêtre de communication "
     "`comm_window_start`/`comm_window_end`, débit `extra.send_rate_per_hour`) ; `organizations.OrgSettings` ajoutée aux lectures de module de "
     "`collection` (`modules.py`), où seule `CalendarReader` figurait",
     "donnée générée ; audit V3 de `COLLECTION_DOMAIN_V1.md` (BLOCKER-2) : `COLLECTION_ENGINE_V1.md` §7 énonce les règles de placement d'un "
     "créneau (jour ouvré, fenêtre de communication, lissage du débit) ; A2 les applique à la planification initiale et A12 à la replanification "
     "(« le nouveau créneau repasse par les mêmes règles »), mais aucun des deux cas d'usage ne déclarait la moindre lecture calendaire, et "
     "`organizations.OrgSettings` n'était déclarée nulle part pour `collection`. Même espèce d'écart que B5/B6 (lecture réelle du Domain non "
     "déclarée) : `priority` avait gagné `organizations.OrgSettings` en B6 pour `critical_amount_minor`. Aucune règle métier nouvelle, aucune "
     "modification d'un document gelé, aucun changement de machine à états ni de contrat de données", 'oui, 2026-09-29'),
]


def fingerprint():
    import build_registry as B
    import gen_application as GA
    import gen_contracts as G
    B.run()
    G.generate()
    files = GA.add_files({})
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode('utf-8'))
        h.update(b'\0')
        h.update(files[rel].encode('utf-8'))
        h.update(b'\0')
    return h.hexdigest(), len(files)


def read_freeze():
    if not os.path.exists(FREEZE_FILE):
        return None
    with io.open(FREEZE_FILE, encoding='utf-8') as f:
        return json.load(f)


def check_freeze():
    """Erreurs de gel : fichier absent, empreinte différente, journal incohérent."""
    frozen = read_freeze()
    if frozen is None:
        return ['gel : `application_freeze.json` absent (Application Contract V1 non gelé)']
    sha, n = fingerprint()
    errors = []
    if frozen.get('sha256') != sha or frozen.get('files') != n:
        errors.append('gel : les fichiers Application ne correspondent plus à l\'empreinte gelée (%s…) : amendement non journalisé' % frozen.get('sha256', '')[:12])
    if frozen.get('amendments') != len(AMENDMENTS):
        errors.append('gel : le nombre d\'amendements du journal (%d) diffère de celui du gel (%s)' % (len(AMENDMENTS), frozen.get('amendments')))
    return errors


def write_freeze(date):
    sha, n = fingerprint()
    with io.open(FREEZE_FILE, 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'frozen': date, 'sha256': sha, 'files': n, 'amendments': len(AMENDMENTS)}, f, indent=2)
        f.write('\n')
    return sha, n


if __name__ == '__main__':
    if '--write' in sys.argv:
        print('gel écrit :', *write_freeze(sys.argv[sys.argv.index('--write') + 1]))
    else:
        errs = check_freeze()
        print('\n'.join(errs) or 'gel : OK')
        sys.exit(1 if errs else 0)
