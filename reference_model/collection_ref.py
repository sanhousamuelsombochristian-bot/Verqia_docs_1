"""VERQIA : référence Collection (spécification exécutable), Collection Domain V3 — 22 cas d'usage.

Règles de ce module (même discipline que `risk_ref.py` et `priority_ref.py`) :
  * NAÏVE et INDÉPENDANTE : aucune importation de `verqia`, du Domain, de `verqia_models`, des autres références ;
    bibliothèque standard seulement ; transcrite depuis les sources GELÉES (`COLLECTION_ENGINE_V1.md` §2-§14,
    `COLLECTION_ENGINE_V1_2.md`, `STATE_MACHINES_V1.md` §8-§9, `INVARIANTS_V1.md` §7.1-§7.2 §10,
    `DATA_CONTRACT_V1.md` §6.1-§6.3, `ENGINE_CONTRACTS_V1.md` §EC-11, et la spécification
    `COLLECTION_DOMAIN_V1.md`), JAMAIS depuis une future implémentation du Domain ;
  * AUCUNE horloge : `as_of` est toujours un paramètre explicite (jamais `datetime.now()`) ;
  * AUCUN identifiant généré, AUCUNE persistance, AUCUN accès réseau ;
  * Collection **ne recalcule jamais** une règle : une `ReferenceRuleDecision` est reçue en ENTRÉE, avec son
    `outcome`, son `level` et ses codes déjà évalués par le Rule Engine (DV4-1, gelé). Ce module ne contient
    donc ni barème de niveau, ni évaluation d'exception L1, ni calcul de risque ou de priorité — les valider,
    oui (plage 1-5, plancher, non-régression : invariants structurels du Collection Engine, §3.1bis catégorie A) ;
    les produire, jamais ;
  * le résultat d'un cas d'usage est son CONTRAT OBSERVABLE (`ReferenceDecision`), pas un état interne : deux
    implémentations de structures internes différentes sont équivalentes si leurs `ReferenceDecision` coïncident ;
  * le `SlotCalculator` de §7 est transcrit DEUX FOIS, indépendamment (`next_slot_a`, `next_slot_b`), pour que
    l'égalité des deux transcriptions détecte une erreur de lecture avant toute implémentation ;
  * là où la spécification est explicitement OPEN, l'oracle le SIGNALE (`ReferenceDecision.reserves`) au lieu
    d'inventer une valeur : un oracle qui comble un silence n'est plus un oracle.

Modélisation du temps : instants naïfs exprimés dans le fuseau de l'organisation (§7 « fuseau de l'organisation »).
C'est un choix de MODÉLISATION de cette référence, pas une affirmation de la spécification ; il est exact pour le
scénario de référence §11 (Africa/Abidjan, sans heure d'été) et évite d'introduire une dépendance de fuseau dans un
oracle qui doit rester comparable champ par champ.
"""
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta

# --------------------------------------------------------------------------- listes fermées (sources gelées)

# `STATE_MACHINES_V1.md` §8 ; `INVARIANTS_V1.md` §7.1 ligne « 4 Transitions »
STATUSES = ('PROPOSED', 'SCHEDULED', 'PENDING_APPROVAL', 'EXECUTING', 'DONE', 'FAILED', 'CANCELLED', 'SUPPRESSED')
TERMINAL = ('DONE', 'FAILED', 'CANCELLED', 'SUPPRESSED')
# portée des réactions de suppression (`COLLECTION_ENGINE_V1.md` §12 préambule : « Actions concernées »)
SUPPRESSIBLE = ('PROPOSED', 'SCHEDULED', 'PENDING_APPROVAL')

# `DATA_CONTRACT_V1.md` §6.1 ; `COLLECTION_ENGINE_V1.md` §2
ACTION_TYPES = ('REMINDER', 'CALL_TASK', 'FOLLOW_UP', 'ESCALATION')
HUMAN_TASK_TYPES = ('CALL_TASK', 'FOLLOW_UP', 'ESCALATION')
CLIENT_FACING_TYPES = ('REMINDER',)          # §7 point 5 : seules les actions envoyées au client ont une fenêtre

# `COLLECTION_ENGINE_V1.md` §13 (liste fermée C7) ; `DATA_CONTRACT_V1.md` §6.1 `CHECK`
OUTCOMES_SEND = ('SENT', 'BOUNCED')
OUTCOMES_TASK = ('CONTACTED', 'NO_ANSWER', 'PROMISE_OBTAINED', 'DISPUTE_RAISED', 'REFUSED', 'WRONG_CONTACT', 'OTHER')
OUTCOMES_CANCEL = ('USER_CANCELLED', 'APPROVAL_REJECTED', 'APPROVAL_EXPIRED')
OUTCOMES_ALL = OUTCOMES_SEND + OUTCOMES_TASK + OUTCOMES_CANCEL
# §8.2 : les deux issues qui SUGGÈRENT à l'interface, sans jamais créer
OUTCOMES_SUGGESTING = ('PROMISE_OBTAINED', 'DISPUTE_RAISED')

# `DATA_CONTRACT_V1.md` §6.1 ; `RULE_ENGINE_V1.md` §3 (13 exceptions L1, ordre fixe)
SUPPRESSION_CODES = ('PAID', 'VOIDED', 'DISPUTED', 'PROMISE_ACTIVE', 'HOLD_ACTIVE', 'IMPORT_HELD',
                     'RECONCILIATION_PENDING', 'FREQUENCY_LIMIT', 'NO_CONTACT', 'NO_CONSENT',
                     'CUSTOMER_INACTIVE', 'CUSTOMER_ARCHIVED', 'ORG_INACTIVE')

# `INVARIANTS_V1.md` §10 : catalogue fermé des événements produits par ce Domain
EVENTS = ('COLLECTION_ACTION_PROPOSED', 'COLLECTION_ACTION_SCHEDULED', 'COLLECTION_ACTION_EXECUTED',
          'COLLECTION_ACTION_FAILED', 'COLLECTION_ACTION_CANCELLED', 'COLLECTION_ACTION_SUPPRESSED',
          'COLLECTION_HOLD_PLACED', 'COLLECTION_HOLD_RELEASED')

