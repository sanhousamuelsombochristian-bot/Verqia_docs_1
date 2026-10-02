"""VERQIA : modèles de référence (spécification exécutable).

risk-1.0 · prio-1.0 · cash-1.0

Règles de ce module :
  * arithmétique ENTIÈRE uniquement (aucun flottant) ; toute division est explicite (floor ou demi-vers-le-haut) ;
  * aucune lecture de l'horloge : `as_of` est toujours un paramètre ;
  * toute sortie persistée est dérivée UNIQUEMENT des entrées normalisées et de la version du modèle.
"""
import hashlib
import json
from datetime import date, timedelta

# --------------------------------------------------------------------------- outils entiers


def round_half_up_div(n, d):
    """Division entière arrondie au plus proche, demi vers le haut, valable aussi pour n < 0 (d > 0)."""
    return (2 * n + d) // (2 * d)


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def input_hash(model_version, organization_id, subject, normalized_inputs):
    payload = {'model': model_version, 'org': organization_id, 'subject': subject, 'inputs': normalized_inputs}
    return hashlib.sha256(canonical_json(payload).encode('utf-8')).hexdigest()


# --------------------------------------------------------------------------- niveaux et hystérésis
HYST_MARGIN = 3


def level_index(score, thresholds):
    idx = 0
    for i, t in enumerate(thresholds):
        if score >= t:
            idx = i
    return idx


def stabilise(score, previous_published, thresholds, margin=HYST_MARGIN):
    """Montée immédiate ; descente seulement si score + marge franchit encore le seuil du niveau courant."""
    raw = level_index(score, thresholds)
    if previous_published is None or raw >= previous_published:
        return raw
    return max(raw, level_index(score + margin, thresholds))


# --------------------------------------------------------------------------- RISK  (risk-1.0)
RISK_MODEL = 'risk-1.0'
RISK_LEVELS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
RISK_THRESHOLDS = [0, 25, 50, 75]
MIN_SAMPLE = 3


def _delay_points(D):
    if D <= 0:
        return 0
    if D <= 7:
        return 5
    if D <= 15:
        return 12
    if D <= 30:
        return 20
    if D <= 60:
        return 26
    return 30


