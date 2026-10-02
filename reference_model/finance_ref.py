"""VERQIA : référence financière (spécification exécutable), tranche Facture / Échéance / Paiement.

Règles de ce module (Domain V1, tranche 1, §9 et V8) :
  * NAÏVE et INDÉPENDANTE : aucune importation de `verqia`, du Domain ni de `verqia_models` ; bibliothèque standard seulement ;
  * arithmétique ENTIÈRE ; aucune horloge : « aujourd'hui » est toujours un paramètre ;
  * chaque fonction transcrit UN texte gelé (State Machines, Invariants, Data Contract) de la manière la plus évidente, même si le Domain
    l'implémentera autrement (par sauts, par différences, par tables) : c'est ce qui rend la comparaison différentielle utile ;
  * les refus rendent le CODE du catalogue, dans l'ordre de précédence de la §7.1 du document du Domain.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

LIFECYCLE_ORDER = ['ISSUED', 'DUE_SOON', 'DUE', 'OVERDUE']
PAYABLE = frozenset(LIFECYCLE_ORDER)


# --------------------------------------------------------------------------- montants, lignes, règlement
def line_total(quantity_e4, unit_price_minor):
    """`round(quantity * prix)` avec la quantité en dix-millièmes : demi vers le haut, valeurs >= 0."""
    assert quantity_e4 > 0 and unit_price_minor >= 0
    return (quantity_e4 * unit_price_minor + 5000) // 10000


def settlement_of(paid, total):
    """Data Contract §3.1, trois branches exclusives."""
    if paid == 0:
        return 'UNPAID'
    if 0 < paid < total:
        return 'PARTIALLY_PAID'
    if paid == total and total > 0:
        return 'PAID'
    raise ValueError('règlement impossible : paid=%d total=%d' % (paid, total))


def payment_status_of(amount, allocated, reversed_):
    """Data Contract §4.1 : hors `REVERSED`, fonction de `allocated`."""
    if reversed_:
        assert allocated == 0
        return 'REVERSED'
    if allocated == 0:
        return 'RECEIVED'
    if allocated < amount:
        return 'PARTIALLY_ALLOCATED'
    assert allocated == amount
    return 'ALLOCATED'


def outstanding_of(total, paid):
    return total - paid


# --------------------------------------------------------------------------- temps et échéance
def business_date(instant, tz_name):
    """Date locale de l'organisation (K20, C10). L'instant est obligatoirement horodaté."""
    if instant.tzinfo is None:
        raise ValueError('instant naïf refusé')
    return instant.astimezone(ZoneInfo(tz_name)).date()


def days_to_due(due, today):
    return (due - today).days


def position_of(due, today, due_soon_days):
    """Position d'échéance du jour : la garde vraie la plus avancée (State Machines §3, sauts permis)."""
    d = days_to_due(due, today)
    if d < 0:
        return 'OVERDUE'
    if d == 0:
        return 'DUE'
    if d <= due_soon_days:
        return 'DUE_SOON'
    return 'NOT_YET'


def days_late(due, today):
    return max(0, (today - due).days)


def is_late(due, today):
    return today > due


# --------------------------------------------------------------------------- litige (D1 verrouillé)
def collectible_of(outstanding, dispute):
    """`dispute` : None (aucun litige OPEN) ou {'amount': None | int}."""
    if dispute is None:
        return outstanding
    if dispute['amount'] is None:
        return 0
    return max(outstanding - dispute['amount'], 0)


def disputed_part_of(outstanding, dispute):
    """Part contestée d'un litige OPEN, telle que la Prévision la lit (`min(montant, dû)`)."""
    if dispute is None:
        return 0
    if dispute['amount'] is None:
        return outstanding
    return min(dispute['amount'], outstanding)


# --------------------------------------------------------------------------- registre d'allocations
# une ligne : {'id', 'payment', 'invoice', 'amount' (signé), 'reverses' (id de l'origine ou None)}
def net_to_invoice(ledger, invoice):
    return sum(r['amount'] for r in ledger if r['invoice'] == invoice)


def net_of_payment(ledger, payment):
    return sum(r['amount'] for r in ledger if r['payment'] == payment)


def net_of_payment_to_invoice(ledger, payment, invoice):
    return sum(r['amount'] for r in ledger if r['payment'] == payment and r['invoice'] == invoice)


def reversible_of(ledger, allocation_id):
    """Reliquat reversable d'une ligne : origine + reversals liés ; 0 pour une ligne négative."""
    row = [r for r in ledger if r['id'] == allocation_id][0]
    if row['amount'] <= 0:
        return 0
    return row['amount'] + sum(r['amount'] for r in ledger if r['reverses'] == allocation_id)


def active_allocations(ledger, payment):
    return [r for r in ledger if r['payment'] == payment and r['amount'] > 0 and reversible_of(ledger, r['id']) > 0]