# `COLLECTION_ENGINE_V1.md` §12 : événement -> code de suppression (C1 à C7)
SUPPRESSION_ON_EVENT = {
    'INVOICE_PAID': 'PAID',                       # C1
    'INVOICE_VOIDED': 'VOIDED',                   # C2
    'INVOICE_CANCELLED': 'VOIDED',                # C2
    'INVOICE_DISPUTED': 'DISPUTED',               # C3, CONDITIONNEL : seulement si collectible_minor == 0 (D1)
    'PROMISE_CREATED': 'PROMISE_ACTIVE',          # C4
    'COLLECTION_HOLD_PLACED': 'HOLD_ACTIVE',      # C5
    'CUSTOMER_DEACTIVATED': 'CUSTOMER_INACTIVE',  # C6
    'CUSTOMER_ARCHIVED': 'CUSTOMER_ARCHIVED',     # C6
    'ORGANIZATION_SUSPENDED': 'ORG_INACTIVE',     # C7
    'ORGANIZATION_CLOSED': 'ORG_INACTIVE',        # C7, DV4-7 : traité comme _SUSPENDED
}

# `COLLECTION_ENGINE_V1.md` §9 : réessai d'une erreur transitoire, puis échec
RETRY_DELAYS = (timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2))
MAX_ATTEMPTS = 3                                   # §9, « 3 par défaut »
REAP_AFTER = timedelta(minutes=15)                 # §8.3 + `ENGINE_CONTRACTS_V1.md` §EC-03
MIN_LEVEL_WHEN_OVERDUE = 3                         # §3.1bis catégorie A, « niveau minimal 3 dès OVERDUE »
LEVEL_RANGE = (1, 5)                               # `INVARIANTS_V1.md` §7.1, « level entre 1 et 5 [VERROUILLÉ] »

# `COLLECTION_ENGINE_V1.md` §9, classes d'échec d'envoi
ERROR_CLASSES = ('TRANSIENT', 'PERMANENT', 'CONFIGURATION', 'BUSINESS')


# --------------------------------------------------------------------------- types de référence minimaux

@dataclass(frozen=True)
class ReferenceAction:
    """État observable d'une action. Champs strictement issus de `DATA_CONTRACT_V1.md` §6.1."""
    action_id: str
    invoice_id: str
    customer_id: str
    type: str
    level: int
    origin: str = 'AUTOMATION'                 # AUTOMATION | MANUAL
    cycle: int = 0
    occurrence: int = 0
    status: str = 'PROPOSED'
    scheduled_for: datetime | None = None
    assigned_to: str | None = None
    assigned_role: str | None = None
    outcome: str | None = None
    outcome_note: str | None = None
    executed_at: datetime | None = None
    suppression_code: str | None = None
    attempts: int = 0
    next_retry_at: datetime | None = None
    executing_since: datetime | None = None
    manual_key: str | None = None              # clé d'idempotence d'une création manuelle (§4)

    def is_human_task(self):
        return self.type in HUMAN_TASK_TYPES

    def is_terminal(self):
        return self.status in TERMINAL


@dataclass(frozen=True)
class ReferenceRuleDecision:
    """Décision REÇUE du Rule Engine. Ce module ne la produit ni ne la recalcule jamais (DV4-1)."""
    outcome: str                               # PROCEED | SUPPRESS | SKIP | DEFER
    level: int | None = None
    suppression_code: str | None = None
    retry_at: datetime | None = None
    requires_approval: bool = False
    risk_level: str | None = None
    priority_level: str | None = None
    primary_exception: str | None = None
    exceptions_trace: tuple = ()
    overrides: tuple = ()


@dataclass(frozen=True)
class ReferenceFacts:
    """Faits reçus (assemblés hors Domain). Aucun n'est dérivé ici d'une règle."""
    invoice_exists: bool = True
    invoice_is_open: bool = True
    invoice_overdue: bool = False
    collectible_minor: int = 0
    collection_cycle: int = 0
    messages_already_that_day: int = 0         # §7 point 3, plafond par client
    sends_already_that_hour: int = 0           # §7 point 4, lissage
    actor_role: str | None = None
    actor_id: str | None = None
    actor_active: bool = True


@dataclass(frozen=True)
class ReferenceOrgRules:
    """Règles de placement : catégorie C (réglages d'organisation) et B (stratégie), §3.1bis, §7."""
    comm_window_start: time = time(8, 0)                # C, `org_settings.comm_window_start`
    comm_window_end: time = time(18, 0)                 # C, `org_settings.comm_window_end`
    business_weekdays: tuple = (0, 1, 2, 3, 4)          # C, lundi-vendredi par défaut (§11)
    holidays: frozenset = frozenset()                   # C, `org_holidays`
    send_hour: time = time(9, 0)                        # B, « heure d'envoi visée (09:00) », §3.3
    max_customer_messages_per_day: int = 2              # C, `extra.max_customer_messages_per_day`
    send_rate_per_hour: int = 200                       # C, `extra.send_rate_per_hour`

    def is_business_day(self, d):
        return d.weekday() in self.business_weekdays and d not in self.holidays

    def send_hour_inside_window(self):
        return self.comm_window_start <= self.send_hour < self.comm_window_end


class PlacementRulesInconsistent(Exception):
    """CONSTAT sur la spécification gelée (relevé par cet oracle, non tranché) — voir `notes.md` / §17.

    `heure d'envoi visée` est un paramètre de **catégorie B** (par version de définition d'automatisation, §3.1bis)
    tandis que la `fenêtre de communication` est de **catégorie C** (par organisation) — et §3.1bis justifie
    précisément la catégorie C par le fait qu'une définition ne peut pas connaître les réglages de chaque
    organisation. Les deux peuvent donc se contredire. Or si l'heure visée tombe HORS de la fenêtre, les règles du
    §7 lues littéralement ne terminent pas : chaque jour est abordé à l'heure visée, hors fenêtre, donc débordé
    vers le jour suivant, indéfiniment. Aucune source consultée ne contraint l'heure visée à tomber dans la
    fenêtre, et aucune règle de validation de définition ne le vérifie (`RULE_ENGINE_V1.md` §5).

    L'oracle REFUSE donc cette configuration explicitement plutôt que de choisir une règle de repli (écrêtage sur
    le début de fenêtre ? sur la fin ? refus de la définition ?) qu'aucune source n'énonce.
    """


@dataclass(frozen=True)
class ReferenceDecision:
    """Contrat OBSERVABLE d'un cas d'usage : ce qui doit coïncider entre l'oracle et toute implémentation."""
    use_case: str
    issue: str                                  # OK | REPLAY | SKIPPED | DEFERRED | PROCESSED | REFUSED
    refusal: str | None = None                   # code d'erreur, ou None (voir `reserves` si non nommé)
    transition: tuple | None = None              # (état_avant, état_après) ; None = aucune transition de statut
    writes: tuple = ()                           # ((champ, valeur), ...) trié, comparable
    events: tuple = ()
    suppression: str | None = None
    retry_at: datetime | None = None
    dedup_key: str | None = None
    audit: bool = False
    reserves: tuple = ()                         # réserves OPEN rencontrées, jamais comblées

    def with_writes(self, **kw):
        return replace(self, writes=tuple(sorted(kw.items())))


