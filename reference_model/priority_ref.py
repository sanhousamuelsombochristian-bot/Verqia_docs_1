"""VERQIA : référence Priority (spécification exécutable), Domain V1 — tranche Priority (`prio-1.0`).

Règles de ce module (Priority Domain V1, même discipline que `risk_ref.py`) :
  * NAÏVE et INDÉPENDANTE : aucune importation de `verqia`, du Domain, de `verqia_models` ni de `risk_ref` ;
    bibliothèque standard seulement ; transcrite depuis `RISK_PRIORITY_CASHFLOW_V1.md` (§1.3, §3) et
    `PRIORITY_DOMAIN_V1.md` (PD1 à PD11, arbitrage DV3), JAMAIS depuis une future implémentation du Domain ;
  * arithmétique ENTIÈRE partout (RP-B) ; chaque division est nommée (`floor`) ; aucune horloge ;
  * couvre ce que `verqia_models.prio_evaluate` ne couvre pas : l'ÉLIGIBILITÉ À TROIS ÉTATS (PD3 : DRAFT / facture
    fermée / facture active), la DÉRIVATION de `dispute_no_collectible` depuis des faits bruts (PD7, § DV3-5, jamais
    reçue en paramètre nu), la DÉRIVATION de `overdue` depuis `is_late` (§ DV3-7), et la DÉCISION de publication
    (rien / élément seul / élément + `PRIORITY_CHANGED`, PD11) à travers une succession d'appels — jamais la formule
    de score elle-même, déjà indépendamment vérifiée (`verqia_models.py`, `golden_cases.json['priority']`, cas
    P1-P7). Les deux références sont volontairement redondantes sur la formule : c'est ce qui permet de détecter une
    erreur de transcription avant tout code.
"""

MODEL = 'prio-1.0'
LEVELS = ['NONE', 'WATCH', 'ACTION', 'PRIORITY', 'CRITICAL']
THRESHOLDS = [0, 20, 40, 60, 80]
MARGIN = 3                      # hystérésis : descente seulement si score + MARGIN reste sous le seuil courant (§1.3)
CAP_WATCH = 1                    # index de WATCH : plafond « promesse ou hold »
CAP_ACTION = 2                   # index de ACTION : plafond « litige sans recouvrable »
RISK_PTS = {'LOW': 0, 'MEDIUM': 8, 'HIGH': 17, 'CRITICAL': 25, None: 5}


