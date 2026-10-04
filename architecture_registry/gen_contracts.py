"""Module Contracts V1 : génère `verqia/<module>/contracts/` depuis les quatre registres gelés.

Trois niveaux, jamais mélangés :
  A  contrats STRUCTURELS : une classe par commande, par événement, par requête, par port ; leurs métadonnées viennent du registre
  B  types CONTRACTUELS   : identifiants typés, monnaie en unité mineure, contexte d'appel, erreurs (kernel), types explicitement figés
                            par les contrats d'interface (EC-04, EC-05, EC-10, EC-11, EC-12, EC-13)
  C  COMPORTEMENT         : invariants, transitions, validations : PAS ICI (étape Application + Domain)

Aucun contrat n'importe autre chose que la bibliothèque standard et `verqia.*` (framework-free). L'organisation n'est JAMAIS un champ de
commande : elle vient du `CallContext` (K14).

Usage : python architecture_registry/gen_contracts.py [--out DIR] [--check]
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(DOCS, 'test_matrix'))

import build_registry as B  # noqa: E402
import commands as K  # noqa: E402
import modules as M  # noqa: E402
import universe  # noqa: E402

# Fichiers écrits à la main (hors contrats) : vérifiés par `verify_architecture.py`, pas par le générateur.
HANDWRITTEN = {'verqia/kernel/runtime.py', 'verqia/kernel/fakes.py',
               # Domain V1 : types de sortie du Domain pur, calendrier local (K20) et formes de niveau C des faits
               'verqia/kernel/decision.py', 'verqia/kernel/calendar.py', 'verqia/kernel/facts.py'}
DOMAIN_PATTERN = re.compile(r'^verqia/[a-z_]+/domain/[a-z_0-9]+\.py$')                 # couche Domain (TD2) : vérifiée par ses propres tests, pas par le générateur
FACTS_PATTERN = re.compile(r'^verqia/[a-z_]+/contracts/(facts|risk_facts)\.py$')       # formes de niveau C : données seulement, hygiène des contrats appliquée


def is_domain(rel):
    return bool(DOMAIN_PATTERN.match(rel))


def is_handwritten(rel):
    return rel in HANDWRITTEN or is_domain(rel) or bool(FACTS_PATTERN.match(rel))
DEFAULT_OUT = os.path.abspath(os.path.join(DOCS, '..', 'verqia-app'))
HEADER = ("# GÉNÉRÉ par architecture_registry/gen_contracts.py depuis les registres gelés (V1). Ne pas modifier à la main :\n"
          "# `verify_contracts.py` détecte toute dérive.\n")

# --------------------------------------------------------------------------------------------- utilitaires


def camel(s):
    return ''.join(w.capitalize() for w in s.split('_'))


ID_TYPES = {
    'organization_id': 'OrganizationId', 'user_id': 'UserId', 'membership_id': 'MembershipId', 'customer_id': 'CustomerId',
    'contact_id': 'ContactId', 'invoice_id': 'InvoiceId', 'dispute_id': 'DisputeId', 'payment_id': 'PaymentId',
    'allocation_id': 'AllocationId', 'promise_id': 'PromiseId', 'action_id': 'ActionId', 'hold_id': 'HoldId',
    'approval_id': 'ApprovalId', 'notification_id': 'NotificationId', 'automation_id': 'AutomationId',
    'batch_id': 'ImportBatchId', 'run_id': 'RunId',
}
KERNEL_IDS = ['OrganizationId', 'UserId', 'MembershipId', 'CustomerId', 'ContactId', 'InvoiceId', 'DisputeId', 'PaymentId', 'AllocationId',
              'PromiseId', 'ActionId', 'HoldId', 'ApprovalId', 'NotificationId', 'AutomationId', 'AutomationVersionId', 'ExecutionId',
              'ImportBatchId', 'RunId', 'EventId']
INT_FIELDS = {'level', 'score', 'rank_score', 'version_no', 'horizon_days', 'rows_total', 'collection_cycle', 'reversed_allocations_count'}
DATE_FIELDS = {'due_date', 'value_date', 'settled_on', 'promised_date'}
KIND_LABEL = {'command': 'commande', 'system': 'cas d\'usage système', 'service': 'service appelé par un autre cas d\'usage', 'job': 'travail',
              'worker': 'cas d\'usage de travailleur', 'handler': 'handler d\'événements'}


def field_type(name, optional, is_list):
    if is_list:
        base = 'tuple[str, ...]'
    elif name in ID_TYPES:
        base = ID_TYPES[name]
    elif name.endswith('_id'):
        base = 'UUID'
    elif name.endswith('_minor') or name in INT_FIELDS or name.endswith('_count'):
        base = 'int'
    elif name in DATE_FIELDS or name.endswith('_date') or name.endswith('_on'):
        base = 'date'
    elif name.endswith('_at'):
        base = 'datetime'
    else:
        base = 'str'
    return base + (' | None' if optional else '')


def load_catalogue_full():
    inv = universe.rd('INVARIANTS_V1.md')
    cat = universe.section(inv, '### 10.3', '\n---\n')
    out, category = [], None
    for line in cat.split('\n'):
        if line.startswith('**'):
            category = line.strip('* ').split('*')[0].split(' ')[0]
            continue
        if not line.startswith('| `'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        prefix = None
        # A5 (DV5-1) : une parenthèse ÉNUMÈRE les valeurs d'un champ (« `cause` (`RELEASED`, `EXPIRED`) »), elle n'ajoute pas de champs
        payload_cell = re.sub(r'\([^)]*\)', '', cells[2]) if len(cells) > 2 else ''
        payload = [(m.group(1), bool(m.group(2)), bool(m.group(3))) for m in re.finditer(r'`(\w+)(\[\])?(\?)?`', payload_cell)]
        for t in re.findall(r'`(_?[A-Z][A-Z0-9_]+)`', cells[0]):
            name = prefix + t if t.startswith('_') else t
            if not t.startswith('_'):
                prefix = t.rsplit('_', 1)[0]
            out.append({'type': name, 'category': category, 'aggregate': cells[1], 'payload': payload})
    return out


def event_module(ev, cons):
    o = B.event_owner(ev['type'])
    if o:
        return o
    subs = cons.get(ev['type'], [])
    assert len(subs) == 1, ev['type']
    return subs[0].split('.')[0]


REQUEST_AGGREGATE = {'risk': 'customer', 'priority': 'invoice', 'cashflow': 'organization'}

# --------------------------------------------------------------------------------------------- kernel (niveau B)
KERNEL_TYPES = HEADER + '''"""Types contractuels partagés (niveau B). Bibliothèque standard seulement."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NewType
from uuid import UUID