def _decision(use_case, issue, **kw):
    writes = kw.pop('writes', {})
    return ReferenceDecision(use_case=use_case, issue=issue, writes=tuple(sorted(writes.items())), **kw)


# --------------------------------------------------------------------------- déduplication (§4, DV4-4, AM-01)

def dedup_key(invoice_id, type_, level, cycle, occurrence):
    """`INVARIANTS_V1.md` §7.1 après AM-01 : `{invoice_id}:{type}:L{level}:C{cycle}:R{occurrence}`.

    `occurrence` est TOUJOURS fournie (produite par l'Automation Engine) : ce module ne la choisit jamais (C4).
    """
    return '%s:%s:L%d:C%d:R%d' % (invoice_id, type_, level, cycle, occurrence)


def manual_dedup_key(idempotency_key):
    """§4, actions manuelles : formule distincte, jamais confondue avec la clé automatique."""
    return 'manual:%s' % idempotency_key


def key_blocks_duplicate(status):
    """`DATA_CONTRACT_V1.md` §6.1 : UQ partiel `WHERE status NOT IN ('CANCELLED','SUPPRESSED')`.

    `DONE` et `FAILED` continuent donc de bloquer ; `CANCELLED` et `SUPPRESSED` libèrent la clé.
    """
    return status not in ('CANCELLED', 'SUPPRESSED')


def existing_for_key(actions, key):
    """L'action vivante qui occupe la clé, s'il y en a une."""
    for a in actions:
        if a_key(a) == key and key_blocks_duplicate(a.status):
            return a
    return None


def a_key(a):
    return manual_dedup_key(a.manual_key) if a.manual_key else dedup_key(a.invoice_id, a.type, a.level, a.cycle, a.occurrence)


def highest_reached_level(actions, invoice_id, cycle):
    """Non-régression R9 (§11) : plus haut niveau `SCHEDULED`, `EXECUTING` ou `DONE` dans un (facture, cycle)."""
    reached = [a.level for a in actions
               if a.invoice_id == invoice_id and a.cycle == cycle and a.status in ('SCHEDULED', 'EXECUTING', 'DONE')]
    return max(reached) if reached else None


# --------------------------------------------------------------------------- §7 : SlotCalculator, transcription A

def next_slot_a(as_of, target, rules, client_facing, task_due_date=None,
                messages_that_day=0, sends_that_hour=0):
    """Transcription A de `prochain_créneau(as_of, heure_visée, règles)` — §7 points 1 à 5.

    Formulation ITÉRATIVE : on part de l'instant visé et on avance jusqu'à satisfaire chaque règle, dans l'ordre
    du document. `client_facing` distingue le point 2 (fenêtre, plafond, lissage) du point 5 (tâche humaine).
    """
    if not client_facing:
        # 5. Tâches humaines et escalades : pas de fenêtre ; `scheduled_for` = échéance de la tâche ; jour ouvré
        #    conservé par défaut.
        d = task_due_date if task_due_date is not None else target.date()
        while not rules.is_business_day(d):
            d += timedelta(days=1)
        return datetime.combine(d, target.timetz().replace(tzinfo=None) if target else rules.send_hour)

    if not rules.send_hour_inside_window():
        raise PlacementRulesInconsistent(
            'heure d\'envoi visée %s hors de la fenêtre %s-%s : §7 ne termine pas'
            % (rules.send_hour, rules.comm_window_start, rules.comm_window_end))

    # Portée des deux faits de saturation : ils décrivent UN instant précis (le jour de la cible, l'heure de la
    # cible) et rien d'autre. Un scalaire ne dit rien d'un autre jour ni d'une autre heure : dès que le candidat
    # quitte cet instant, le fait cesse de s'appliquer. C'est une décision de MODÉLISATION de cette référence,
    # nécessaire parce que §7 ne décrit pas la portée de ces compteurs ; elle est identique dans les deux
    # transcriptions, sans quoi leur égalité ne voudrait rien dire.
    saturated_day = target.date() if messages_that_day >= rules.max_customer_messages_per_day else None
    throttled_hour = target.hour if sends_that_hour >= rules.send_rate_per_hour else None

    # 1. Partir de l'instant visé.
    at = target
    for _ in range(400):                                  # borne de sûreté : jamais atteinte sur des règles saines
        # 2a. avancer jusqu'à un jour ouvré
        if not rules.is_business_day(at.date()):
            at = datetime.combine(at.date() + timedelta(days=1), rules.send_hour)
            continue
        # 2b. puis jusqu'à l'intérieur de la fenêtre de communication
        if at.time() < rules.comm_window_start:
            at = datetime.combine(at.date(), rules.comm_window_start)
            continue
        if at.time() >= rules.comm_window_end:
            at = datetime.combine(at.date() + timedelta(days=1), rules.send_hour)
            continue
        # 3. plafond par client : ce jour-là est saturé -> jour ouvré suivant
        if at.date() == saturated_day:
            at = datetime.combine(at.date() + timedelta(days=1), rules.send_hour)
            continue
        # 4. lissage : débit horaire dépassé -> décaler d'une heure ; si ce décalage sort de la journée ou de la
        #    fenêtre, on aborde le jour suivant à SON heure d'envoi visée (§7 point 1, « heure d'envoi visée du
        #    jour »), jamais en poursuivant depuis l'instant décalé — c'est ce que §11 exhibe (débordement du
        #    dimanche vers lundi 09:00, l'heure visée, et non 08:00, le début de fenêtre).
        if at.date() == target.date() and at.hour == throttled_hour:
            shifted = at + timedelta(hours=1)
            if shifted.date() != at.date() or shifted.time() >= rules.comm_window_end:
                at = datetime.combine(at.date() + timedelta(days=1), rules.send_hour)
            else:
                at = shifted
            continue
        return at
    raise AssertionError('règles de placement non convergentes')


# --------------------------------------------------------------------------- §7 : SlotCalculator, transcription B