# --------------------------------------------------------------------------- PD4 : barème (§3.3, transcrit)
def amount_points(A, C):
    """Montant, 0 à 30."""
    if C <= 0:
        return 0
    return min(30, (A * 30) // C)


def delay_points(Dd):
    """Retard, 0 à 30 — appelé seulement si `overdue` (§ DV3-7 : overdue = is_late)."""
    if Dd <= 0:
        return 0
    if Dd <= 7:
        return 8
    if Dd <= 15:
        return 16
    if Dd <= 30:
        return 24
    return 30


def due_points(Dj):
    """Échéance imminente, 0 à 5 — appelé seulement si NON `overdue`."""
    if 0 <= Dj <= 3:
        return 5
    if 4 <= Dj <= 7:
        return 2
    return 0


def attention_points(S):
    """Attention requise, 0 à 10 — appelé seulement si `overdue`. `None` : aucune action connue (PL3, S=Dd déjà appliqué par l'appelant)."""
    if S is None:
        return 0
    if S >= 10:
        return 10
    if S >= 5:
        return 5
    return 0


def points_of(A, C, overdue, Dd, Dj, risk_level, S):
    """RD4 : `overdue` détermine l'exclusion retard/échéance (§ DV3-7, dérivé de `is_late` par l'appelant, jamais recalculé ici)."""
    if overdue:
        delay_pts, due_pts, attention_pts = delay_points(Dd), 0, attention_points(S)
    else:
        delay_pts, due_pts, attention_pts = 0, due_points(Dj), 0
    return {'amount_pts': amount_points(A, C), 'delay_pts': delay_pts, 'risk_pts': RISK_PTS[risk_level],
            'due_pts': due_pts, 'attention_pts': attention_pts}


# --------------------------------------------------------------------------- PD5, PD6 : score et niveau brut
def rank_score(pts):
    return pts['amount_pts'] + pts['delay_pts'] + pts['risk_pts'] + pts['due_pts'] + pts['attention_pts']


def level_index(score, thresholds=THRESHOLDS):
    idx = 0
    for i, t in enumerate(thresholds):
        if score >= t:
            idx = i
    return idx


# --------------------------------------------------------------------------- PD7 : hystérésis puis plafonds (chaîne à 4 étapes, différente de Risk)
def stabilise(score, previous_level_index):
    """Montée immédiate ; descente seulement si `score + MARGIN` reste STRICTEMENT sous le seuil courant (même
    correction que RL10/Risk : `level_index` compare par `≥`, l'égalité `score+MARGIN == seuil` NE descend PAS)."""
    raw = level_index(score)
    if previous_level_index is None or raw >= previous_level_index:
        return raw
    return max(raw, level_index(score + MARGIN))


def apply_caps(stabilised_index, promise_or_hold, dispute_no_collectible):
    """§3.4 : le plus bas des plafonds actifs l'emporte (`min`) ; un plafond ne relève jamais un niveau."""
    cap = len(LEVELS) - 1
    caps = []
    if promise_or_hold:
        cap = min(cap, CAP_WATCH)
        caps.append('PROMISE_OR_HOLD')
    if dispute_no_collectible:
        cap = min(cap, CAP_ACTION)
        caps.append('DISPUTED')
    return min(stabilised_index, cap), caps


# --------------------------------------------------------------------------- PD10.1 : entrées normalisées
def normalized_inputs_of(pts, previous_level, cap_promise_or_hold, cap_dispute, reconciliation_pending):
    return dict(pts, previous_level=previous_level, cap_promise_or_hold=bool(cap_promise_or_hold),
               cap_dispute=bool(cap_dispute), reconciliation_pending=bool(reconciliation_pending))


def reasons_of(pts, caps, signals):
    """`{"factors": [...], "caps": [...], "signals": [...]}` ; `normalized_input` est la valeur normalisée
    (`"pts=N"`), jamais une valeur brute (RP14, même règle que Risk)."""
    order = ('amount_pts', 'delay_pts', 'risk_pts', 'due_pts', 'attention_pts')
    factors = [{'factor': k[:-4], 'points': pts[k], 'normalized_input': 'pts=%d' % pts[k]} for k in order]
    return {'factors': factors, 'caps': list(caps), 'signals': list(signals)}


# --------------------------------------------------------------------------- PD7/DV3-5, DV3-7 : dérivations du Domain (jamais reçues en paramètre nu)
def dispute_no_collectible_of(has_open_dispute, collectible_minor):
    """§ DV3-5 : dérivation, pas un fait persistant ni un paramètre d'entrée séparé."""
    return bool(has_open_dispute) and collectible_minor == 0


# --------------------------------------------------------------------------- PD3 : éligibilité à trois états
def eligibility_of(is_draft, is_open):
    """`'draft'` (aucun élément) · `'closed'` (élément NONE/CLOSED) · `'active'` (calcul complet)."""
    if is_draft:
        return 'draft'
    return 'closed' if not is_open else 'active'


def score_and_level(A, C, overdue, Dd, Dj, risk_level, S, previous_level, promise_or_hold, dispute_no_collectible):
    """Équivalent, pour la formule seule, de `verqia_models.prio_evaluate` — reproduit ici indépendamment."""
    pts = points_of(A, C, overdue, Dd, Dj, risk_level, S)
    score = rank_score(pts)
    prev_idx = LEVELS.index(previous_level) if previous_level is not None else None
    stabilised = stabilise(score, prev_idx)
    published_idx, caps = apply_caps(stabilised, promise_or_hold, dispute_no_collectible)
    return {'score': score, 'level': LEVELS[published_idx], 'caps': caps, 'pts': pts}


# --------------------------------------------------------------------------- PD11 : décision de publication
def evaluate_priority(previous, is_draft, is_open, critical_amount_minor, outstanding_minor, is_late, days_late,
                      days_to_due, collectible_minor, has_open_dispute, risk_level, days_since_last_action,
                      active_promise, hold_active, reconciliation_pending):
    """`previous` : `None`, ou `{'level': str, 'normalized_inputs': dict}` (PD2.5 — jamais un `input_hash`).
    Rend `{'eligible', 'is_closed', 'score', 'level', 'reasons', 'normalized_inputs', 'changed', 'event'}` ;
    `event` = `{'from_level','to_level','rank_score'}` seulement si le niveau publié change ET qu'un `previous`
    existait (§ PD11.2, même règle que Risk DV2-7)."""
    if is_draft:
        return {'eligible': False, 'is_closed': False, 'score': None, 'level': None, 'reasons': None,
                'normalized_inputs': None, 'changed': False, 'event': None}

    previous_level = previous['level'] if previous is not None else None

    if not is_open:
        pts = {'amount_pts': 0, 'delay_pts': 0, 'risk_pts': 0, 'due_pts': 0, 'attention_pts': 0}
        score, level = 0, 'NONE'
        ni = normalized_inputs_of(pts, previous_level, False, False, False)
        reasons = reasons_of(pts, [], [])
    else:
        overdue = bool(is_late)
        S = days_since_last_action if days_since_last_action is not None else days_late    # PD2.3/PL3
        dispute_no_collectible = dispute_no_collectible_of(has_open_dispute, collectible_minor)
        promise_or_hold = bool(active_promise) or bool(hold_active)
        out = score_and_level(outstanding_minor, critical_amount_minor, overdue, days_late, days_to_due, risk_level,
                              S, previous_level, promise_or_hold, dispute_no_collectible)
        score, level = out['score'], out['level']
        signals = ['RECONCILIATION_PENDING'] if reconciliation_pending else []
        ni = normalized_inputs_of(out['pts'], previous_level, promise_or_hold, dispute_no_collectible, reconciliation_pending)
        reasons = reasons_of(out['pts'], out['caps'], signals)

    changed = previous is None or ni != previous['normalized_inputs']
    event = None
    if changed and previous is not None and level != previous['level']:
        event = {'from_level': previous['level'], 'to_level': level, 'rank_score': score}
    return {'eligible': True, 'is_closed': not is_open, 'score': score, 'level': level, 'reasons': reasons,
            'normalized_inputs': ni, 'changed': changed, 'event': event}