''' + '\n'.join("%s = NewType('%s', UUID)" % (n, n) for n in KERNEL_IDS) + '''

Currency = NewType('Currency', str)
"""Code ISO 4217 sur trois lettres."""
MoneyMinor = NewType('MoneyMinor', int)
"""Montant en unité mineure, entier signé ; jamais de flottant."""
CorrelationId = NewType('CorrelationId', UUID)
IdempotencyKey = NewType('IdempotencyKey', str)


class ActorType(str, Enum):
    USER = 'USER'
    SYSTEM = 'SYSTEM'
    AUTOMATION = 'AUTOMATION'


class IsolationLevel(str, Enum):
    READ_COMMITTED = 'READ_COMMITTED'
    REPEATABLE_READ = 'REPEATABLE_READ'


class TransactionScope(str, Enum):
    """Portée d'une unité de travail (amendements K1 et K3 de C10). Trois régimes distincts, jamais trois variantes d'un `organization_id` nul.
    Déterminée par le contrat Application, jamais choisie par l'appelant."""
    TENANT = 'TENANT'    # unité de travail d'une organisation : `CallContext`, organisation posée avant toute lecture (TD26)
    SYSTEM = 'SYSTEM'    # unité de travail globale, sans organisation : `SystemContext` (relais d'outbox, gestionnaire de partitions)
    NEW = 'NEW'          # unité de travail qui CRÉE l'organisation : `CreationContext` ; organisation liée par `TenantContext.bind_new` (amendement K3, TD59)


class IdempotencyScope(str, Enum):
    """Portée d'une clé d'idempotence (amendement K2 de C10) : typée, jamais un `organization_id` nul par convention."""
    ORGANIZATION = 'ORGANIZATION'    # (organisation, clé, route) : cas général (TD32)
    ACTOR = 'ACTOR'                  # (acteur, clé, route) : `CreateOrganization`, l'organisation n'existant pas encore (AP-14)


@dataclass(frozen=True)
class Actor:
    type: ActorType
    id: UserId | None = None
    role: str | None = None


@dataclass(frozen=True)
class SubjectRef:
    """Référence d'un sujet : type (`INVOICE`, `CUSTOMER`, `PAYMENT`, `PROMISE`) et identifiant."""
    subject_type: str
    subject_id: UUID


@dataclass(frozen=True)
class Command:
    """Marqueur : cas d'usage publié par un module. L'organisation vient du `CallContext`, jamais d'un champ."""


@dataclass(frozen=True)
class Query:
    """Marqueur : lecture publiée par un module (jamais utilisée par une décision comme cache, X1)."""
'''

KERNEL_CONTEXT = HEADER + '''"""Contexte d'appel (EC §0.2) : obligatoire pour tout contrat."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from verqia.kernel.types import Actor, CorrelationId, IdempotencyKey, OrganizationId


@dataclass(frozen=True)
class CallContext:
    """Organisation, acteur, chaîne de causalité, temps métier injecté (`as_of`, TD23) et clé d'idempotence."""
    organization_id: OrganizationId
    actor: Actor
    correlation_id: CorrelationId
    as_of: datetime
    causation_id: CorrelationId | None = None
    causation_depth: int = 0
    idempotency_key: IdempotencyKey | None = None


@dataclass(frozen=True)
class SystemContext:
    """Contexte d'une unité de travail `SYSTEM` (amendement K1 de C10) : il n'a AUCUN champ d'organisation. `CallContext.organization_id` reste obligatoire."""
    actor: Actor
    correlation_id: CorrelationId
    as_of: datetime
    causation_id: CorrelationId | None = None
    causation_depth: int = 0


@dataclass(frozen=True)
class CreationContext:
    """Contexte d'une unité de travail `NEW` (amendement K3 de C10) : l'organisation n'existe pas encore, le champ n'existe donc pas. Elle est
    liée par `TenantContext.bind_new`, jamais par une modification d'un contexte existant. Porte la clé d'idempotence (portée `ACTOR`, AP-14)."""
    actor: Actor
    correlation_id: CorrelationId
    as_of: datetime
    causation_id: CorrelationId | None = None
    causation_depth: int = 0
    idempotency_key: IdempotencyKey | None = None