def next_slot_b(as_of, target, rules, client_facing, task_due_date=None,
                messages_that_day=0, sends_that_hour=0):
    """Transcription B, INDÉPENDANTE de A : énumération de créneaux candidats puis premier acceptable.

    Même source (§7), formulation différente : A avance par corrections successives, B génère les candidats
    (jour ouvré, heure dans la fenêtre) et retient le premier qui satisfait tous les prédicats. Leur égalité sur
    les cas de référence est ce qui atteste la transcription (voir `test_collection_ref.py`).
    """
    if not client_facing:
        base = task_due_date if task_due_date is not None else target.date()
        day = next(d for d in _days_from(base) if rules.is_business_day(d))
        hour = target.timetz().replace(tzinfo=None) if target else rules.send_hour
        return datetime.combine(day, hour)

    if not rules.send_hour_inside_window():
        raise PlacementRulesInconsistent(
            'heure d\'envoi visée %s hors de la fenêtre %s-%s : §7 ne termine pas'
            % (rules.send_hour, rules.comm_window_start, rules.comm_window_end))

    saturated_day = target.date() if messages_that_day >= rules.max_customer_messages_per_day else None
    throttled_hour = target.hour if sends_that_hour >= rules.send_rate_per_hour else None

    for day in _days_from(target.date()):
        if not rules.is_business_day(day):              # 2a. jour ouvré
            continue
        if day == saturated_day:                        # 3. plafond par client : ce jour est saturé
            continue
        for at in _candidates_of_day(day, rules, target):
            if day == target.date() and at.hour == throttled_hour:
                continue                                # 4. lissage : décalage d'une heure = candidat suivant
            return at
    raise AssertionError('règles de placement non convergentes')


def _days_from(d):
    for k in range(400):
        yield d + timedelta(days=k)


def _candidates_of_day(day, rules, target):
    """Instants candidats d'un jour ouvré, du plus tôt au plus tard, par pas d'une heure (§7 points 1, 2, 4).

    Ancrage du jour : le jour de l'instant visé démarre à cet instant même, ramené à l'intérieur de la fenêtre
    (§7 point 2, « avancer jusqu'à l'intérieur de la fenêtre ») ; un jour de débordement démarre à l'heure d'envoi
    visée DE CE JOUR (§7 point 1, « heure d'envoi visée du jour »), elle aussi ramenée dans la fenêtre. Aucun
    candidat n'est jamais antérieur à l'instant visé : les opérateurs du §7 avancent, ils ne reculent pas.
    """
    lo = datetime.combine(day, rules.comm_window_start)
    hi = datetime.combine(day, rules.comm_window_end)
    anchor = target if day == target.date() else datetime.combine(day, rules.send_hour)
    at = max(anchor, lo, target)
    while at < hi:
        yield at
        at = at + timedelta(hours=1)                    # « décaler d'une heure », sans arrondi


def anchored_target(target, as_of):
    """Ancrage d'une replanification : `max(cible, as_of)`.

    DÉCISION NORMATIVE du 2026-09-29 (BLOCKER-1, `COLLECTION_DOMAIN_V1.md` §4 A12 point 4) : §7 ne définit pas
    d'ancrage ; normaliser depuis une cible passée produirait un créneau immédiatement échu, donc un envoi hors
    de la fenêtre de communication, et un état que nul autre chemin du système ne produit.
    """
    return target if target >= as_of else as_of


# --------------------------------------------------------------------------- A1 / A4 : création

def _validate_level(level, facts):
    """Invariants structurels de niveau (§3.1bis catégorie A) : plage, puis plancher après `OVERDUE`.

    VALIDE un niveau reçu ; ne le calcule jamais (DV4-1).
    """
    lo, hi = LEVEL_RANGE
    if level is None or not (lo <= level <= hi):
        return 'ACTION_LEVEL_INVALID'
    if facts.invoice_overdue and level < MIN_LEVEL_WHEN_OVERDUE:
        return 'ACTION_LEVEL_BELOW_MINIMUM'
    return None


def create_collection_action(actions, command, decision, facts, as_of, rules, manual=False):
    """A1 `CreateCollectionAction` et A4 `CreateManualAction` — §4, `STATE_MACHINES_V1.md` §8.

    `command` : dict {invoice_id, customer_id, type, level, cycle, occurrence, idempotency_key?, assigned_role?}.
    Le niveau vient de la décision reçue (A1) ou de l'utilisateur (A4) ; dans les deux cas il est VALIDÉ, jamais
    calculé. L'audit est toujours requis pour A4, conditionnel pour A1 (§4, D3).
    """
    uc = 'CreateManualAction' if manual else 'CreateCollectionAction'
    key = manual_dedup_key(command['idempotency_key']) if manual else dedup_key(
        command['invoice_id'], command['type'], command['level'], command['cycle'], command['occurrence'])

    if not facts.invoice_exists:
        return _decision(uc, 'REFUSED', refusal='SUBJECT_NOT_FOUND', dedup_key=key, audit=manual)

    bad = _validate_level(command['level'], facts)
    if bad:
        return _decision(uc, 'REFUSED', refusal=bad, dedup_key=key, audit=manual)

    existing = existing_for_key(actions, key)
    if existing is not None:
        # §11 : « un seul exemplaire par (facture, type, niveau, cycle, répétition) » -> l'existante est renvoyée
        return _decision(uc, 'REPLAY', dedup_key=key, audit=manual)

    reached = highest_reached_level(actions, command['invoice_id'], command['cycle'])
    if reached is not None and command['level'] < reached:
        # Non-régression R9 : refus. Le catalogue `INVARIANTS_V1.md` §7.1 nomme `ACTION_LEVEL_REGRESSION`, mais
        # aucun cas d'usage ne le déclare dans le registre : réserve R-7, non comblée ici.
        return _decision(uc, 'REFUSED', refusal=None, dedup_key=key, audit=manual,
                         reserves=('R-7 : régression de niveau refusée, code d\'erreur non rattaché dans le registre',))

    if decision.outcome == 'SUPPRESS':
        # §4 : créée DIRECTEMENT en SUPPRESSED (une seule ligne, jamais deux écritures)
        return _decision(uc, 'SKIPPED', transition=(None, 'SUPPRESSED'), dedup_key=key, audit=manual,
                         suppression=decision.suppression_code,
                         events=('COLLECTION_ACTION_SUPPRESSED',),
                         writes={'status': 'SUPPRESSED', 'suppression_code': decision.suppression_code,
                                 'level': command['level'], 'dedup_key': key,
                                 'origin': 'MANUAL' if manual else 'AUTOMATION'})
    if decision.outcome == 'SKIP':
        return _decision(uc, 'SKIPPED', dedup_key=key, audit=manual)
    if decision.outcome == 'DEFER':
        return _decision(uc, 'DEFERRED', dedup_key=key, audit=manual, retry_at=decision.retry_at)

    return _decision(uc, 'OK', transition=(None, 'PROPOSED'), dedup_key=key, audit=manual,
                     events=('COLLECTION_ACTION_PROPOSED',),
                     writes={'status': 'PROPOSED', 'level': command['level'], 'dedup_key': key,
                             'origin': 'MANUAL' if manual else 'AUTOMATION'})