def settled_on_of(ledger, invoice, value_dates, total):
    """DD11 (V7) : date de valeur la plus tardive parmi les paiements dont la contribution nette est positive, si la facture est soldée.
    Indépendante de l'ordre dans lequel les allocations ont été passées."""
    if total == 0 or net_to_invoice(ledger, invoice) != total:
        return None
    payments = {r['payment'] for r in ledger if r['invoice'] == invoice}
    return max(value_dates[p] for p in payments if net_of_payment_to_invoice(ledger, p, invoice) > 0)


def payment_available(amount, allocated, status):
    return 0 if status == 'REVERSED' else amount - allocated


# --------------------------------------------------------------------------- cycle de vie d'une facture (simulation évidente)
def new_invoice(total, issue, due):
    return {'lifecycle': 'DRAFT', 'settlement': 'UNPAID', 'paid': 0, 'total': total, 'issue': issue, 'due': due, 'settled_on': None,
            'cycle': 0, 'ledger': [], 'value_dates': {}, 'events': [], 'outcomes': []}


def _forward(inv, today, dsd, day):
    """Applique la position du jour, seulement en avant, une transition, un événement."""
    pos = position_of(inv['due'], today, dsd)
    if pos == 'NOT_YET':
        return
    if LIFECYCLE_ORDER.index(pos) > LIFECYCLE_ORDER.index(inv['lifecycle']):
        inv['lifecycle'] = pos
        inv['events'].append([day, 'INVOICE_' + pos])
        if pos == 'OVERDUE':
            inv['cycle'] += 1


def op_issue(inv, today, dsd, day):
    assert inv['lifecycle'] == 'DRAFT'
    inv['lifecycle'] = 'ISSUED'
    inv['events'].append([day, 'INVOICE_ISSUED'])
    _forward(inv, today, dsd, day)
    inv['outcomes'].append('OK')


def op_scan(inv, today, dsd, day):
    before = len(inv['events'])
    if inv['lifecycle'] in PAYABLE and inv['settlement'] != 'PAID':
        _forward(inv, today, dsd, day)
    inv['outcomes'].append('OK' if len(inv['events']) > before else 'SKIPPED')


def _settle(inv, delta, today, dsd, day):
    before_settlement, before_lifecycle = inv['settlement'], inv['lifecycle']
    inv['paid'] += delta
    inv['settlement'] = settlement_of(inv['paid'], inv['total'])
    inv['settled_on'] = settled_on_of(inv['ledger'], 'INV', inv['value_dates'], inv['total'])
    rank = {'UNPAID': 0, 'PARTIALLY_PAID': 1, 'PAID': 2}
    if inv['settlement'] != before_settlement:
        if inv['settlement'] == 'PAID':
            inv['events'].append([day, 'INVOICE_PAID'])
        elif rank[inv['settlement']] > rank[before_settlement]:
            inv['events'].append([day, 'INVOICE_PARTIALLY_PAID'])
        else:
            inv['events'].append([day, 'INVOICE_SETTLEMENT_REVERTED'])
    if before_settlement == 'PAID' and inv['settlement'] != 'PAID':
        _forward(inv, today, dsd, day)            # recalcul en avant (B3-a)
        if before_lifecycle == 'OVERDUE':
            inv['cycle'] += 1                     # règle (b) : déjà OVERDUE, donc aucune transition


def op_alloc(inv, today, dsd, day, payment, amount, value_date):
    inv['ledger'].append({'id': 'L%d' % len(inv['ledger']), 'payment': payment, 'invoice': 'INV', 'amount': amount, 'reverses': None})
    inv['value_dates'][payment] = value_date
    _settle(inv, amount, today, dsd, day)
    inv['outcomes'].append('OK')


def op_reverse(inv, today, dsd, day, allocation_index, amount):
    origin = [r for r in inv['ledger'] if r['amount'] > 0][allocation_index]
    assert amount <= reversible_of(inv['ledger'], origin['id'])
    inv['ledger'].append({'id': 'L%d' % len(inv['ledger']), 'payment': origin['payment'], 'invoice': 'INV', 'amount': -amount, 'reverses': origin['id']})
    _settle(inv, -amount, today, dsd, day)
    inv['outcomes'].append('OK')


def run_timeline(total, issue, due, due_soon_days, ops):
    """`ops` : ['issue', jour] | ['scan', jour] | ['alloc', jour, paiement, montant, date_de_valeur] | ['reverse', jour, indice_allocation, montant].
    Les jours sont des dates locales ISO."""
    inv = new_invoice(total, date.fromisoformat(issue), date.fromisoformat(due))
    for op in ops:
        day = op[1]
        today = date.fromisoformat(day)
        if op[0] == 'issue':
            op_issue(inv, today, due_soon_days, day)
        elif op[0] == 'scan':
            op_scan(inv, today, due_soon_days, day)
        elif op[0] == 'alloc':
            op_alloc(inv, today, due_soon_days, day, op[2], op[3], date.fromisoformat(op[4]))
        elif op[0] == 'reverse':
            op_reverse(inv, today, due_soon_days, day, op[2], op[3])
        else:
            raise ValueError(op)
    return {'lifecycle': inv['lifecycle'], 'settlement': inv['settlement'], 'paid': inv['paid'], 'settled_on': inv['settled_on'] and inv['settled_on'].isoformat(),
            'cycle': inv['cycle'], 'events': inv['events'], 'outcomes': inv['outcomes']}