'''

KERNEL_EVENTS = HEADER + '''"""Vocabulaire des événements (catalogue des Invariants §10) : quatre catégories, jamais confondues."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import ClassVar
from uuid import UUID

from verqia.kernel.types import CorrelationId, EventId, OrganizationId


class EventCategory(str, Enum):
    MUTATION = 'MUTATION'
    TRANSITION = 'TRANSITION'
    REQUEST = 'REQUEST'
    RESULT = 'RESULT'


@dataclass(frozen=True)
class Event:
    """Fait passé (MUTATION, TRANSITION, RESULT) ou demande adressée à un seul moteur (REQUEST). Payload sans donnée personnelle (C9)."""
    TYPE: ClassVar[str]
    CATEGORY: ClassVar[EventCategory]
    AGGREGATE: ClassVar[str]
    SCHEMA_VERSION: ClassVar[int]


@dataclass(frozen=True)
class EventEnvelope:
    """Ce que toute ligne d'outbox porte en plus du payload (Invariants §10.3)."""
    event_id: EventId
    organization_id: OrganizationId
    occurred_at: datetime
    category: EventCategory
    type: str
    correlation_id: CorrelationId
    aggregate_type: str
    aggregate_id: UUID
    payload: Event
    causation_id: EventId | None = None
    causation_depth: int = 0
    aggregate_version: int | None = None
    actor_type: str = 'SYSTEM'
    actor_id: UUID | None = None
    schema_version: int = 1
    import_batch_id: UUID | None = None


@dataclass(frozen=True)
class HandlerSpec:
    """Abonnement d'un handler : nom stable `module.Nom`, événements écoutés, effets déclarés. Un REQUEST n'a qu'un destinataire."""
    name: str
    subscribes: tuple[type[Event], ...]
    emits: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    lock: str | None = None
    single_recipient: bool = False
'''

KERNEL_PORTS = HEADER + '''"""Ports partagés (TA §8.2) : des CAPACITÉS, jamais des implémentations. Les adaptateurs (Django, PostgreSQL, Redis) viendront plus tard."""
from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from typing import Mapping, Protocol, Sequence
from uuid import UUID

from verqia.kernel.context import CallContext, CreationContext, SystemContext
from verqia.kernel.events import Event
from verqia.kernel.types import EventId, IdempotencyKey, IdempotencyScope, IsolationLevel, OrganizationId, TransactionScope


class Clock(Protocol):
    """Temps métier : `as_of` de l'unité de travail (TD23). Seule heure que voient le Domain et l'Application."""

    def as_of(self) -> datetime: ...


class IdGenerator(Protocol):
    """Identifiants UUIDv7 ; l'instant vient du `Clock`."""

    def new_id(self) -> UUID: ...


class TransactionManager(Protocol):
    """Unité de travail : pose l'organisation, l'`as_of`, l'isolation et les délais (TD25, TD26). `TENANT` exige un `CallContext` ;
    `SYSTEM` exige un `SystemContext` et interdit toute organisation ; `NEW` exige un `CreationContext` : l'organisation n'est liée qu'après `bind_new`.
    La portée vient du contrat Application, jamais de l'appelant."""

    def atomic(self, ctx: CallContext | SystemContext | CreationContext, isolation: IsolationLevel = IsolationLevel.READ_COMMITTED,
               scope: TransactionScope = TransactionScope.TENANT) -> AbstractContextManager[None]: ...


class LockManager(Protocol):
    """Verrous ordonnés ; l'opération DOIT être enregistrée au Lock Registry, sinon violation d'architecture (TD27)."""

    def lock_rows(self, operation: str, resource: str, ids: Sequence[UUID]) -> None: ...

    def lock_advisory(self, operation: str, key: str) -> None: ...


class TenantContext(Protocol):
    """Organisation courante ; refus si absente (TD17). Une fois liée, elle ne change plus pendant l'unité de travail."""

    def organization_id(self) -> OrganizationId: ...

    def bind_new(self, organization_id: OrganizationId) -> None:
        """Amendement K3. Réservé à une unité `NEW` : lie l'identifiant d'une organisation VENANT D'ÊTRE GÉNÉRÉ par `IdGenerator`, une seule fois.
        Tout autre usage (unité `TENANT` ou `SYSTEM`, identifiant non généré ou déjà connu, seconde liaison) est une violation d'architecture."""


class EventOutbox(Protocol):
    """Émettre un événement dans la transaction de l'appelant (EC-01) : jamais hors transaction."""

    def emit(self, ctx: CallContext, event: Event, aggregate_id: UUID, aggregate_version: int | None = None) -> EventId: ...


class AuditWriter(Protocol):
    """Écrire l'audit dans la transaction (D3)."""

    def write(self, ctx: CallContext, action: str, entity_type: str, entity_id: UUID, before: Mapping[str, object] | None = None,
              after: Mapping[str, object] | None = None, reason: str | None = None) -> None: ...


class IdempotencyStore(Protocol):
    """Clé insérée au début de la transaction du cas d'usage ; renvoie la réponse déjà stockée en cas de rejeu (TD32). La portée est TYPÉE :
    `(scope, scope_id, key, route)`, avec `scope_id` = organisation ou acteur selon `scope`."""

    def begin(self, scope: IdempotencyScope, scope_id: UUID, key: IdempotencyKey, route: str, request_hash: str) -> Mapping[str, object] | None: ...

    def complete(self, scope: IdempotencyScope, scope_id: UUID, key: IdempotencyKey, route: str, response_status: int,
                 response_body: Mapping[str, object]) -> None: ...