# --------------------------------------------------------------------------- A2 : progression

def advance_proposed_action(action, decision, facts, as_of, rules, target=None, task_due_date=None):
    """A2 `AdvanceProposedAction` — §4 étape 7, `STATE_MACHINES_V1.md` §8.

    Garde d'état : `PROPOSED` seulement. La décision reçue est une NOUVELLE évaluation (le `decision_snapshot`
    de création n'est jamais relu comme autorité, DV4-1 / OPEN-06 A2).
    """
    uc = 'AdvanceProposedAction'
    if action.status != 'PROPOSED':
        return _decision(uc, 'SKIPPED')

    if decision.outcome == 'SUPPRESS':
        return _decision(uc, 'OK', transition=('PROPOSED', 'SUPPRESSED'), suppression=decision.suppression_code,
                         events=('COLLECTION_ACTION_SUPPRESSED',),
                         writes={'status': 'SUPPRESSED', 'suppression_code': decision.suppression_code})
    if decision.outcome == 'DEFER':
        return _decision(uc, 'DEFERRED', retry_at=decision.retry_at)
    if decision.requires_approval:
        # §6 : les tâches humaines et les escalades n'exigent jamais d'approbation
        if action.is_human_task():
            pass
        else:
            return _decision(uc, 'OK', transition=('PROPOSED', 'PENDING_APPROVAL'),
                             writes={'status': 'PENDING_APPROVAL'})

    client_facing = action.type in CLIENT_FACING_TYPES
    aimed = target if target is not None else datetime.combine(as_of.date(), rules.send_hour)
    slot = next_slot_a(as_of, aimed, rules, client_facing, task_due_date,
                       facts.messages_already_that_day, facts.sends_already_that_hour)
    return _decision(uc, 'OK', transition=('PROPOSED', 'SCHEDULED'),
                     events=('COLLECTION_ACTION_SCHEDULED',),
                     writes={'status': 'SCHEDULED', 'scheduled_for': slot})


def resume_proposed_actions(actions, decisions, facts, as_of, rules):
    """A3 `ResumeProposedActions` — balayage : rejoue A2 sur chaque ligne restée `PROPOSED`, même garde.

    Aucune décision propre. La CADENCE de ce balayage n'est spécifiée par aucune source (OPEN-02) : elle est hors
    de ce module, qui n'a pas d'horloge.
    """
    out = []
    for a in actions:
        if a.status == 'PROPOSED':
            out.append(advance_proposed_action(a, decisions[a.action_id], facts, as_of, rules))
    return tuple(out)


# --------------------------------------------------------------------------- A5 : annulation

def cancel_collection_action(action, reason, as_of):
    """A5 `CancelCollectionAction` — `STATE_MACHINES_V1.md` §8 : tout état NON TERMINAL -> `CANCELLED`, motif."""
    uc = 'CancelCollectionAction'
    if action.is_terminal():
        return _decision(uc, 'REPLAY' if action.status == 'CANCELLED' else 'REFUSED',
                         refusal=None if action.status == 'CANCELLED' else 'ACTION_INVALID_TRANSITION', audit=True)
    if not reason:
        return _decision(uc, 'REFUSED', refusal=None, audit=True,
                         reserves=('motif obligatoire (`STATE_MACHINES_V1.md` §8) sans code d\'erreur nommé',))
    return _decision(uc, 'OK', transition=(action.status, 'CANCELLED'), audit=True,
                     events=('COLLECTION_ACTION_CANCELLED',),
                     writes={'status': 'CANCELLED', 'outcome': 'USER_CANCELLED', 'outcome_note': reason})


# --------------------------------------------------------------------------- A6 / A7 / A9 : exécution

def execute_due_action(action, decision, facts, as_of, rules):
    """A6 `ExecuteDueAction`, phase CLAIM — §8.1 étapes 1-2.

    Seul point de revalidation complète (contexte D). La transition finale (`DONE`/`FAILED`) n'appartient PAS à ce
    cas d'usage : elle est produite par A9 (`emits` d'A6 ne contient que `_SUPPRESSED`).
    """
    uc = 'ExecuteDueAction'
    if action.status != 'SCHEDULED':
        return _decision(uc, 'SKIPPED')
    if action.scheduled_for is not None and action.scheduled_for > as_of:
        return _decision(uc, 'SKIPPED')
    if action.attempts >= MAX_ATTEMPTS:
        return _decision(uc, 'REFUSED', refusal='ACTION_MAX_ATTEMPTS_REACHED',
                         reserves=('R-7 : `ACTION_MAX_ATTEMPTS_REACHED` au catalogue des invariants, '
                                   'rattaché à aucun cas d\'usage dans le registre',))
    if decision.outcome == 'SUPPRESS':
        return _decision(uc, 'OK', transition=('SCHEDULED', 'SUPPRESSED'), suppression=decision.suppression_code,
                         events=('COLLECTION_ACTION_SUPPRESSED',),
                         writes={'status': 'SUPPRESSED', 'suppression_code': decision.suppression_code})
    if decision.outcome == 'DEFER':
        slot = next_slot_a(as_of, decision.retry_at or as_of, rules, action.type in CLIENT_FACING_TYPES)
        return _decision(uc, 'DEFERRED', retry_at=slot, writes={'scheduled_for': slot})
    return _decision(uc, 'OK', transition=('SCHEDULED', 'EXECUTING'),
                     writes={'status': 'EXECUTING', 'executing_since': as_of, 'attempts': action.attempts + 1})


