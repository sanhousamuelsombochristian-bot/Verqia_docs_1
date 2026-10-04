"""Application Contract V1 : génère le contrat de CHAQUE cas d'usage (`UseCaseSpec`) depuis les quatre registres.

Un cas d'usage est décrit par 16 éléments : commande, nom, entrée, transaction, organisation, idempotence, verrous, lectures, Domain,
appels inter-modules, événements, audit, erreurs, résultat, reprise, atomicité. Rien ici n'est du comportement : c'est de la DONNÉE
vérifiée contre les registres (`verify_application.py`) et consommée par le coureur de cas d'usage (`kernel/runtime.py`).

Sortie : `verqia/kernel/application.py` (le type), `verqia/kernel/lock_registry.py` (l'échelle générée du Lock Registry),
`verqia/<module>/application/specs.py` (les cas d'usage du module).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_registry as B  # noqa: E402
import commands as K  # noqa: E402
import gen_contracts as G  # noqa: E402
import locks as L  # noqa: E402
import modules as M  # noqa: E402

HEADER = G.HEADER

KERNEL_APPLICATION = HEADER + '''"""Contrat d'un cas d'usage (Application Contract V1) : de la donnée, jamais du comportement. Le coureur (`application_runner`) la consomme."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from verqia.kernel.types import IdempotencyScope, TransactionScope


class TenantMode(str, Enum):
    REQUIRED = 'REQUIRED'          # organisation posée par l'unité de travail (TD26), refus si absente
    EVENT = 'EVENT'                # handler : organisation de l'événement
    ENUMERATOR = 'ENUMERATOR'      # travail périodique : organisations énumérées, une unité de travail chacune
    NEW = 'NEW'                    # création de l'organisation : identifiant généré APRÈS la clé d'idempotence, lié par `TenantContext.bind_new` (TD59, K3)
    RELAY = 'RELAY'                # relais d'outbox : politique nommée, aucune donnée métier (TD18)
    NONE = 'NONE'                  # tables techniques hors organisation


# Portée de transaction (K1, K3) : DÉRIVÉE du régime d'organisation, jamais choisie par l'appelant. `SYSTEM` : relais d'outbox et gestionnaire de partitions ;
# `NEW` : `CreateOrganization` seule.
SCOPE_OF_TENANT: Mapping[TenantMode, TransactionScope] = {
    TenantMode.REQUIRED: TransactionScope.TENANT,
    TenantMode.EVENT: TransactionScope.TENANT,
    TenantMode.ENUMERATOR: TransactionScope.TENANT,
    TenantMode.NEW: TransactionScope.NEW,
    TenantMode.RELAY: TransactionScope.SYSTEM,
    TenantMode.NONE: TransactionScope.SYSTEM,
}


class AuditMode(str, Enum):
    REQUIRED = 'REQUIRED'
    CONDITIONAL = 'CONDITIONAL'
    NONE = 'NONE'


class Entry(str, Enum):
    """Porte d'entrée : ce qui distingue une commande publique d'une opération interne."""
    PUBLIC = 'PUBLIC'                            # commande d'un utilisateur ou d'une automatisation
    PROVISIONING_STEP = 'PROVISIONING_STEP'      # implémentation du port `ProvisioningStep` (TD59)
    INTERNAL = 'INTERNAL'                        # cas d'usage système ou service, appelé par un autre cas d'usage ou un balayage
    REACTION = 'REACTION'                        # handler d'événements
    BACKGROUND = 'BACKGROUND'                    # travail périodique ou travailleur à bail


class PhaseRole(str, Enum):
    WRITE = 'WRITE'          # transaction propre au cas d'usage
    CLAIM = 'CLAIM'          # réclamation gardée (bail, RUNNING) ; toujours la première phase
    EFFECT = 'EFFECT'        # effet dans la transaction du module propriétaire (`own:`), idempotent
    EXTERNAL = 'EXTERNAL'    # effet extérieur : dans AUCUNE transaction
    FINALIZE = 'FINALIZE'    # enregistrement du résultat ; ne finalise qu'une réclamation correspondante