class RateLimiter(Protocol):
    """Limitation d'API et étranglement d'envoi : seuls usages de Redis en V1 (TD49)."""

    def allow(self, key: str, limit: int, window_seconds: int) -> bool: ...


class Metrics(Protocol):
    """Compteurs et histogrammes ; jamais l'organisation en étiquette (cardinalité), jamais de donnée personnelle."""

    def count(self, name: str, value: int = 1, **labels: str) -> None: ...

    def observe(self, name: str, value: float, **labels: str) -> None: ...


class Tracer(Protocol):
    """Trace rattachée à la chaîne événement / exécution / action."""

    def span(self, name: str, ctx: CallContext) -> AbstractContextManager[None]: ...


class Logger(Protocol):
    """Journal structuré avec `correlation_id` ; jamais de donnée personnelle."""

    def log(self, level: str, message: str, ctx: CallContext, **fields: object) -> None: ...
'''


def kernel_errors():
    eng = universe.rd('ENGINE_CONTRACTS_V1.md')
    ann = eng[eng.index('## Annexe A'):]
    rows = re.findall(r'^\| `([A-Z_]+)` \| (\w+) \| ([0-9/]+) \| (oui|non) \|', ann, re.M)
    rows.sort()
    lines = [HEADER + '"""Modèle d\'erreur commun (EC §0.3, §0.4) et catalogue généré depuis l\'Annexe A."""',
             'from __future__ import annotations', '',
             'from dataclasses import dataclass, field', 'from enum import Enum', 'from typing import Mapping', '', '',
             'class ErrorClass(str, Enum):']
    for c in ('VALIDATION', 'BUSINESS_RULE', 'NOT_FOUND', 'FORBIDDEN', 'CONFLICT', 'RATE_LIMITED', 'TRANSIENT', 'INTERNAL'):
        lines.append("    %s = '%s'" % (c, c))
    lines += ['', '', 'class Outcome(str, Enum):', '    """Issues d\'un appel (EC §0.3) ; une erreur n\'en est pas une : elle lève `DomainError`."""']
    for c in ('OK', 'REPLAY', 'SKIPPED', 'DEFERRED'):
        lines.append("    %s = '%s'" % (c, c))
    lines += ['', '', '@dataclass(frozen=True)', 'class ErrorSpec:', '    code: str', '    error_class: ErrorClass', '    http: str', '    retryable: bool', '', '',
              '@dataclass(eq=False)', 'class DomainError(Exception):',
              '    """Erreur de domaine : code stable, classe, indication de nouvelle tentative, détails sans donnée personnelle."""',
              '    code: str', '    error_class: ErrorClass', '    retryable: bool = False', '    details: Mapping[str, object] = field(default_factory=dict)', '', '',
              'ERROR_CATALOGUE: Mapping[str, ErrorSpec] = {']
    for code, cls, http, retry in rows:
        lines.append("    '%s': ErrorSpec('%s', ErrorClass.%s, '%s', %s)," % (code, code, cls, http, 'True' if retry == 'oui' else 'False'))
    lines.append('}')
    return '\n'.join(lines) + '\n', [r[0] for r in rows]


# --------------------------------------------------------------------------------------------- types de module (niveau B, explicitement figés)
MODULE_TYPES = {}


def exception_codes():
    rule = universe.rd('RULE_ENGINE_V1.md')
    sec = universe.section(rule, '## 3.', '### 3.1')
    return re.findall(r'^\| \d+ \| `([A-Z_]+)` \|', sec, re.M)


MODULE_TYPES['rules'] = lambda: HEADER + '''"""Types contractuels du Rule Engine : les 13 exceptions (§3), l'origine d'un appel, le grant d'override typé (§3.3, EC-10)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from verqia.kernel.types import EventId, UserId


class ExceptionCode(str, Enum):
    """Les exceptions intégrées, dans l'ordre fixe d'évaluation."""
''' + '\n'.join("    %s = '%s'" % (c, c) for c in exception_codes()) + '''


class Origin(str, Enum):
    AUTOMATIC = 'AUTOMATIC'
    MANUAL = 'MANUAL'


@dataclass(frozen=True)
class OverrideGrant:
    """Preuve d'un contournement décidé par un humain : ce n'est pas une autorité, elle est revérifiée à l'exécution (V1.2, G4)."""
    exception_code: ExceptionCode
    actor_id: UserId
    actor_role: str
    reason_code: str
    reason_text: str
    granted_at: datetime


@dataclass(frozen=True)
class TriggerEventRef:
    event_id: EventId
    type: str
    occurred_at: datetime
'''

MODULE_TYPES['payments'] = lambda: HEADER + '''"""Types contractuels des paiements (EC-05)."""
from __future__ import annotations

from dataclasses import dataclass

from verqia.kernel.types import InvoiceId, MoneyMinor


@dataclass(frozen=True)
class AllocationLine:
    invoice_id: InvoiceId
    amount_minor: MoneyMinor
'''

MODULE_TYPES['approvals'] = lambda: HEADER + '''"""Types contractuels des approbations (EC-13) : la cible est une action de recouvrement ou une exécution d'automatisation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class ApprovalTargetType(str, Enum):
    COLLECTION_ACTION = 'COLLECTION_ACTION'
    AUTOMATION_EXECUTION = 'AUTOMATION_EXECUTION'


@dataclass(frozen=True)
class ApprovalTarget:
    target_type: ApprovalTargetType
    target_id: UUID
'''

MODULE_TYPES['notifications'] = lambda: HEADER + '''"""Types contractuels de l'envoi (EC-04) : le résultat d'un envoi est une valeur, jamais une exception."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from verqia.kernel.types import NotificationId