def reap_actions(action, as_of):
    """A7 `ReapActions` — §8.3 : une action `EXECUTING` depuis plus de 15 min SANS résultat est une tentative
    transitoire échouée (worker interrompu). N'émet aucun événement (OPEN-04 ACCEPTÉ).

    Écrit une ligne d'essai clôturant l'essai abandonné : convergence de §8.3 (« tentative échouée transitoire »),
    §9 (« tentative enregistrée (`collection_action_attempts`) » pour une transitoire) et des écritures déclarées
    d'A7 au registre. Le CODE de la cause reste non nommé dans les sources : réserve R-5.
    """
    uc = 'ReapActions'
    if action.status != 'EXECUTING':
        return _decision(uc, 'SKIPPED')
    if action.executing_since is None or as_of - action.executing_since <= REAP_AFTER:
        return _decision(uc, 'SKIPPED')
    return _decision(uc, 'OK', transition=('EXECUTING', 'SCHEDULED'),
                     retry_at=as_of,
                     writes={'status': 'SCHEDULED', 'executing_since': None,
                             'attempt_closed': ('FAILED', as_of)},
                     reserves=('R-5 : aucun code nommé pour la cause « worker interrompu » de l\'essai clos',))


def on_notification_result(action, result, as_of, rules, error_class=None):
    """A9 `OnNotificationResult` — §8.1 étape 5, §9, `STATE_MACHINES_V1.md` §8. C'est ICI que la boucle se referme.

    `result` : 'SENT' | 'FAILED'. `error_class` ∈ ERROR_CLASSES pour un échec. La classification est un FAIT reçu,
    jamais dérivée ici.
    """
    uc = 'OnNotificationResult'
    if action.status != 'EXECUTING':
        # état devenu terminal entre-temps (annulation pendant un envoi en vol, §15 course 4)
        return _decision(uc, 'SKIPPED')
    if result == 'SENT':
        return _decision(uc, 'PROCESSED', transition=('EXECUTING', 'DONE'),
                         events=('COLLECTION_ACTION_EXECUTED',),
                         writes={'status': 'DONE', 'outcome': 'SENT', 'executed_at': as_of})
    if error_class == 'TRANSIENT' and action.attempts < MAX_ATTEMPTS:
        delay = RETRY_DELAYS[min(action.attempts, len(RETRY_DELAYS)) - 1] if action.attempts else RETRY_DELAYS[0]
        return _decision(uc, 'PROCESSED', transition=('EXECUTING', 'SCHEDULED'),
                         events=('COLLECTION_ACTION_SCHEDULED',), retry_at=as_of + delay,
                         writes={'status': 'SCHEDULED', 'next_retry_at': as_of + delay,
                                 'attempt_closed': ('FAILED', as_of)})
    return _decision(uc, 'PROCESSED', transition=('EXECUTING', 'FAILED'),
                     events=('COLLECTION_ACTION_FAILED',),
                     writes={'status': 'FAILED', 'attempt_closed': ('FAILED', as_of)})


# --------------------------------------------------------------------------- A8 : approbation

def on_approval_decided(action, granted, as_of, rules, facts=None, target=None, task_due_date=None):
    """A8 `OnApprovalDecided` — §6, `STATE_MACHINES_V1.md` §8. Ne rappelle PAS le Rule Engine (DV4-5) : la cible
    est revalidée par `approvals.DecideApproval` AVANT l'émission de l'événement.
    """
    uc = 'OnApprovalDecided'
    if action.status != 'PENDING_APPROVAL':
        return _decision(uc, 'SKIPPED')
    if not granted:
        return _decision(uc, 'PROCESSED', transition=('PENDING_APPROVAL', 'CANCELLED'),
                         events=('COLLECTION_ACTION_CANCELLED',),
                         writes={'status': 'CANCELLED', 'outcome': 'APPROVAL_REJECTED'})
    f = facts or ReferenceFacts()
    aimed = target if target is not None else datetime.combine(as_of.date(), rules.send_hour)
    slot = next_slot_a(as_of, aimed, rules, action.type in CLIENT_FACING_TYPES, task_due_date,
                       f.messages_already_that_day, f.sends_already_that_hour)
    return _decision(uc, 'PROCESSED', transition=('PENDING_APPROVAL', 'SCHEDULED'),
                     events=('COLLECTION_ACTION_SCHEDULED',),
                     writes={'status': 'SCHEDULED', 'scheduled_for': slot})


# --------------------------------------------------------------------------- A10 / A11 : tâches humaines

ROLE_ORDER = ('VIEWER', 'COLLECTOR', 'MANAGER', 'ADMIN', 'OWNER')


def role_at_least(actor_role, required):
    """Comparaison de rôles par ordre croissant. `None` requis = aucune exigence de rôle."""
    if required is None:
        return True
    if actor_role is None:
        return False
    try:
        return ROLE_ORDER.index(actor_role) >= ROLE_ORDER.index(required)
    except ValueError:
        return False


def claim_task(action, actor_id, actor_role, as_of):
    """A10 `ClaimTask` — `ENGINE_CONTRACTS_V1.md` §EC-11, `COLLECTION_ENGINE_V1.md` §5.

    Réclamation gardée : une seule gagne. AUCUNE transition de statut — seul `assigned_to` change
    (`INVARIANTS_V1.md` §7.1, « 2 Modifier »). Aucune décision de règle : réclamer n'est pas décider d'agir.
    Aucun événement explicitement identifié dans les sources examinées (réserve R-1), donc aucun émis ici.
    """
    uc = 'ClaimTask'
    if not action.is_human_task():
        return _decision(uc, 'REFUSED', refusal='ACTION_INVALID_TRANSITION', audit=True)
    if action.status != 'SCHEDULED':
        return _decision(uc, 'REFUSED', refusal='ACTION_INVALID_TRANSITION', audit=True)
    if action.assigned_to == actor_id:
        return _decision(uc, 'REPLAY', audit=True)
    if action.assigned_to is not None:
        return _decision(uc, 'REFUSED', refusal='CONCURRENT_MODIFICATION', audit=True)
    if not role_at_least(actor_role, action.assigned_role):
        return _decision(uc, 'REFUSED', refusal='CONCURRENT_MODIFICATION', audit=True,
                         reserves=('rôle insuffisant pour réclamer : EC-11 ne nomme que '
                                   '`CONCURRENT_MODIFICATION` pour ce cas d\'usage',))
    return _decision(uc, 'OK', transition=None, audit=True, writes={'assigned_to': actor_id},
                     reserves=('R-1/R-2 : aucun événement ni audit métier dédié identifié dans les sources',))


