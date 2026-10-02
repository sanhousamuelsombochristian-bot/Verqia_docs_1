"""VERQIA : référence Risk (spécification exécutable), Domain V1 — tranche Risk (`risk-1.0`).

Règles de ce module (Risk Domain V1, RD17, même discipline que `finance_ref.py`, V8) :
  * NAÏVE et INDÉPENDANTE : aucune importation de `verqia`, du Domain, de `verqia_models` ni de `finance_ref` ; bibliothèque
    standard seulement ; transcrite depuis `RISK_PRIORITY_CASHFLOW_V1.md` (§1.2, §1.3, §2) et `RISK_DOMAIN_V1.md` (RD2 à RD11),
    JAMAIS depuis une future implémentation du Domain ;
  * arithmétique ENTIÈRE partout (RP-B) ; chaque division est nommée (`floor` ou demi vers le haut) ; aucune horloge ;
  * couvre ce que `verqia_models.risk_evaluate` ne couvre pas : l'ÉLIGIBILITÉ (RD3), l'AGRÉGATION depuis des listes de faits
    de factures/paiements/promesses (RD2.2), et la DÉCISION de publication (rien / profil seul / profil + `RISK_CHANGED`,
    RD11) à travers une succession d'appels — jamais la formule de score elle-même, déjà indépendamment vérifiée
    (`verqia_models.py`, `golden_cases.json['risk']`, 25 tests). Les deux réfèrences sont volontairement redondantes sur la
    formule (G1 à G5, testé ici aussi) : c'est ce qui permet de détecter une erreur de transcription avant tout code.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

MODEL = 'risk-1.0'
LEVELS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
THRESHOLDS = [0, 25, 50, 75]
MARGIN = 3                      # hystérésis : descente seulement si score + MARGIN reste sous le seuil courant (§1.3)
MIN_SAMPLE = 3                  # RP-G : échantillon minimal pour n, sinon L et M inconnus


# --------------------------------------------------------------------------- calendrier (K20, copie indépendante, cf. finance_ref.business_date)
def business_date(instant, tz_name):
    if instant.tzinfo is None:
        raise ValueError('instant naïf refusé')
    return instant.astimezone(ZoneInfo(tz_name)).date()


# --------------------------------------------------------------------------- RD4 : normalisation des facts (barème §2.3, transcrit)
def delay_points(D):
    """Retard actuel, 0 à 30."""
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


def history_points(n, L, M):
    """Historique de retard, 0 à 25 (deux composantes : late_pts <=15, delay_pts <=10). `L` en pour-mille, `M` en jours, non plafonné en entrée."""
    if n < MIN_SAMPLE:
        return 0, 0
    late_pts = (L * 15) // 1000
    delay_pts = (min(max(M, 0), 30) * 10) // 30
    return late_pts, delay_pts


def broken_points(B):
    return min(15, 5 * B)


def exposure_points(Eo, C):
    if C <= 0:
        return 0
    return min(15, (Eo * 15) // C)


def reversed_points(R):
    return min(10, 5 * R)


def trend_points(T):
    """`T` : jours, ou `None` si inconnu (RD15 RL6, indépendant de `confidence`)."""
    if T is None or T <= 0:
        return 0
    return min(5, (T * 5) // 10)


def confidence_of(n):
    return 'HIGH' if n >= MIN_SAMPLE else 'LOW'


# --------------------------------------------------------------------------- RD5, RD6 : score et niveau brut
def risk_score(pts):
    return (pts['delay_pts'] + pts['history_late_pts'] + pts['history_delay_pts'] + pts['broken_pts']
            + pts['exposure_pts'] + pts['reversed_pts'] + pts['trend_pts'])


def level_index(score, thresholds=THRESHOLDS):
    idx = 0
    for i, t in enumerate(thresholds):
        if score >= t:
            idx = i
    return idx


# --------------------------------------------------------------------------- RD7, RD8 : hystérésis et chaîne de stabilisation (aucun plafond pour Risk)
def stabilise(score, previous_level_index):
    """`previous_level_index` : indice du niveau PUBLIÉ précédent, ou `None` au premier calcul."""
    raw = level_index(score)
    if previous_level_index is None or raw >= previous_level_index:
        return raw
    return max(raw, level_index(score + MARGIN))


# --------------------------------------------------------------------------- points -> facteurs explicables (RD10.1, RD4)
def points_of(D, n, L, M, B, Eo, C, R, T):
    late_pts, delay_pts = history_points(n, L, M)
    return {
        'delay_pts': delay_points(D), 'history_late_pts': late_pts, 'history_delay_pts': delay_pts,
        'broken_pts': broken_points(B), 'exposure_pts': exposure_points(Eo, C),
        'reversed_pts': reversed_points(R), 'trend_pts': trend_points(T),
    }


def factors_of(pts, confidence):
    """`{"factors": [...], "meta": {"confidence"}}` (Data Contract §7.1) : `normalized_input` est la valeur NORMALISÉE
    (`"pts=20"`, `"late=11;delay=6"`), jamais une valeur brute (RP14) ; RD10.1/RD10.2."""
    rows = [
        ('delay', pts['delay_pts'], 30, 'pts=%d' % pts['delay_pts']),
        ('history', pts['history_late_pts'] + pts['history_delay_pts'], 25, 'late=%d;delay=%d' % (pts['history_late_pts'], pts['history_delay_pts'])),
        ('broken_promises', pts['broken_pts'], 15, 'pts=%d' % pts['broken_pts']),
        ('exposure', pts['exposure_pts'], 15, 'pts=%d' % pts['exposure_pts']),
        ('reversed_payments', pts['reversed_pts'], 10, 'pts=%d' % pts['reversed_pts']),
        ('trend', pts['trend_pts'], 5, 'pts=%d' % pts['trend_pts']),
    ]
    return {'factors': [{'factor': f, 'max': m, 'normalized_input': ni, 'points': p} for f, p, m, ni in rows], 'meta': {'confidence': confidence}}


def normalized_inputs_of(pts, confidence, previous_level):
    """RD10.1 : le septuplet que le Domain compare PAR VALEUR (jamais de hachage ici non plus, § DV2-8)."""
    return dict(pts, confidence=confidence, previous_level=previous_level)


def score_and_level(D, n, L, M, B, Eo, C, R, T, previous_level):
    """Équivalent, pour la formule seule, de `verqia_models.risk_evaluate` — reproduit ici indépendamment (RD17)."""
    pts = points_of(D, n, L, M, B, Eo, C, R, T)
    score = risk_score(pts)
    prev_idx = LEVELS.index(previous_level) if previous_level is not None else None
    level = LEVELS[stabilise(score, prev_idx)]
    confidence = confidence_of(n)
    return {'score': score, 'level': level, 'factors': factors_of(pts, confidence),
            'normalized_inputs': normalized_inputs_of(pts, confidence, previous_level)}


# --------------------------------------------------------------------------- RD2.2 : agrégation depuis des listes de faits (LA partie nouvelle de cette tranche)
# Chaque facture est un dict minimal : {'is_open', 'is_late', 'days_late', 'outstanding_minor', 'settlement_delay_days'}.
# `settlement_delay_days` (settled_on - due_date, en jours, PEUT être négatif) n'existe que pour les factures soldées.
def aggregate_D_Eo(open_invoices):
    late = [inv for inv in open_invoices if inv['is_open'] and inv['is_late']]
    D = max((inv['days_late'] for inv in late), default=0)
    Eo = sum(inv['outstanding_minor'] for inv in late)
    return D, Eo


def avg_days_to_pay(delays):
    """`⌊(2×S + n) / (2×n)⌋`, demi vers le haut, valeurs négatives permises (Rule Engine §5). `None` si `delays` est vide."""
    n = len(delays)
    if n == 0:
        return None
    S = sum(delays)
    return (2 * S + n) // (2 * n)


def aggregate_n_L_M(settled_invoices_12m):
    """`n`, `L` (pour-mille, `None` si `n < 3`), `M` (non plafonné, `None` si `n < 3`)."""
    n = len(settled_invoices_12m)
    if n < MIN_SAMPLE:
        return n, None, None
    delays = [inv['settlement_delay_days'] for inv in settled_invoices_12m]
    late_count = sum(1 for d in delays if d > 0)
    L = (1000 * late_count) // n
    M = avg_days_to_pay(delays)
    return n, L, M


def aggregate_T(settled_invoices_12m, today):
    """Tendance du délai : délai moyen des 90 derniers jours moins celui des 90 jours précédents ; `None` si l'une des deux
    fenêtres a moins de 2 factures soldées (indépendant de `n < 3`, RD15 RL6)."""
    recent = [inv['settlement_delay_days'] for inv in settled_invoices_12m if 0 <= (today - inv['settled_on']).days <= 90]
    prior = [inv['settlement_delay_days'] for inv in settled_invoices_12m if 91 <= (today - inv['settled_on']).days <= 180]
    if len(recent) < 2 or len(prior) < 2:
        return None
    return avg_days_to_pay(recent) - avg_days_to_pay(prior)


def aggregate_B(promise_facts):
    return len(promise_facts)


def aggregate_R(reversed_payments):
    return len(reversed_payments)


# --------------------------------------------------------------------------- RD3 : éligibilité
def is_eligible(has_ever_issued):
    """Transcrit de §2.1 : ni `bool(open_invoices)` ni `bool(settled_invoices_12m)` seuls ne suffisent (RD3) ; `has_ever_issued`
    est le seul signal correct, fourni tel quel."""
    return bool(has_ever_issued)


# --------------------------------------------------------------------------- RD11 : décision de publication (rien / profil seul / profil + RISK_CHANGED)
def evaluate_risk(previous, risk_parameters, has_ever_issued, open_invoices, settled_invoices_12m,
                  reversed_payments, promise_facts, as_of):
    """`previous` : `None`, ou `{'level': str, 'normalized_inputs': dict}` (RD2.5 — jamais un `input_hash`).
    Rend `{'eligible', 'score', 'level', 'factors', 'normalized_inputs', 'changed', 'event'}` ; `event` = `{'from_level','to_level','score'}`
    seulement si le niveau publié change ET qu'un `previous` existait (§ DV2-7)."""
    if not is_eligible(has_ever_issued):
        return {'eligible': False, 'score': None, 'level': None, 'factors': None, 'normalized_inputs': None, 'changed': False, 'event': None}

    today = business_date(as_of, risk_parameters['timezone'])
    D, Eo = aggregate_D_Eo(open_invoices)
    n, L, M = aggregate_n_L_M(settled_invoices_12m)
    T = aggregate_T(settled_invoices_12m, today)
    B = aggregate_B(promise_facts)
    R = aggregate_R(reversed_payments)
    C = risk_parameters['critical_amount_minor']
    previous_level = previous['level'] if previous is not None else None

    out = score_and_level(D, n, L, M, B, Eo, C, R, T, previous_level)
    changed = previous is None or out['normalized_inputs'] != previous['normalized_inputs']
    event = None
    if changed and previous is not None and out['level'] != previous['level']:
        event = {'from_level': previous['level'], 'to_level': out['level'], 'score': out['score']}
    return {'eligible': True, 'score': out['score'], 'level': out['level'], 'factors': out['factors'],
            'normalized_inputs': out['normalized_inputs'], 'changed': changed, 'event': event}