class SendOutcome(str, Enum):
    ACCEPTED = 'ACCEPTED'
    TRANSIENT_ERROR = 'TRANSIENT_ERROR'
    PERMANENT_ERROR = 'PERMANENT_ERROR'


@dataclass(frozen=True)
class SendRequest:
    """Clé d'idempotence fournisseur = `{notification_id}:{attempt_no}`."""
    notification_id: NotificationId
    attempt_no: int
    channel: str
    recipient: str
    rendered_content: str


@dataclass(frozen=True)
class SendResult:
    outcome: SendOutcome
    provider_ref: str | None = None
'''

MODULE_TYPES['automation'] = lambda: HEADER + '''"""Types contractuels de l'automatisation (EC-12) : l'aperçu d'inscription vérifié atomiquement à l'activation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EnrollmentPreview:
    as_of: datetime
    expected_count: int
    fingerprint: str
'''

TYPE_HOME = {
    'AllocationLine': 'verqia.payments.contracts.types', 'ApprovalTarget': 'verqia.approvals.contracts.types',
    'OverrideGrant': 'verqia.rules.contracts.types', 'ExceptionCode': 'verqia.rules.contracts.types', 'Origin': 'verqia.rules.contracts.types',
    'TriggerEventRef': 'verqia.rules.contracts.types', 'SendResult': 'verqia.notifications.contracts.types',
    'SendRequest': 'verqia.notifications.contracts.types', 'EnrollmentPreview': 'verqia.automation.contracts.types',
    'SubjectRef': 'verqia.kernel.types', 'Mapping': 'typing', 'datetime': 'datetime', 'UUID': 'uuid',
}
for _k in KERNEL_IDS + ['MoneyMinor', 'Command', 'Query']:
    TYPE_HOME[_k] = 'verqia.kernel.types'

# Charges utiles EXPLICITEMENT figées par les contrats d'interface. Toute autre commande est structurelle (niveau C : plus tard).
PAYLOADS = {
    ('payments', 'AllocatePayment'): ('EC-05', [('payment_id', 'PaymentId', None), ('allocations', 'tuple[AllocationLine, ...]', None)]),
    ('payments', 'ReverseAllocation'): ('EC-05', [('allocation_id', 'AllocationId', None), ('amount_minor', 'MoneyMinor', None), ('reason', 'str', None)]),
    ('payments', 'ReversePayment'): ('EC-05', [('payment_id', 'PaymentId', None), ('reason_code', 'str', None), ('reason', 'str', None)]),
    ('imports', 'NormalizeImportBatch'): ('EC-07', [('batch_id', 'ImportBatchId', None)]),
    ('invoices', 'IssueInvoice'): ('EC-06', [('invoice_id', 'InvoiceId', None)]),
    ('invoices', 'CancelInvoice'): ('EC-06', [('invoice_id', 'InvoiceId', None), ('reason_code', 'str', None)]),
    ('invoices', 'VoidInvoice'): ('EC-06', [('invoice_id', 'InvoiceId', None), ('reason_code', 'str', None)]),
    ('approvals', 'RequestApproval'): ('EC-13', [('target', 'ApprovalTarget', None), ('kind', 'str', None), ('reason', 'str', None),
                                                  ('context', 'Mapping[str, object]', None), ('expires_at', 'datetime', None),
                                                  ('requested_from_user', 'UserId | None', 'None'), ('requested_role', 'str | None', 'None')]),
    ('approvals', 'DecideApproval'): ('EC-13', [('approval_id', 'ApprovalId', None), ('decision', 'str', None), ('comment', 'str | None', 'None')]),
    ('collection', 'CreateCollectionAction'): ('EC-11', [('subject', 'SubjectRef', None), ('type', 'str', None), ('channel', 'str', None),
                                                          ('execution_id', 'ExecutionId | None', 'None'), ('step_id', 'UUID | None', 'None')]),
    ('collection', 'CreateManualAction'): ('EC-11', [('subject', 'SubjectRef', None), ('type', 'str', None), ('level', 'int', None), ('channel', 'str', None),
                                                     ('override_grants', 'tuple[OverrideGrant, ...]', '()')]),
    ('collection', 'ExecuteDueAction'): ('EC-11', [('action_id', 'ActionId', None)]),
    ('collection', 'AuthorizeOverride'): ('EC-10', [('action_ref', 'ActionId', None), ('exception_code', 'ExceptionCode', None),
                                                    ('reason_code', 'str', None), ('reason_text', 'str', None)]),
    ('notifications', 'HandleSendResult'): ('EC-04', [('notification_id', 'NotificationId', None), ('attempt_no', 'int', None), ('result', 'SendResult', None)]),
    ('automation', 'ActivateAutomation'): ('EC-12', [('version_id', 'AutomationVersionId', None), ('enrollment_mode', 'str', None),
                                                      ('preview', 'EnrollmentPreview | None', 'None')]),
    ('automation', 'RunExecutionStep'): ('EC-12', [('execution_id', 'ExecutionId', None)]),
    ('automation', 'RetryExecution'): ('EC-12', [('execution_id', 'ExecutionId', None)]),
    ('automation', 'ReleaseImportTranche'): ('EC-12', [('batch_id', 'ImportBatchId', None)]),
    ('events', 'ReplayDeadEvent'): ('EC-02', [('event_id', 'EventId', None), ('handler_name', 'str', None)]),
}
QUERY_PAYLOADS = {
    ('rules', 'Evaluate'): ('EC-09', [('subject', 'SubjectRef', None), ('origin', 'Origin', None), ('definition_ref', 'UUID | None', 'None'),
                                      ('action_kind', 'str | None', 'None'), ('channel', 'str | None', 'None'),
                                      ('override_grants', 'tuple[OverrideGrant, ...]', '()'), ('trigger_event', 'TriggerEventRef | None', 'None')]),
}

# --------------------------------------------------------------------------------------------- ports de module (capacités)
PORT_SRC = {
    'organizations.ProvisioningStep': ('from verqia.kernel.context import CallContext\nfrom verqia.kernel.types import OrganizationId\n', '''class ProvisioningStep(Protocol):
    """Étape d'un plan de provisioning (TD59) : implémentée par le module qui la possède (`identity`, `billing`, `automation`), idempotente par `(organisation, étape)`."""

    def name(self) -> str: ...

    def provision(self, ctx: CallContext, organization_id: OrganizationId) -> None: ...

    def is_done(self, ctx: CallContext, organization_id: OrganizationId) -> bool: ...