def complete_task(action, actor_id, actor_role, outcome, as_of, outcome_note=None):
    """A11 `CompleteTask` — `STATE_MACHINES_V1.md` §8 (`SCHEDULED → DONE`), §8.2, §13.

    Acteur : assigné OU membre autorisé du pool — la réclamation préalable n'est PAS une contrainte métier.
    Revalidation non requise (l'action humaine est déjà accomplie) : aucune décision de règle.
    """
    uc = 'CompleteTask'
    if not action.is_human_task() or action.status != 'SCHEDULED':
        return _decision(uc, 'REPLAY' if action.status == 'DONE' else 'REFUSED',
                         refusal=None if action.status == 'DONE' else 'ACTION_INVALID_TRANSITION', audit=True)
    is_assignee = action.assigned_to is not None and action.assigned_to == actor_id
    if not (is_assignee or role_at_least(actor_role, action.assigned_role)):
        return _decision(uc, 'REFUSED', refusal='INSUFFICIENT_ROLE', audit=True)
    if outcome not in OUTCOMES_TASK:
        return _decision(uc, 'REFUSED', refusal='ACTION_INVALID_TRANSITION', audit=True,
                         reserves=('issue hors de la liste fermée « tâche humaine » (§13) ; EC-11 ne nomme pas '
                                   'de code distinct pour ce refus',))
    return _decision(uc, 'OK', transition=('SCHEDULED', 'DONE'), audit=True,
                     events=('COLLECTION_ACTION_EXECUTED',),
                     writes={'status': 'DONE', 'outcome': outcome, 'outcome_note': outcome_note,
                             'executed_at': as_of},
                     reserves=(('R-3 : aucun audit métier dédié identifié',) +
                               (('§8.2 : l\'issue %s SUGGÈRE la création, ne la fait jamais' % outcome,)
                                if outcome in OUTCOMES_SUGGESTING else ())))


# --------------------------------------------------------------------------- A12 : replanification

def reschedule_action(action, target, as_of, rules, facts=None, task_due_date=None):
    """A12 `RescheduleAction` — §7, `INVARIANTS_V1.md` §7.1 (« `scheduled_for` tant que `PROPOSED`/`SCHEDULED` »).

    État d'entrée FERMÉ à `PROPOSED`/`SCHEDULED` : `PENDING_APPROVAL` et `EXECUTING` sont exclus, contrairement à
    A5. Aucune transition de statut. La cible est une DEMANDE : elle est normalisée, jamais refusée (§7 point 2,
    « ce n'est pas une erreur ») ; pour une cible passée l'ancrage est `max(cible, as_of)` (décision normative
    2026-09-29). Aucun événement explicitement identifié (réserve R-4).
    """
    uc = 'RescheduleAction'
    if action.status not in ('PROPOSED', 'SCHEDULED'):
        return _decision(uc, 'REFUSED', refusal='ACTION_INVALID_TRANSITION', audit=True)
    f = facts or ReferenceFacts()
    aimed = anchored_target(target, as_of)
    slot = next_slot_a(as_of, aimed, rules, action.type in CLIENT_FACING_TYPES, task_due_date,
                       f.messages_already_that_day, f.sends_already_that_hour)
    if action.scheduled_for == slot:
        return _decision(uc, 'REPLAY', audit=True)
    return _decision(uc, 'OK', transition=None, audit=True, writes={'scheduled_for': slot},
                     reserves=('R-4 : aucun événement identifié dans les sources pour la replanification',))


# --------------------------------------------------------------------------- B1 / B2 / B3 : holds

@dataclass(frozen=True)
class ReferenceHold:
    hold_id: str
    scope: str                                   # INVOICE | CUSTOMER | ORGANIZATION
    invoice_id: str | None = None
    customer_id: str | None = None
    automation_id: str | None = None
    kind: str = 'MANUAL'
    reason: str = ''
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: str = 'ACTIVE'                       # ACTIVE | RELEASED | EXPIRED


def _scope_consistent(h):
    """`DATA_CONTRACT_V1.md` §6.3 `CHECK` : portée cohérente avec la cible."""
    if h.scope == 'INVOICE':
        return h.invoice_id is not None
    if h.scope == 'CUSTOMER':
        return h.customer_id is not None and h.invoice_id is None
    return h.invoice_id is None and h.customer_id is None


def _overlaps(a, b):
    lo = max(a.starts_at, b.starts_at)
    hi_a = a.ends_at or datetime.max
    hi_b = b.ends_at or datetime.max
    return lo < min(hi_a, hi_b)


def place_hold(holds, hold, actor_role, as_of):
    """B1 `PlaceHold` — `STATE_MACHINES_V1.md` §9, `INVARIANTS_V1.md` §7.2, `DATA_CONTRACT_V1.md` §6.3.

    N'écrit QUE l'état du hold. La suspension des actions couvertes est produite par C5, jamais ici.
    """
    uc = 'PlaceHold'
    if not role_at_least(actor_role, 'MANAGER'):
        return _decision(uc, 'REFUSED', refusal='INSUFFICIENT_ROLE', audit=True)
    if not hold.reason:
        return _decision(uc, 'REFUSED', refusal='HOLD_REASON_REQUIRED', audit=True)
    if not _scope_consistent(hold):
        return _decision(uc, 'REFUSED', refusal='HOLD_TARGET_MISMATCH', audit=True)
    for h in holds:
        if (h.status == 'ACTIVE' and h.scope == hold.scope and h.invoice_id == hold.invoice_id
                and h.customer_id == hold.customer_id and h.automation_id == hold.automation_id
                and h.kind == hold.kind and _overlaps(h, hold)):
            return _decision(uc, 'REFUSED', refusal='HOLD_OVERLAP', audit=True)
    return _decision(uc, 'OK', transition=(None, 'ACTIVE'), audit=True,
                     events=('COLLECTION_HOLD_PLACED',), writes={'status': 'ACTIVE'})


def release_hold(hold, actor_role, release_reason, as_of):
    """B2 `ReleaseHold` — §9. La reprise des parcours appartient à l'Automation Engine (§11), pas ici (réserve R-9)."""
    uc = 'ReleaseHold'
    if not role_at_least(actor_role, 'MANAGER'):
        return _decision(uc, 'REFUSED', refusal='INSUFFICIENT_ROLE', audit=True)
    if hold.status != 'ACTIVE':
        return _decision(uc, 'REFUSED', refusal='HOLD_NOT_ACTIVE', audit=True)
    if not release_reason:
        return _decision(uc, 'REFUSED', refusal='HOLD_REASON_REQUIRED', audit=True)
    return _decision(uc, 'OK', transition=('ACTIVE', 'RELEASED'), audit=True,
                     events=('COLLECTION_HOLD_RELEASED',),
                     writes={'status': 'RELEASED', 'release_reason': release_reason, 'released_at': as_of},
                     reserves=('R-9 : effet local éventuel à la levée de la cause non énoncé par §11',))