def risk_points(D, n, late_permille, avg_delay, B, Eo, C, R, T):
    """Retourne les points par facteur (entiers) et la confiance."""
    has_hist = n >= MIN_SAMPLE
    late_pts = (late_permille * 15) // 1000 if has_hist else 0
    delay_pts = (min(max(avg_delay, 0), 30) * 10) // 30 if has_hist else 0
    pts = {
        'delay_pts': _delay_points(D),
        'history_late_pts': late_pts,
        'history_delay_pts': delay_pts,
        'broken_pts': min(15, 5 * B),
        'exposure_pts': min(15, (Eo * 15) // C) if C > 0 else 0,
        'reversed_pts': min(10, 5 * R),
        'trend_pts': min(5, (T * 5) // 10) if (T is not None and T > 0) else 0,
    }
    pts['confidence'] = 'HIGH' if has_hist else 'LOW'
    return pts


def risk_score(pts):
    return (pts['delay_pts'] + pts['history_late_pts'] + pts['history_delay_pts'] + pts['broken_pts']
            + pts['exposure_pts'] + pts['reversed_pts'] + pts['trend_pts'])


def risk_evaluate(organization_id, customer_id, previous_level, *inputs):
    """previous_level : niveau PUBLIÉ précédent (0..3) ou None. Retourne le profil déterministe."""
    pts = risk_points(*inputs)
    score = risk_score(pts)
    level = stabilise(score, previous_level, RISK_THRESHOLDS)
    normalized = dict(pts)
    normalized['previous_level'] = previous_level
    return {
        'score': score,
        'level': RISK_LEVELS[level],
        'level_index': level,
        'factors': {
            'factors': [
                {'factor': 'delay', 'normalized_input': 'pts=%d' % pts['delay_pts'], 'points': pts['delay_pts'], 'max': 30},
                {'factor': 'history', 'normalized_input': 'late=%d;delay=%d' % (pts['history_late_pts'], pts['history_delay_pts']),
                 'points': pts['history_late_pts'] + pts['history_delay_pts'], 'max': 25},
                {'factor': 'broken_promises', 'normalized_input': 'pts=%d' % pts['broken_pts'], 'points': pts['broken_pts'], 'max': 15},
                {'factor': 'exposure', 'normalized_input': 'pts=%d' % pts['exposure_pts'], 'points': pts['exposure_pts'], 'max': 15},
                {'factor': 'reversed_payments', 'normalized_input': 'pts=%d' % pts['reversed_pts'], 'points': pts['reversed_pts'], 'max': 10},
                {'factor': 'trend', 'normalized_input': 'pts=%d' % pts['trend_pts'], 'points': pts['trend_pts'], 'max': 5},
            ],
            'meta': {'confidence': pts['confidence']},
        },
        'input_hash': input_hash(RISK_MODEL, organization_id, customer_id, normalized),
    }


# --------------------------------------------------------------------------- PRIORITY (prio-1.0)
PRIO_MODEL = 'prio-1.0'
PRIO_LEVELS = ['NONE', 'WATCH', 'ACTION', 'PRIORITY', 'CRITICAL']
PRIO_THRESHOLDS = [0, 20, 40, 60, 80]
PRIO_MAX_SCORE = 95            # domaine atteignable de prio-1.0 ; le stockage (0..100) reste plus large
RISK_PTS = {'LOW': 0, 'MEDIUM': 8, 'HIGH': 17, 'CRITICAL': 25, None: 5}
CAP_WATCH = 1
CAP_ACTION = 2


def _prio_delay(Dd):
    if Dd <= 0:
        return 0
    if Dd <= 7:
        return 8
    if Dd <= 15:
        return 16
    if Dd <= 30:
        return 24
    return 30


def prio_points(A, C, Dd, Dj, risk_level, since_action, overdue):
    p_amount = min(30, (A * 30) // C) if C > 0 else 0
    if not overdue and 0 <= Dj <= 3:
        p_due = 5
    elif not overdue and 4 <= Dj <= 7:
        p_due = 2
    else:
        p_due = 0
    if overdue and since_action is not None and since_action >= 10:
        p_att = 10
    elif overdue and since_action is not None and since_action >= 5:
        p_att = 5
    else:
        p_att = 0
    return {'amount_pts': p_amount, 'delay_pts': _prio_delay(Dd) if overdue else 0, 'risk_pts': RISK_PTS[risk_level],
            'due_pts': p_due, 'attention_pts': p_att}


def prio_score(pts):
    return sum(pts.values())


def prio_publish(score, previous_published, promise_or_hold, dispute_no_collectible):
    """Chaîne normative : score -> niveau brut -> hystérésis (sur le niveau PUBLIÉ précédent) -> plafond -> niveau publié."""
    stabilised = stabilise(score, previous_published, PRIO_THRESHOLDS)
    cap = len(PRIO_LEVELS) - 1
    caps_applied = []
    if promise_or_hold:
        cap = min(cap, CAP_WATCH)
        caps_applied.append('PROMISE_OR_HOLD')
    if dispute_no_collectible:
        cap = min(cap, CAP_ACTION)
        caps_applied.append('DISPUTED')
    return min(stabilised, cap), caps_applied


def prio_evaluate(organization_id, invoice_id, previous_published, A, C, Dd, Dj, risk_level, since_action, overdue,
                  promise_or_hold=False, dispute_no_collectible=False, reconciliation_pending=False):
    """reconciliation_pending (RP23) : signal explicatif (paiement reçu non alloué). Il fait partie des entrées
    normalisées (donc du hash et de `reasons`) mais ne modifie NI le score NI le niveau."""
    pts = prio_points(A, C, Dd, Dj, risk_level, since_action, overdue)
    score = prio_score(pts)
    level, caps = prio_publish(score, previous_published, promise_or_hold, dispute_no_collectible)
    normalized = dict(pts)
    normalized.update({'previous_level': previous_published, 'cap_promise_or_hold': bool(promise_or_hold),
                       'cap_dispute': bool(dispute_no_collectible), 'reconciliation_pending': bool(reconciliation_pending)})
    reasons = [{'factor': k[:-4], 'normalized_input': 'pts=%d' % v, 'points': v} for k, v in pts.items()]
    signals = ['RECONCILIATION_PENDING'] if reconciliation_pending else []
    return {'rank_score': score, 'level': PRIO_LEVELS[level], 'level_index': level, 'caps': caps, 'signals': signals,
            'reasons': {'factors': reasons, 'caps': caps, 'signals': signals},
            'input_hash': input_hash(PRIO_MODEL, organization_id, invoice_id, normalized)}


# --------------------------------------------------------------------------- CASHFLOW (cash-1.0)
CASH_MODEL = 'cash-1.0'
P_RISK_BP = {'LOW': 9700, 'MEDIUM': 9000, 'HIGH': 7500, 'CRITICAL': 5000, None: 8500}
SCEN_ADJ_BP = {'BASE': 0, 'OPTIMISTIC': 500, 'PESSIMISTIC': -1500}
OVERDUE_SHIFT = {'BASE': 7, 'OPTIMISTIC': 3, 'PESSIMISTIC': 14}


def decay_bp(days_overdue):
    if days_overdue <= 15:
        return 10000
    if days_overdue <= 30:
        return 9000
    if days_overdue <= 60:
        return 7500
    if days_overdue <= 90:
        return 5500
    return 3500


def scenario_delay(d, scenario):
    if scenario == 'BASE':
        return d
    if scenario == 'OPTIMISTIC':
        return d // 2
    return d + d // 2 + 7


def probability_bp(risk_level, scenario, days_overdue):
    """base = clamp(P_risque + ajustement, 1000, 10000) ; p = floor(base * décote / 10000)."""
    base = max(1000, min(10000, P_RISK_BP[risk_level] + SCEN_ADJ_BP[scenario]))
    return (base * decay_bp(max(days_overdue, 0))) // 10000


def weighted(amount, p_bp):
    """weighted = floor((amount * p + 5000) / 10000)  ==  round-half-up(amount * p / 10000) pour amount >= 0."""
    return (amount * p_bp + 5000) // 10000


def reserve_unallocated(invoices, unallocated):
    """Réserve de la trésorerie déjà reçue mais non allouée, en FIFO (échéance croissante, puis identifiant).
    Elle réduit d'abord la part recouvrable, puis la part contestée. Retourne {id: (collectible, disputed, reserved)}."""
    out = {}
    remaining = max(0, unallocated)
    for inv in sorted(invoices, key=lambda i: (i['due'], i['id'])):
        disp = min(inv.get('disputed', 0), inv['outstanding'])
        coll = inv['outstanding'] - disp
        r1 = min(remaining, coll)
        coll -= r1
        remaining -= r1
        r2 = min(remaining, disp)
        disp -= r2
        remaining -= r2
        out[inv['id']] = (coll, disp, r1 + r2)
    return out


def invoice_lines(as_of, horizon, scenario, inv, collectible, disputed, risk_level, d_cust, promise=None, broken=0):
    """Lignes prévisionnelles d'une facture (jamais de REALIZED)."""
    end = as_of + timedelta(days=horizon)
    due = inv['due']
    overdue = due < as_of
    dod = (as_of - due).days if overdue else 0
    p = probability_bp(risk_level, scenario, dod)
    lines = []
    if disputed > 0:
        lines.append({'invoice': inv['id'], 'category': 'AT_RISK', 'amount': disputed, 'p_bp': p // 2, 'date': None,
                      'basis': 'DISPUTED_PORTION'})
    rest = collectible
    if promise and rest > 0:
        pdate, pamount = promise
        if as_of <= pdate <= end:
            amt = min(pamount, rest)
            lines.append({'invoice': inv['id'], 'category': 'PROBABLE', 'amount': amt,
                          'p_bp': max(3000, 8000 - 1500 * broken), 'date': pdate, 'basis': 'PROMISE'})
            rest -= amt
    if rest > 0:
        t = due + timedelta(days=scenario_delay(d_cust, scenario))
        if overdue and t <= as_of:
            t = as_of + timedelta(days=OVERDUE_SHIFT[scenario])
        if overdue and (risk_level == 'CRITICAL' or dod > 60):
            lines.append({'invoice': inv['id'], 'category': 'AT_RISK', 'amount': rest, 'p_bp': p, 'date': None,
                          'basis': 'OVERDUE_RISK'})
        elif t <= end:
            lines.append({'invoice': inv['id'], 'category': 'PROBABLE' if overdue else 'EXPECTED', 'amount': rest,
                          'p_bp': p, 'date': t, 'basis': 'DUE_DATE_PLUS_DELAY'})
    for ln in lines:
        ln['weighted'] = weighted(ln['amount'], ln['p_bp'])
    return lines


def customer_forecast(as_of, horizon, scenario, invoices, unallocated, risk_level, d_cust, promises=None, broken=0):
    """Prévision d'un client : réserve du non-alloué (FIFO), puis lignes par facture.
    invoices : liste de dict(id, due, outstanding, disputed) ; promises : {invoice_id: (date, montant)}."""
    promises = promises or {}
    res = reserve_unallocated(invoices, unallocated)
    lines = []
    for inv in sorted(invoices, key=lambda i: (i['due'], i['id'])):
        coll, disp, _ = res[inv['id']]
        lines += invoice_lines(as_of, horizon, scenario, inv, coll, disp, risk_level, d_cust, promises.get(inv['id']), broken)
    return lines, sum(v[2] for v in res.values())


def promote_current(current, candidate):
    """Promotion monotone d'un run en run courant : jamais un run plus ancien ne remplace un plus récent.
    current / candidate : (as_of, computed_at) ; current peut être None."""
    if candidate is None:
        return False
    if current is None:
        return True
    return candidate > current


# --------------------------------------------------------------------------- RAPPROCHEMENT (Collection V1.2, RP23)
# Un paiement reçu mais non alloué est un signal de rapprochement à résoudre, jamais une conclusion « facture payée ».
# Cashflow PRÉSUME (réserve FIFO) pour prévoir avec prudence ; Collection NE PRÉSUME PAS pour agir : elle suspend
# toutes les factures candidates, pendant une fenêtre bornée en jours ouvrés.
RECON_HOLD_BUSINESS_DAYS = 3      # fenêtre de suspension (org_settings.extra.reconciliation_hold_business_days)
RECON_REVIEW_AFTER_BUSINESS_DAYS = 1
UNALLOCATED_STATUSES = ('RECEIVED', 'PARTIALLY_ALLOCATED')
DEFAULT_WEEKDAYS = frozenset({1, 2, 3, 4, 5})


def is_business_day(d, weekdays=DEFAULT_WEEKDAYS, holidays=frozenset()):
    return d.isoweekday() in weekdays and d not in holidays


def add_business_days(d, n, weekdays=DEFAULT_WEEKDAYS, holidays=frozenset()):
    cur, k = d, 0
    while k < n:
        cur += timedelta(days=1)
        if is_business_day(cur, weekdays, holidays):
            k += 1
    return cur


def unallocated_of(payment):
    return max(0, payment['amount'] - payment['allocated'])


def payment_qualifies(payment, invoice):
    """Q1 à Q4 (Q5, la fenêtre, dépend de la date) : non alloué > 0, non annulé, même client et même devise,
    facture ouverte, facture émise au plus tard à la date de valeur du paiement."""
    return (payment['status'] in UNALLOCATED_STATUSES and unallocated_of(payment) > 0
            and payment['customer'] == invoice['customer'] and payment['currency'] == invoice['currency']
            and invoice['is_open'] and payment['value_date'] >= invoice['issue_date'])


def window_last_day(payment, n=RECON_HOLD_BUSINESS_DAYS, weekdays=DEFAULT_WEEKDAYS, holidays=frozenset()):
    """Dernier jour (inclus) de suspension : n jours ouvrés après la date d'ENREGISTREMENT du paiement (`created_at`)."""
    return add_business_days(payment['recorded'], n, weekdays, holidays)


def reconciliation_state(invoice, payments, as_of, n=RECON_HOLD_BUSINESS_DAYS, weekdays=DEFAULT_WEEKDAYS, holidays=frozenset()):
    """Fait `invoice.reconciliation_pending` et ses compléments, pour une date `as_of` (fuseau de l'organisation)."""
    active, stale, review_due = [], [], []
    for p in payments:
        if not payment_qualifies(p, invoice):
            continue
        if as_of <= window_last_day(p, n, weekdays, holidays):
            active.append(p['id'])
            if as_of >= add_business_days(p['recorded'], RECON_REVIEW_AFTER_BUSINESS_DAYS, weekdays, holidays):
                review_due.append(p['id'])
        else:
            stale.append(p['id'])
    by_id = {p['id']: p for p in payments}
    return {
        'pending': bool(active),
        'pending_minor': sum(unallocated_of(by_id[i]) for i in active),
        'payments': sorted(active),
        'review_due': sorted(review_due),
        'stale': sorted(stale),
    }


# --- Instants et fuseau (RN5) : la décision ne dépend JAMAIS de l'heure d'exécution d'un job.
# La date d'enregistrement et la date d'évaluation sont des DATES LOCALES de l'organisation ; la fenêtre se compte en jours
# ouvrés du calendrier de l'organisation. La barrière est active jusqu'à la FIN du dernier jour de suspension (heure locale)
# et périmée (`stale`) dès le jour local suivant.
def local_date(instant_utc, tz):
    """Date locale (fuseau de l'organisation) d'un instant. `instant_utc` doit être « aware »."""
    if instant_utc.tzinfo is None:
        raise ValueError('instant naïf refusé : tout instant est horodaté (UTC)')
    return instant_utc.astimezone(tz).date()


def reconciliation_state_at(invoice, payments, now_utc, tz, n=RECON_HOLD_BUSINESS_DAYS, weekdays=DEFAULT_WEEKDAYS, holidays=frozenset()):
    """Même fait que `reconciliation_state`, à partir d'INSTANTS : `payments[i]['created_at']` et `now_utc`.
    Le résultat est identique pour tous les instants d'un même jour local."""
    pays = [dict(p, recorded=local_date(p['created_at'], tz)) for p in payments]
    return reconciliation_state(invoice, pays, local_date(now_utc, tz), n, weekdays, holidays)


def barrier_lifted_at(payment_created_at, tz, n=RECON_HOLD_BUSINESS_DAYS, weekdays=DEFAULT_WEEKDAYS, holidays=frozenset()):
    """Premier instant (UTC) où la barrière de ce paiement n'existe plus : minuit local qui suit le dernier jour de suspension."""
    from datetime import datetime, time, timezone
    last = add_business_days(local_date(payment_created_at, tz), n, weekdays, holidays)
    return datetime.combine(last + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)