'''),
    'rules.FactProvider': ('from verqia.kernel.context import CallContext\nfrom verqia.kernel.types import SubjectRef\n', '''class FactProvider(Protocol):
    """Fournisseur de faits pour une famille (TD12) : déclaré par `rules`, implémenté par le module propriétaire des données."""

    def family(self) -> str: ...

    def load(self, ctx: CallContext, subject: SubjectRef, names: Sequence[str]) -> Mapping[str, object]: ...
'''),
    'approvals.ApprovalTargetReader': ('from verqia.approvals.contracts.types import ApprovalTarget\nfrom verqia.kernel.context import CallContext\n', '''class ApprovalTargetReader(Protocol):
    """Interroge la cible d'une approbation (TD58) : implémenté par `collection` et `automation`."""

    def is_resolved(self, ctx: CallContext, target: ApprovalTarget) -> bool: ...
'''),
    'notifications.NotificationSender': ('from verqia.notifications.contracts.types import SendRequest, SendResult\n', '''class NotificationSender(Protocol):
    """Remise à un fournisseur externe : jamais dans une transaction (X13), garantie au moins une fois (EC-04)."""

    def send(self, request: SendRequest) -> SendResult: ...
'''),
    'jobs.JobRunner': ('from verqia.kernel.context import CallContext\n', '''class JobRunner(Protocol):
    """Exécute un travail ; le planificateur calcule l'échéance, le coureur exécute, le moteur décide (TD41)."""

    def run(self, job_name: str, ctx: CallContext) -> None: ...