def hold_expiry_scan(hold, as_of):
    """B3 `HoldExpiryScan` — §9 : MATÉRIALISE une expiration déjà effective dès `ends_at`. Aucun audit (temporel)."""
    uc = 'HoldExpiryScan'
    if hold.status != 'ACTIVE' or hold.ends_at is None or hold.ends_at > as_of:
        return _decision(uc, 'SKIPPED')
    return _decision(uc, 'OK', transition=('ACTIVE', 'EXPIRED'),
                     events=('COLLECTION_HOLD_RELEASED',), writes={'status': 'EXPIRED'})


def hold_in_force(hold, as_of):
    """§6.3 : un hold est hors vigueur dès `ends_at` dépassé, INDÉPENDAMMENT du passage du balayage."""
    if hold.status != 'ACTIVE':
        return False
    if hold.starts_at is not None and as_of < hold.starts_at:
        return False
    return hold.ends_at is None or as_of < hold.ends_at


# --------------------------------------------------------------------------- C1 à C7 : suppressions réactives

def hold_covers(hold, action):
    """Portée d'un hold appliquée à une action (§12 : « pour la portée du hold »)."""
    if hold.automation_id is not None:
        return False if hold.scope == 'ORGANIZATION' else True
    if hold.scope == 'INVOICE':
        return action.invoice_id == hold.invoice_id
    if hold.scope == 'CUSTOMER':
        return action.customer_id == hold.customer_id
    return True


def suppress_on_event(action, event, payload, facts, as_of, hold=None):
    """C1 à C7 — `COLLECTION_ENGINE_V1.md` §12.

    Forme commune : événement -> relire la cible -> condition -> `SUPPRESSED` ou no-op. Aucune évaluation de règle
    (DV4-6 ACCEPTÉ : l'événement EST la condition de l'exception L1). Portée fermée à
    `PROPOSED`/`SCHEDULED`/`PENDING_APPROVAL` : une action `EXECUTING` n'est JAMAIS supprimée par réaction (§15
    course 1) — c'est la revalidation d'A6 qui traite ce cas.
    """
    uc = 'SuppressOn:' + event
    if event not in SUPPRESSION_ON_EVENT:
        return _decision(uc, 'SKIPPED')
    if action.status not in SUPPRESSIBLE:
        return _decision(uc, 'SKIPPED')

    if event == 'INVOICE_DISPUTED' and facts.collectible_minor != 0:
        # C3, D1 : litige PARTIEL -> aucune suppression, le recouvrement continue sur le montant recouvrable
        return _decision(uc, 'SKIPPED')
    if event == 'PROMISE_CREATED':
        scoped_invoice = payload.get('invoice_id')
        if scoped_invoice is not None and action.invoice_id != scoped_invoice:
            return _decision(uc, 'SKIPPED')
        if scoped_invoice is None and action.customer_id != payload.get('customer_id'):
            return _decision(uc, 'SKIPPED')
    if event == 'COLLECTION_HOLD_PLACED':
        if hold is None or not hold_covers(hold, action):
            return _decision(uc, 'SKIPPED')
    if event in ('INVOICE_PAID', 'INVOICE_VOIDED', 'INVOICE_CANCELLED', 'INVOICE_DISPUTED'):
        if action.invoice_id != payload.get('invoice_id'):
            return _decision(uc, 'SKIPPED')
    if event in ('CUSTOMER_DEACTIVATED', 'CUSTOMER_ARCHIVED'):
        if action.customer_id != payload.get('customer_id'):
            return _decision(uc, 'SKIPPED')

    code = SUPPRESSION_ON_EVENT[event]
    return _decision(uc, 'PROCESSED', transition=(action.status, 'SUPPRESSED'), suppression=code,
                     events=('COLLECTION_ACTION_SUPPRESSED',),
                     writes={'status': 'SUPPRESSED', 'suppression_code': code})


# --------------------------------------------------------------------------- scénario de référence §11

#: Scénario de référence gelé, `COLLECTION_ENGINE_V1.md` §11 « test d'or de bout en bout ».
#: Les NIVEAUX y sont des valeurs REÇUES du Rule Engine (S1->1, S2->2, S3->3, S4->3, S5->4, S6->4 car
#: MEDIUM < HIGH) : l'oracle ne les recalcule jamais, il vérifie l'effet de la décision sur Collection.
GOLDEN_RULES = ReferenceOrgRules(
    comm_window_start=time(8, 0), comm_window_end=time(18, 0),
    business_weekdays=(0, 1, 2, 3, 4), holidays=frozenset(),
    send_hour=time(9, 0), max_customer_messages_per_day=2, send_rate_per_hour=200)

GOLDEN_INVOICE = {'invoice_id': 'INV-1', 'customer_id': 'CUS-1', 'total_minor': 500000,
                  'issued_on': date(2026, 9, 28), 'due_on': date(2026, 10, 15),
                  'risk_level': 'MEDIUM', 'critical_amount_minor': 1000000, 'due_soon_days': 7}

#: (étape, instant du déclencheur, niveau reçu, type, résultat attendu tel que §11 l'énonce)
GOLDEN_STEPS = (
    ('S1', datetime(2026, 10, 1, 7, 0), 1, 'REMINDER', datetime(2026, 10, 1, 9, 0)),
    ('S2', datetime(2026, 10, 8, 7, 0), 2, 'REMINDER', datetime(2026, 10, 8, 9, 0)),
    ('S3', datetime(2026, 10, 18, 7, 0), 3, 'REMINDER', datetime(2026, 10, 19, 9, 0)),
    ('S4', datetime(2026, 10, 25, 7, 0), 3, 'CALL_TASK', datetime(2026, 10, 26, 9, 0)),
    ('S5', datetime(2026, 10, 30, 7, 0), 4, 'ESCALATION', datetime(2026, 10, 30, 9, 0)),
)

#: §11 : à risque MEDIUM, S6 calcule le niveau 4, DÉJÀ ATTEINT par S5 -> même clé -> REPLAY, aucune action.
GOLDEN_S6 = ('S6', datetime(2026, 11, 14, 7, 0), 4, 'ESCALATION', 'REPLAY')

#: §11, variantes dérivées du même scénario.
GOLDEN_VARIANTS = (
    ('risk_high', 'S6 donne le niveau 5 si l\'exposition en retard atteint 1 000 000'),
    ('settled_2026_10_22', 'tout ce qui suit est SUPPRESSED (PAID) ou annulé'),
    ('promise_2026_10_20', 'S4 et S5 SUPPRESSED (PROMISE_ACTIVE)'),
)