# --------------------------------------------------------------------------- refus : le code du catalogue, dans l'ordre de précédence (§7.1)
def check_issue(inv, org_active, customer_status):
    """inv : lifecycle, lines (liste de line_total), total, issue, due."""
    if inv['lifecycle'] != 'DRAFT':
        return 'INVALID_TRANSITION'
    if not org_active:
        return 'ORG_NOT_ACTIVE'
    if customer_status == 'ARCHIVED':
        return 'CUSTOMER_ARCHIVED'
    if customer_status == 'INACTIVE':
        return 'CUSTOMER_INACTIVE'
    if len(inv['lines']) == 0:
        return 'INVOICE_EMPTY'
    if inv['total'] <= 0:
        return 'INVOICE_TOTAL_MUST_BE_POSITIVE'
    if inv['due'] < inv['issue']:
        return 'INVOICE_DATES_INVALID'
    if sum(inv['lines']) != inv['total']:
        return 'DB_INVARIANT_VIOLATED'
    return None


def check_cancel(inv):
    return None if inv['lifecycle'] == 'DRAFT' else 'INVALID_TRANSITION'


def check_void(inv, has_open_dispute):
    if inv['lifecycle'] not in PAYABLE:
        return 'INVALID_TRANSITION'
    if inv['paid'] > 0:
        return 'INVOICE_HAS_PAYMENTS'
    if has_open_dispute:
        return 'INVOICE_HAS_OPEN_DISPUTE'
    return None


def check_open_dispute(inv, has_open_dispute, reason, amount):
    if inv['lifecycle'] not in PAYABLE or inv['settlement'] == 'PAID':
        return 'DISPUTE_INVOICE_NOT_DISPUTABLE'
    if has_open_dispute:
        return 'DISPUTE_ALREADY_OPEN'
    if not reason.strip():
        return 'DISPUTE_REASON_REQUIRED'
    if amount is not None and amount > inv['total']:
        return 'DISPUTE_AMOUNT_EXCEEDS_TOTAL'
    return None


def check_create_payment(customer_status, amount, currency, org_currency, value_date, received_at, today, now, reference_taken):
    if customer_status == 'ARCHIVED':
        return 'CUSTOMER_ARCHIVED'
    if amount <= 0:
        return 'PAYMENT_AMOUNT_INVALID'
    if currency != org_currency:
        return 'PAYMENT_CURRENCY_MISMATCH'
    if value_date > today or received_at > now:
        return 'PAYMENT_DATE_IN_FUTURE'
    if reference_taken:
        return 'PAYMENT_DUPLICATE_REFERENCE'
    return None


def check_allocation(org_active, payment, invoices, lines):
    """payment : customer, currency, amount, allocated, status. invoices : {id: customer, currency, lifecycle, total, paid}. lines : [(id, montant)]."""
    if not org_active:
        return 'ORG_NOT_ACTIVE'
    if payment['status'] == 'REVERSED':
        return 'ALLOCATION_PAYMENT_REVERSED'
    for invoice_id, amount in lines:
        inv = invoices[invoice_id]
        if inv['lifecycle'] not in PAYABLE:
            return 'ALLOCATION_INVOICE_NOT_PAYABLE'
        if inv['customer'] != payment['customer']:
            return 'ALLOCATION_CUSTOMER_MISMATCH'
        if inv['currency'] != payment['currency']:
            return 'ALLOCATION_CURRENCY_MISMATCH'
        if amount > outstanding_of(inv['total'], inv['paid']):
            return 'ALLOCATION_EXCEEDS_INVOICE_OUTSTANDING'
    if sum(a for _, a in lines) > payment_available(payment['amount'], payment['allocated'], payment['status']):
        return 'ALLOCATION_EXCEEDS_PAYMENT_AVAILABLE'
    return None


def check_reverse_allocation(org_active, ledger, allocation_id, amount, reason):
    if not org_active:
        return 'ORG_NOT_ACTIVE'
    if not reason.strip():
        return 'REVERSAL_REASON_REQUIRED'
    if amount > reversible_of(ledger, allocation_id):
        return 'REVERSAL_EXCEEDS_ORIGINAL'
    return None


def check_reverse_payment(org_active, status, reason):
    if not org_active:
        return 'ORG_NOT_ACTIVE'
    if status == 'REVERSED':
        return 'PAYMENT_ALREADY_REVERSED'
    if not reason.strip():
        return 'PAYMENT_REVERSAL_REASON_REQUIRED'
    return None


def reverse_payment_effects(ledger, payment):
    """Une ligne négative par allocation active (reliquat) ; deltas cumulés par facture, dans l'ordre des identifiants de facture."""
    rows = [(r['id'], r['invoice'], reversible_of(ledger, r['id'])) for r in active_allocations(ledger, payment)]
    per_invoice = {}
    for _, invoice, amount in rows:
        per_invoice[invoice] = per_invoice.get(invoice, 0) - amount
    return {'reversals': rows, 'per_invoice': dict(sorted(per_invoice.items())), 'count': len(rows)}