'''),
}
PORT_SRC_STD = {'organizations.ProvisioningStep': False, 'rules.FactProvider': True, 'approvals.ApprovalTargetReader': False,
                'notifications.NotificationSender': False, 'jobs.JobRunner': False}

# --------------------------------------------------------------------------------------------- génération


def imports_for(type_strings, own_module, extra=()):
    names = set()
    for t in type_strings:
        names |= set(re.findall(r'[A-Za-z_][A-Za-z_0-9]*', t))
    groups = {}
    for n in sorted(names):
        home = TYPE_HOME.get(n)
        if home:
            groups.setdefault(home, []).append(n)
    std = [(h, ns) for h, ns in groups.items() if not h.startswith('verqia')]
    ver = [(h, ns) for h, ns in groups.items() if h.startswith('verqia')]
    lines = []
    for h, ns in sorted(std):
        lines.append('from %s import %s' % (h, ', '.join(ns)))
    if lines:
        lines.append('')
    for h, ns in sorted(ver):
        lines.append('from %s import %s' % (h, ', '.join(ns)))
    return lines


def gen_commands(module, cmds):
    types_used = []
    body = []
    for c in cmds:
        payload = PAYLOADS.get((module, c.name))
        fields = payload[1] if payload else []
        types_used += [f[1] for f in fields]
        doc = '%s.%s : %s. Source : %s.' % (module, c.name, KIND_LABEL[c.kind], c.src)
        if payload:
            doc += ' Charge utile figée par %s.' % payload[0]
        else:
            doc += ' Charge utile : niveau C (avec le cas d\'usage).'
        body += ['@dataclass(frozen=True)', 'class %s(Command):' % c.name, '    """%s"""' % doc, '']
        for n, t, d in fields:
            body.append('    %s: %s%s' % (n, t, (' = ' + d) if d else ''))
        if fields:
            body.append('')
        body += ["    MODULE: ClassVar[str] = '%s'" % module, "    KIND: ClassVar[str] = '%s'" % c.kind, "    SOURCE: ClassVar[str] = %r" % c.src,
                 "    LOCK: ClassVar[str | None] = %r" % (c.lock,), "    WRITES: ClassVar[tuple[str, ...]] = %r" % (tuple(c.writes),),
                 "    EMITS: ClassVar[tuple[str, ...]] = %r" % (tuple(c.emits),), "    CALLS: ClassVar[tuple[str, ...]] = %r" % (tuple(c.calls),),
                 "    IMPLEMENTS: ClassVar[tuple[str, ...]] = %r" % (tuple(c.implements),), "    IDEMPOTENCY: ClassVar[str] = %r" % (c.idem,),
                 "    TRANSACTION: ClassVar[str] = %r" % (c.txn,), "    C12: ClassVar[bool] = %r" % (c.c12,), '', '']
    head = [HEADER + '"""Commandes publiées par `%s` (niveau A). L\'organisation vient du `CallContext`, jamais d\'un champ."""' % module,
            'from __future__ import annotations', '', 'from dataclasses import dataclass', 'from typing import ClassVar', '']
    head += imports_for(types_used + ['Command'], module) + ['', '', '']
    text = '\n'.join(head) + '\n'.join(body)
    # `Command` peut déjà être importé par imports_for (jamais : absent de TYPE_HOME) ; fusion des imports kernel identiques
    return text.rstrip('\n') + '\n'


def gen_queries(module, consumers):
    types_used, body = [], []
    for q in M.MODULES[module]['queries']:
        payload = QUERY_PAYLOADS.get((module, q))
        fields = payload[1] if payload else []
        types_used += [f[1] for f in fields]
        doc = '%s.%s : lecture publiée (niveau A).' % (module, q)
        doc += (' Charge utile figée par %s.' % payload[0]) if payload else ' Forme du résultat : niveau C.'
        body += ['@dataclass(frozen=True)', 'class %s(Query):' % q, '    """%s"""' % doc, '']
        for n, t, d in fields:
            body.append('    %s: %s%s' % (n, t, (' = ' + d) if d else ''))
        if fields:
            body.append('')
        body += ["    MODULE: ClassVar[str] = '%s'" % module, "    CONSUMERS: ClassVar[tuple[str, ...]] = %r" % (tuple(sorted(consumers.get('%s.%s' % (module, q), ()))),), '', '']
    head = [HEADER + '"""Lectures publiées par `%s` (niveau A). Les autres modules ne lisent que par elles (DR2)."""' % module,
            'from __future__ import annotations', '', 'from dataclasses import dataclass', 'from typing import ClassVar', '']
    head += imports_for(types_used + ['Query'], module) + ['', '', '']
    return ('\n'.join(head) + '\n'.join(body)).rstrip('\n') + '\n'


def gen_events(module, events, handlers, event_home):
    types_used, cls_lines, imports_ev = [], [], {}
    for ev in events:
        fields = ev['payload']
        req = [f for f in fields if not f[2]]
        opt = [f for f in fields if f[2]]
        cname = camel(ev['type'])
        agg = ev['aggregate']
        if ev['category'] == 'REQUEST':
            agg = REQUEST_AGGREGATE[module]
        cls_lines += ['@dataclass(frozen=True)', 'class %s(Event):' % cname,
                      '    """%s : %s."""' % (ev['type'], {'MUTATION': 'fait : création ou mutation', 'TRANSITION': 'fait : changement d\'état',
                                                            'REQUEST': 'demande adressée à un seul moteur', 'RESULT': 'résultat d\'un calcul'}[ev['category']]), '']
        for n, is_list, is_opt in req:
            t = field_type(n, False, is_list)
            types_used.append(t)
            cls_lines.append('    %s: %s' % (n, t))
        for n, is_list, is_opt in opt:
            t = field_type(n, True, is_list)
            types_used.append(t)
            cls_lines.append('    %s: %s = None' % (n, t))
        if fields:
            cls_lines.append('')
        cls_lines += ["    TYPE: ClassVar[str] = '%s'" % ev['type'], "    CATEGORY: ClassVar[EventCategory] = EventCategory.%s" % ev['category'],
                      "    AGGREGATE: ClassVar[str] = '%s'" % agg, '    SCHEMA_VERSION: ClassVar[int] = 1', '', '']
    handler_lines = []
    for h in handlers:
        subs = []
        for e in h.subscribes:
            cname = camel(e)
            home = event_home[e]
            if home != module:
                imports_ev.setdefault(home, set()).add(cname)
            subs.append(cname)
        single = any(B.EVT[e][0] == 'REQUEST' for e in h.subscribes)
        handler_lines += ['    HandlerSpec(', "        name='%s.%s'," % (module, h.name), '        subscribes=(%s%s),' % (', '.join(subs), ',' if len(subs) == 1 else ''),
                          '        emits=%r,' % (tuple(h.emits),), '        writes=%r,' % (tuple(h.writes),), '        lock=%r,' % (h.lock,),
                          '        single_recipient=%r,' % single, '    ),']
    head = [HEADER + '"""Événements de `%s` (niveau A) et abonnements de ses handlers. Un événement est un fait passé ou une demande à un seul moteur ; jamais une commande déguisée."""' % module,
            'from __future__ import annotations', '', 'from dataclasses import dataclass']
    typestr = ' '.join(types_used)
    dt = [n for n in ('date', 'datetime') if re.search(r'\b%s\b' % n, typestr)]
    if dt:
        head.append('from datetime import %s' % ', '.join(dt))
    head.append('from typing import ClassVar')
    if re.search(r'\bUUID\b', typestr):
        head.append('from uuid import UUID')
    head.append('')
    kern = sorted({n for n in re.findall(r'[A-Za-z_]+', typestr) if n in KERNEL_IDS})
    if kern:
        head.append('from verqia.kernel.types import %s' % ', '.join(kern))
    kev = ['Event', 'EventCategory'] if events else []
    if handlers:
        kev.append('HandlerSpec')
    if kev:
        head.append('from verqia.kernel.events import %s' % ', '.join(kev))
    for home in sorted(imports_ev):
        head.append('from verqia.%s.contracts.events import %s' % (home, ', '.join(sorted(imports_ev[home]))))
    head += ['', '', '']
    text = '\n'.join(head) + '\n'.join(cls_lines)
    if handlers:
        text += 'HANDLERS: tuple[HandlerSpec, ...] = (\n' + '\n'.join(handler_lines) + '\n)\n'
    return text.rstrip('\n') + '\n'


def gen_ports(module):
    keys = [k for k, v in M.PORT_REGISTRY.items() if v[0] == module]
    imps, body = [], []
    for k in keys:
        imp, src = PORT_SRC[k]
        imps.append(imp)
        body.append(src)
    uses_map = any(k == 'rules.FactProvider' for k in keys)
    typing_names = ['Protocol'] + (['Mapping', 'Sequence'] if uses_map else [])
    head = [HEADER + '"""Ports de `%s` (niveau A) : des capacités requises ou fournies, jamais des implémentations."""' % module,
            'from __future__ import annotations', '', 'from typing import %s' % ', '.join(sorted(typing_names)), '']
    lines = []
    for imp in imps:
        for l in imp.strip('\n').split('\n'):
            if l not in lines:
                lines.append(l)
    return '\n'.join(head + sorted(lines) + ['', '']) + '\n\n'.join(body).rstrip('\n') + '\n'


def generate():
    """Retourne (fichiers, statistiques) : dict chemin relatif -> contenu."""
    B.run()
    files, stats = {}, {}
    catalogue = load_catalogue_full()
    cons = {}
    for c in K.COMMANDS:
        for e in c.subscribes:
            cons.setdefault(e, []).append('%s.%s' % (c.module, c.name))
    event_home = {ev['type']: event_module(ev, cons) for ev in catalogue}
    # consommateurs de chaque lecture publiée
    consumers = {}
    for m, d in M.MODULES.items():
        for r in d['reads']:
            consumers.setdefault(r, set()).add(m)
    for c in K.COMMANDS:
        for t in c.calls:
            r = B.resolve_call(c, t)
            if r and r[0] == 'query' and r[1] != c.module:
                consumers.setdefault('%s.%s' % (r[1], r[2]), set()).add(c.module)
    files['verqia/__init__.py'] = HEADER + '"""VERQIA : monolithe modulaire (TD1). Contrats V1 générés depuis les registres gelés."""\n'
    err_text, codes = kernel_errors()
    files['verqia/kernel/__init__.py'] = HEADER + '"""Noyau partagé, sans cadre logiciel : types, contexte, erreurs, événements, ports."""\n'
    files['verqia/kernel/types.py'] = KERNEL_TYPES
    files['verqia/kernel/context.py'] = KERNEL_CONTEXT
    files['verqia/kernel/errors.py'] = err_text
    files['verqia/kernel/events.py'] = KERNEL_EVENTS
    files['verqia/kernel/ports.py'] = KERNEL_PORTS
    stats['error_codes'] = codes
    for m, d in M.MODULES.items():
        if m == 'kernel':
            continue
        files['verqia/%s/__init__.py' % m] = HEADER + '"""Module `%s` (%s) : %s"""\n' % (m, d['group'], d['note'] or 'contrats publics dans `contracts/`.')
        if m == 'config':
            continue
        cmds = [c for c in K.COMMANDS if c.module == m and c.kind != 'handler']
        handlers = [c for c in K.COMMANDS if c.module == m and c.kind == 'handler']
        events = [ev for ev in catalogue if event_home[ev['type']] == m]
        has_ports = any(v[0] == m for v in M.PORT_REGISTRY.values())
        base = 'verqia/%s/contracts/' % m
        needed = {}
        if cmds:
            needed['commands.py'] = gen_commands(m, cmds)
        if d['queries']:
            needed['queries.py'] = gen_queries(m, consumers)
        if events or handlers:
            needed['events.py'] = gen_events(m, events, handlers, event_home)
        if has_ports:
            needed['ports.py'] = gen_ports(m)
        if m in MODULE_TYPES:
            needed['types.py'] = MODULE_TYPES[m]()
        if not needed:
            continue
        files[base + '__init__.py'] = HEADER + '"""Contrats publics de `%s` : la seule surface importable par les autres modules (TD4)."""\n' % m
        for n, t in needed.items():
            files[base + n] = t
    import gen_application
    gen_application.add_files(files)
    return files, stats


def write(files, out):
    for rel, text in files.items():
        p = os.path.join(out, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)


def main():
    out = DEFAULT_OUT
    if '--out' in sys.argv:
        out = sys.argv[sys.argv.index('--out') + 1]
    files, stats = generate()
    if '--check' in sys.argv:
        drift = []
        for rel, text in files.items():
            p = os.path.join(out, rel.replace('/', os.sep))
            if not os.path.exists(p) or io.open(p, encoding='utf-8', newline='').read() != text:
                drift.append(rel)
        extra = []
        for root, _, names in os.walk(os.path.join(out, 'verqia')):
            for n in names:
                if n.endswith('.py'):
                    rel = os.path.relpath(os.path.join(root, n), out).replace(os.sep, '/')
                    if rel not in files and not is_handwritten(rel):
                        extra.append(rel)
        print('dérive : %d fichier(s) modifié(s) ou absent(s), %d fichier(s) en trop' % (len(drift), len(extra)))
        for x in drift + extra:
            print('  ', x)
        sys.exit(1 if drift or extra else 0)
    write(files, out)
    if '--no-doc' not in sys.argv:
        import gen_contracts_doc
        with io.open(os.path.join(DOCS, 'MODULE_CONTRACTS_V1.md'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(gen_contracts_doc.render_doc(files))
    print('%d fichiers écrits dans %s' % (len(files), out))


if __name__ == '__main__':
    main()