@dataclass(frozen=True)
class Phase:
    """Une phase d'un cas d'usage composé : une transaction (ou, pour EXTERNAL, aucune), ordonnée."""
    order: int
    role: PhaseRole
    modules: tuple[str, ...]
    calls: tuple[str, ...]
    effects: tuple[str, ...]
    what: str


@dataclass(frozen=True)
class UseCaseSpec:
    """Les seize éléments d'un cas d'usage."""
    module: str
    name: str
    kind: str
    command: str | None
    input: str
    transaction: str
    tenant: TenantMode
    transaction_scope: TransactionScope
    idempotency: str
    idempotency_scope: IdempotencyScope | None
    lock_operation: str | None
    lock_sequence: tuple[tuple[str, str], ...]
    reads: tuple[str, ...]
    domain: tuple[str, ...]
    cross_module: tuple[str, ...]
    emits: tuple[str, ...]
    audit: AuditMode
    audit_basis: str
    errors: tuple[str, ...]
    error_classes: tuple[str, ...]
    entry: Entry
    outcomes: tuple[str, ...]
    result: str
    retry: str
    atomic_effects: tuple[str, ...]
    phases: tuple[Phase, ...]
'''

# Erreurs propres à un cas d'usage : UNIQUEMENT celles que les contrats d'interface et les Invariants figés nomment (B3-c : tranche Facture / Paiement).
ERRORS = {
    'AllocatePayment': ('ALLOCATION_EXCEEDS_PAYMENT_AVAILABLE', 'ALLOCATION_EXCEEDS_INVOICE_OUTSTANDING', 'ALLOCATION_CUSTOMER_MISMATCH', 'ALLOCATION_CURRENCY_MISMATCH',
                        'ALLOCATION_INVOICE_NOT_PAYABLE', 'ALLOCATION_PAYMENT_REVERSED', 'ORG_NOT_ACTIVE', 'CONCURRENT_MODIFICATION'),
    'ReverseAllocation': ('REVERSAL_EXCEEDS_ORIGINAL', 'REVERSAL_REASON_REQUIRED', 'ORG_NOT_ACTIVE', 'CONCURRENT_MODIFICATION'),
    'ReversePayment': ('PAYMENT_ALREADY_REVERSED', 'PAYMENT_REVERSAL_REASON_REQUIRED', 'ORG_NOT_ACTIVE', 'CONCURRENT_MODIFICATION'),
    'CreateInvoice': ('CUSTOMER_INACTIVE', 'CUSTOMER_ARCHIVED', 'INVOICE_DATES_INVALID', 'INVOICE_NUMBER_TAKEN'),
    'IssueInvoice': ('INVALID_TRANSITION', 'INVOICE_EMPTY', 'INVOICE_TOTAL_MUST_BE_POSITIVE', 'CUSTOMER_INACTIVE', 'CUSTOMER_ARCHIVED', 'INVOICE_DATES_INVALID', 'ORG_NOT_ACTIVE'),
    'CancelInvoice': ('INVALID_TRANSITION',), 'VoidInvoice': ('INVALID_TRANSITION', 'INVOICE_HAS_PAYMENTS', 'INVOICE_HAS_OPEN_DISPUTE'),
    'OpenInvoiceDispute': ('DISPUTE_INVOICE_NOT_DISPUTABLE', 'DISPUTE_ALREADY_OPEN', 'DISPUTE_REASON_REQUIRED', 'DISPUTE_AMOUNT_EXCEEDS_TOTAL'),
    'ResolveInvoiceDispute': ('INVALID_TRANSITION',),
    'CreatePayment': ('CUSTOMER_ARCHIVED', 'PAYMENT_AMOUNT_INVALID', 'PAYMENT_CURRENCY_MISMATCH', 'PAYMENT_DATE_IN_FUTURE', 'PAYMENT_DUPLICATE_REFERENCE'),
    'NormalizeImportBatch': ('IMPORT_NORMALIZATION_FAILED', 'IMPORT_BATCH_NOT_READY'),
    'ReleaseImportTranche': ('IMPORT_BATCH_NOT_READY',),
    'AuthorizeOverride': ('OVERRIDE_NOT_ALLOWED', 'OVERRIDE_ROLE_INSUFFICIENT', 'OVERRIDE_REASON_REQUIRED', 'OVERRIDE_ORIGIN_NOT_MANUAL'),
    'CreateCollectionAction': ('SUBJECT_NOT_FOUND', 'ACTION_LEVEL_INVALID', 'ACTION_LEVEL_BELOW_MINIMUM', 'DEDUP_REPLAY_UNAVAILABLE'),       # B11 : R12-O1, option B
    'CreateManualAction': ('SUBJECT_NOT_FOUND', 'ACTION_LEVEL_INVALID', 'ACTION_LEVEL_BELOW_MINIMUM', 'OVERRIDE_NOT_ALLOWED', 'OVERRIDE_ROLE_INSUFFICIENT',
                           'OVERRIDE_REASON_REQUIRED', 'OVERRIDE_ORIGIN_NOT_MANUAL', 'DEDUP_REPLAY_UNAVAILABLE'),                # B11
    'ExecuteDueAction': ('TEMPLATE_UNAVAILABLE',),
    'RunExecutionStep': ('EXECUTION_RATE_LIMITED',),
    'ActivateAutomation': ('AUTOMATION_PRECONDITIONS_NOT_MET', 'ENROLLMENT_PREVIEW_STALE', 'AUTOMATION_SET_LOOP_DETECTED', 'INSUFFICIENT_ROLE'),
    'PauseAutomation': ('INSUFFICIENT_ROLE',), 'RetryExecution': ('INSUFFICIENT_ROLE',),
    'DecideApproval': ('APPROVER_NOT_ELIGIBLE', 'APPROVAL_ALREADY_DECIDED', 'APPROVAL_EXPIRED', 'SELF_APPROVAL_FORBIDDEN'),
    'RecomputeRisk': ('RISK_MODEL_UNKNOWN', 'CONCURRENT_MODIFICATION'), 'RecomputePriority': ('PRIORITY_MODEL_UNKNOWN', 'CONCURRENT_MODIFICATION'),
    'RunCashflow': ('CASHFLOW_MODEL_UNKNOWN', 'CASHFLOW_RUN_CONFLICT'),
    'EmitEvent': ('EVENT_SCHEMA_INVALID', 'EVENT_PAYLOAD_NOT_WHITELISTED', 'CAUSATION_DEPTH_EXCEEDED'),
}
RESULTS = {
    'AllocatePayment': 'identifiants des allocations créées, résumé du paiement et des factures touchées (EC-05)',
    'ReverseAllocation': 'identifiants des allocations créées, résumé du paiement et des factures touchées (EC-05)',
    'ReversePayment': 'identifiants des allocations créées, résumé du paiement et des factures touchées (EC-05)',
    'CreateCollectionAction': 'PROPOSED / SCHEDULED / PENDING_APPROVAL / SUPPRESSED, ou SKIPPED / DEFERRED, avec `decision_snapshot` (EC-11)',
    'CreateManualAction': 'idem, avec audit (EC-11)', 'AuthorizeOverride': 'OverrideGrant, ou refus (EC-10)',
    'RequestApproval': 'approbation PENDING (EC-13)', 'ExecuteDueAction': 'EXECUTING, SUPPRESSED ou DEFERRED après revalidation complète (EC-11, X3)',
}
# Audit : D3 (Data Contract §12.4) : commandes d'un utilisateur ou d'une automatisation, configuration et droits, holds, approbations, actions sensibles.
AUDIT_SENSITIVE = {'AnonymizeCustomer', 'AnonymizeUser', 'AnonymizeAuditLogs', 'AuthorizeOverride', 'ReplayDeadEvent'}
AUDIT_CONDITIONAL = {'CreateCollectionAction': "seulement si l'action est manuelle ou porte un override (Collection §4, D3)",
                     'ExecuteDueAction': "à chaque vérification d'un grant d'override à l'exécution (V1.2, G8)"}
TENANT_SPECIAL = {('events', 'OutboxPublisher'): 'RELAY', ('platform', 'PartitionManager'): 'NONE', ('organizations', 'CreateOrganization'): 'NEW'}


# Issues par nature (le contrat, pas un état global du système) : `REPLAY` n'existe que pour une commande à clé d'idempotence ;
# les issues d'un handler sont celles de son reçu (`REPLAY` d'un handler est compté, non stocké : EC-02).
OUTCOMES = {'command': ('OK', 'REPLAY'), 'handler': ('PROCESSED', 'SKIPPED', 'RETRYING', 'DEAD'), 'job': ('OK', 'SKIPPED'),
            'worker': ('OK', 'RETRYING', 'DEFERRED'), 'system': ('OK', 'SKIPPED'), 'service': ()}
OUTCOME_EXTRAS = {'CreateCollectionAction': ('SKIPPED', 'DEFERRED'), 'CreateManualAction': ('SKIPPED', 'DEFERRED'),   # EC-11 : décision d'action
                  # B10 (DV5-2 bis) : EC §5, « Transition d'état | garde d'état en base | SKIPPED » — rejouer la MÊME transition
                  'CancelCollectionAction': ('SKIPPED',), 'CompleteTask': ('SKIPPED',), 'ReleaseHold': ('SKIPPED',)}

# Cas d'usage composés (liste fermée et nominative, TD58) : phases ordonnées, une transaction chacune.
# (rôle, modules, appels `own:` sans préfixe, écritures propres au cas d'usage dans cette phase, description)
STEP_MODULES = sorted({c.module for c in K.COMMANDS if 'organizations.ProvisioningStep' in c.implements}, key=list(M.MODULES).index)
_PROPOSE = (('WRITE', ('collection',), (), ('collection.action_status', 'événements', 'audit', "clé d'idempotence"), "l'action est créée PROPOSED (transaction de collection)"),
            ('EFFECT', ('collection',), ('collection.AdvanceProposedAction',), (),
             "composition orchestrée (TD58) : approbation demandée dans la transaction d'approvals, puis transition dans celle de collection"))
PHASES = {
    ('organizations', 'CreateOrganization'): (
        ('WRITE', ('organizations',), (), ('organizations.record', 'organizations.settings', 'organizations.status', 'audit', "clé d'idempotence"),
         "organisation et réglages, état PROVISIONING ; aucune commande métier n'y est acceptée (TD59)"),
        ('EFFECT', tuple(STEP_MODULES), ('organizations.ProvisioningStep',), (),
         'une transaction par étape, dans son module propriétaire, idempotente par (organisation, étape)'),
        ('FINALIZE', ('organizations',), ('organizations.CompleteProvisioning',), (),
         'PROVISIONING → ACTIVE et ORGANIZATION_CREATED, quand toutes les étapes sont faites')),
    ('collection', 'CreateCollectionAction'): _PROPOSE,
    ('collection', 'CreateManualAction'): _PROPOSE,
    ('collection', 'AdvanceProposedAction'): (
        ('EFFECT', ('approvals',), ('approvals.RequestApproval',), (), "demande d'approbation dans la transaction d'approvals"),
        ('FINALIZE', ('collection',), (), ('collection.action_status', 'événements'),
         'transition PROPOSED → SCHEDULED, PENDING_APPROVAL ou SUPPRESSED, selon le résultat')),
    ('collection', 'ExecuteDueAction'): (
        ('CLAIM', ('collection',), (), ('collection.action_status', 'collection.attempts', 'audit'), 'claim gardé et revalidation complète (audit des grants vérifiés)'),
        ('EFFECT', ('notifications',), ('notifications.CreateNotification',), (), 'notification créée dans la transaction de notifications'),
        ('EXTERNAL', ('notifications',), (), (), 'envoi : hors de toute transaction (TD31)'),
        ('FINALIZE', ('collection',), (), ('événements',), 'enregistrement du résultat')),
    ('automation', 'RunExecutionStep'): (
        ('CLAIM', ('automation',), (), ('automation.execution',),
         "T1 : execution → RUNNING ; seul le porteur de la réclamation peut atteindre le propriétaire de l'effet"),
        ('EFFECT', ('collection', 'notifications', 'approvals'),
         ('collection.CreateCollectionAction', 'notifications.CreateNotification', 'approvals.RequestApproval'), (),
         "T2 : effet dans la transaction du module propriétaire, idempotent"),
        ('FINALIZE', ('automation',), (), ('automation.execution', 'événements'),
         "T3 : résultat ; ne finalise que l'exécution dont la réclamation correspond")),
    ('events', 'OutboxPublisher'): (
        ('CLAIM', ('events',), (), ('events.publication',), 'bail court (available_at, publish_attempts), SKIP LOCKED'),
        ('EFFECT', ('*',), (), ('events.receipts',),
         'chaque handler abonné dans sa propre transaction, son reçu écrit par lui ; jamais de verrou tenu pendant un handler'),
        ('FINALIZE', ('events',), (), ('events.publication',),
         'published_at quand chaque handler a pris en charge, quel que soit le résultat (TD33)')),
    ('organizations', 'ResumeProvisioning'): (
        ('EFFECT', tuple(STEP_MODULES), ('organizations.ProvisioningStep',), (), 'reprise étape par étape, chacune dans sa transaction'),
        ('FINALIZE', ('organizations',), ('organizations.CompleteProvisioning',), (), 'PROVISIONING → ACTIVE')),
    ('collection', 'ResumeProposedActions'): (
        ('EFFECT', ('collection',), ('collection.AdvanceProposedAction',), (), 'un balayage relance chaque action PROPOSED interrompue'),),
    ('collection', 'ScanReconciliationReviews'): (
        ('EFFECT', ('notifications',), ('notifications.CreateNotification',), (), 'notification dans la transaction de notifications'),),
    ('jobs', 'ImportReleaser'): (
        ('EFFECT', ('automation',), ('automation.ReleaseImportTranche',), (), "tranche libérée dans la transaction d'automation"),
        ('EFFECT', ('imports',), ('imports.CompleteImportRelease',), (), "lot marqué RELEASED dans la transaction d'imports")),
    ('jobs', 'ReconciliationWindowScan'): (
        ('EFFECT', ('collection',), ('collection.ScanReconciliationReviews',), (), 'revues de rapprochement, transaction de collection'),
        ('EFFECT', ('automation',), ('automation.ResumeReconciliationPaused',), (), "reprise des exécutions en pause, transaction d'automation")),
}


# Exception nominative du contrat d'idempotence (AP-14) : la portée est celle de l'ACTEUR avant que l'organisation existe.
ACTOR_SCOPED = {('organizations', 'CreateOrganization')}


def has_request_key(c):
    """Une commande prend une clé de requête d'API (TD32) si son opération de verrous insère `K` : le texte libre d'idempotence du registre n'en fait pas foi."""
    return c.kind == 'command' and bool(c.lock) and any(mode == 'K' for _, mode in L.op_sequence(c.lock))


def scope_for(c):
    if not has_request_key(c):
        return None
    return 'ACTOR' if (c.module, c.name) in ACTOR_SCOPED else 'ORGANIZATION'


SYSTEM_TENANTS = {'RELAY', 'NONE'}


def entry_for(c):
    if 'organizations.ProvisioningStep' in c.implements:
        return 'PROVISIONING_STEP'
    return {'command': 'PUBLIC', 'handler': 'REACTION', 'job': 'BACKGROUND', 'worker': 'BACKGROUND', 'system': 'INTERNAL', 'service': 'INTERNAL'}[c.kind]


def spec_for(c):
    payload = G.PAYLOADS.get((c.module, c.name))
    if c.kind == 'handler':
        inp = 'événements : ' + ', '.join(c.subscribes)
        cmd = None
    elif payload:
        inp = 'charge utile figée (%s) : %s' % (payload[0], ', '.join(f[0] for f in payload[1]))
        cmd = c.name
    else:
        inp = 'structurelle (niveau C)'
        cmd = c.name
    tenant = TENANT_SPECIAL.get((c.module, c.name))
    if tenant is None:
        tenant = 'EVENT' if c.kind == 'handler' else ('ENUMERATOR' if c.kind == 'job' else 'REQUIRED')
    seq = tuple(L.op_sequence(c.lock)) if c.lock else ()
    reads = []
    for t in c.calls:
        r = B.resolve_call(c, t)
        if r and r[0] == 'query':
            reads.append('%s.%s' % (r[1], r[2]))
    cross = []
    for t in c.calls:
        r = B.resolve_call(c, t)
        if r and r[0] != 'query' and (r[1] != c.module or r[0] == 'port'):
            cross.append(t)
    cross += ['implémente:' + p for p in c.implements]
    if c.name in AUDIT_CONDITIONAL:
        audit, basis = 'CONDITIONAL', AUDIT_CONDITIONAL[c.name]
    elif c.kind == 'command' or c.name in AUDIT_SENSITIVE:
        audit, basis = 'REQUIRED', "D3 : commande d'un utilisateur ou action sensible" if c.name not in AUDIT_SENSITIVE else 'D3 : action sensible'
    else:
        audit, basis = 'NONE', 'D3 : réaction, transition temporelle ou service : historique et événements, sans doublon d\'audit'
    errs = ERRORS.get(c.name, ())
    if c.kind == 'handler':
        classes = ('TRANSIENT', 'INTERNAL')
    elif c.kind == 'command':
        classes = ('VALIDATION', 'NOT_FOUND', 'FORBIDDEN', 'CONFLICT', 'BUSINESS_RULE', 'TRANSIENT')
    else:
        classes = ('NOT_FOUND', 'CONFLICT', 'BUSINESS_RULE', 'TRANSIENT')
    result = RESULTS.get(c.name) or {
        'handler': 'PROCESSED, SKIPPED, RETRYING ou DEAD (reçu) ; REPLAY compté, non stocké (EC-02)', 'job': 'OK ou SKIPPED par organisation ; le prochain passage rattrape',
        'worker': "OK, RETRYING ou DEFERRED ; l'échec suit le contrat", 'service': 'suit l\'appelant', 'system': 'OK ou SKIPPED (garde d\'état)',
        'command': 'OK ou REPLAY, identifiants créés (niveau C)'}[c.kind]
    retry = {
        'command': 'TD30 : rejeu borné (3) sur 40001 / 40P01, avant tout effet externe ; sinon erreur retryable pour le client (clé d\'idempotence)',
        'handler': 'reçu RETRYING : 10 s, 1 min, 5 min, 30 min, 2 h, puis DEAD (TD35)',
        'job': 'de niveau : le prochain passage rattrape (TD43) ; le résultat ne dépend pas de l\'heure (W6)',
        'worker': 'bail (RUNNING / EXECUTING) repris par le Reaper ; livraison au moins une fois (TD31)',
        'service': 'suit la transaction et la reprise de l\'appelant', 'system': 'garde d\'état ; suit la reprise du processus (TD58)'}[c.kind]
    eff = list(c.writes)
    if c.emits:
        eff.append('événements')
    if audit == 'REQUIRED':
        eff.append('audit')
    if has_request_key(c):
        eff.append('clé d\'idempotence')
    if c.kind == 'handler':
        eff.append('reçu')
    return dict(module=c.module, name=c.name, kind=c.kind, command=cmd, input=inp, transaction=c.txn, tenant=tenant, idempotency=c.idem or '—',
                lock_operation=c.lock, lock_sequence=seq, reads=tuple(sorted(set(reads))), domain=tuple(c.writes), cross_module=tuple(cross),
                emits=tuple(c.emits), audit=audit, audit_basis=basis, errors=tuple(errs), error_classes=classes, result=result, retry=retry,
                atomic_effects=tuple(eff), entry=entry_for(c), outcomes=tuple(OUTCOMES[c.kind]) + tuple(OUTCOME_EXTRAS.get(c.name, ())),
                phases=tuple(PHASES.get((c.module, c.name), ())), idempotency_scope=scope_for(c),
                transaction_scope='SYSTEM' if tenant in SYSTEM_TENANTS else ('NEW' if tenant == 'NEW' else 'TENANT'))


def gen_specs(module):
    cs = [c for c in K.COMMANDS if c.module == module]
    lines = [HEADER + '"""Cas d\'usage de `%s` (Application Contract V1) : un `UseCaseSpec` par entrée du registre. Donnée seulement."""' % module,
             'from __future__ import annotations', '', 'from verqia.kernel.application import AuditMode, Entry, Phase, PhaseRole, TenantMode, UseCaseSpec', 'from verqia.kernel.types import IdempotencyScope, TransactionScope', '', '',
             'USE_CASES: tuple[UseCaseSpec, ...] = (']
    for c in cs:
        s = spec_for(c)
        lines.append('    UseCaseSpec(')
        for k in ('module', 'name', 'kind', 'command', 'input', 'transaction'):
            lines.append('        %s=%r,' % (k, s[k]))
        lines.append('        tenant=TenantMode.%s,' % s['tenant'])
        lines.append('        transaction_scope=TransactionScope.%s,' % s['transaction_scope'])
        lines.append('        idempotency=%r,' % s['idempotency'])
        lines.append('        idempotency_scope=%s,' % ('IdempotencyScope.%s' % s['idempotency_scope'] if s['idempotency_scope'] else 'None'))
        for k in ('lock_operation', 'lock_sequence', 'reads', 'domain', 'cross_module', 'emits'):
            lines.append('        %s=%r,' % (k, s[k]))
        lines.append('        audit=AuditMode.%s,' % s['audit'])
        for k in ('audit_basis', 'errors', 'error_classes'):
            lines.append('        %s=%r,' % (k, s[k]))
        lines.append('        entry=Entry.%s,' % s['entry'])
        for k in ('outcomes', 'result', 'retry', 'atomic_effects'):
            lines.append('        %s=%r,' % (k, s[k]))
        if s['phases']:
            lines.append('        phases=(')
            for i, (role, mods, calls, effs, what) in enumerate(s['phases'], 1):
                lines.append('            Phase(order=%d, role=PhaseRole.%s, modules=%r, calls=%r, effects=%r, what=%r),' % (i, role, mods, calls, effs, what))
            lines.append('        ),')
        else:
            lines.append('        phases=(),')
        lines.append('    ),')
    lines.append(')')
    return '\n'.join(lines) + '\n'


def gen_lock_registry():
    canon, cycle = L.canonical()
    assert cycle is None
    lines = [HEADER + '"""Échelle des verrous GÉNÉRÉE depuis le Lock Registry (TD27) : jamais écrite à la main. Rang croissant obligatoire."""',
             'from __future__ import annotations', '', 'from typing import Mapping', '',
             'LADDER: tuple[str, ...] = %r' % (tuple(canon),), '',
             'RANK: Mapping[str, int] = {']
    for i, r in enumerate(canon):
        lines.append("    %r: %d," % (r, (i + 1) * 10))
    lines += ['}', '', 'OPERATIONS: Mapping[str, tuple[tuple[str, str], ...]] = {']
    for name in L.OPERATIONS:
        lines.append('    %r: %r,' % (name, tuple(L.op_sequence(name))))
    lines.append('}')
    return '\n'.join(lines) + '\n'


def add_files(files):
    files['verqia/kernel/application.py'] = KERNEL_APPLICATION
    files['verqia/kernel/lock_registry.py'] = gen_lock_registry()
    for m in M.MODULES:
        if m in ('kernel', 'config'):
            continue
        if not [c for c in K.COMMANDS if c.module == m]:
            continue
        files['verqia/%s/application/__init__.py' % m] = HEADER + '"""Application de `%s` : cas d\'usage. Pour l\'instant, seulement leur contrat (`specs.py`)."""\n' % m
        files['verqia/%s/application/specs.py' % m] = gen_specs(m)
    return files
