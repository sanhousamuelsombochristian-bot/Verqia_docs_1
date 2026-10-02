"""Mutations de CODE du Domain V1 : chacune retire ou corrompt UNE règle d'un invariant ; les tests désignés doivent alors ÉCHOUER (« tuer » la mutation).

Une mutation dont le motif est introuvable est une ERREUR de la porte, jamais un « OK ». Format : Mutation(id, edits, kill) ; `edits` = ((fichier relatif à verqia-app,
motif, remplacement, occurrences attendues), ...) ; `kill` = identifiants de tests de `domain_tests` qui doivent tomber. La relation invariant → mutations est dans `domain_proofs.py`.
"""
from collections import namedtuple

Mutation = namedtuple('Mutation', 'id edits kill')

S, L, F, B, D, I = ('verqia/invoices/domain/%s.py' % n for n in ('settlement', 'lifecycle', 'facts', 'body', 'dispute', 'invariants'))
A, PF = 'verqia/payments/domain/allocations.py', 'verqia/payments/domain/facts.py'
CAL = 'verqia/kernel/calendar.py'
DEC, REF, TAB, PRO, PUR = ('domain_tests.test_dt_%s.' % n for n in ('decisions', 'reference', 'tables_due', 'properties', 'purity_contracts'))
NOM, REFU, LIM = DEC + 'TestNominal.', DEC + 'TestRefusals.', DEC + 'TestLimits.'
GOLD = REF + 'TestGoldenTimelines.test_every_golden_timeline_matches_the_domain'
FACTS = REF + 'TestFactsAgainstTheReference.'

MUTATIONS = [
    Mutation('M-IF1-bounds-unchecked', ((S, "    if not 0 <= paid <= inv.total_minor:", "    if False:", 1),), (REFU + 'test_c20_settlement_service_defends_the_bounds',)),
    Mutation('M-IF2-partial-includes-total', ((F, "    if 0 < paid < total:", "    if 0 < paid <= total:", 1),), (FACTS + 'test_settlement_and_status_match_the_reference', GOLD)),
    Mutation('M-IF3-settled-on-without-full-payment', ((S, "    if paid != total or total <= 0:\n        return None", "    if total <= 0:\n        return None", 1),),
             (GOLD, NOM + 'test_n11_to_n14_allocations')),
    Mutation('M-IF3-settled-on-earliest-instead-of-latest', ((S, "    return max(dates)", "    return min(dates)", 1),), (LIM + 'test_l23_settled_on_is_the_latest_value_date_whatever_the_order', GOLD)),
    Mutation('M-IF4-positive-settlement-on-unpayable', ((S, "    if delta > 0 and not is_payable(inv):", "    if False:", 1),), (REFU + 'test_c20_settlement_service_defends_the_bounds',)),
    Mutation('M-IF4-void-with-payments', ((L, "    if inv.paid_minor > 0:\n        raise reject('INVOICE_HAS_PAYMENTS')", "    if False:\n        raise reject('INVOICE_HAS_PAYMENTS')", 1),),
             (REFU + 'test_c5_c6_void_guards',)),
    Mutation('M-IF5-zero-total-issued', ((L, "    if inv.total_minor <= 0:", "    if False:", 1),), (REFU + 'test_c2_issue_guards_and_their_precedence',)),
    Mutation('M-IF6-issued-at-not-written', ((L, "lifecycle_writes(inv, final, tuple(history), {'issued_at': as_of})", "lifecycle_writes(inv, final, tuple(history), {})", 1),),
             (NOM + 'test_n2_to_n5_issue_and_catch_up',)),
    Mutation('M-IF7-cancel-reason-not-written', ((L, "{'cancelled_at': as_of, 'cancel_reason': reason}", "{'cancelled_at': as_of}", 2),), (NOM + 'test_n18_to_n21_dispute_void_cancel',)),
    Mutation('M-IF8-dates-unchecked', ((B, "    if command.due_date < command.issue_date:", "    if False:", 1),), (REFU + 'test_create_invoice_guards',)),
    Mutation('M-IF9-rounding-down', ((I, "(quantity_e4 * unit_price_minor + 5000) // 10000", "(quantity_e4 * unit_price_minor) // 10000", 1),),
             (FACTS + 'test_line_rounding_matches_the_reference', LIM + 'test_l14_rounding', NOM + 'test_n1_create_invoice')),
    Mutation('M-IF10-body-rewritten', ((L, "'state_changed_at': after.state_changed_at}", "'state_changed_at': after.state_changed_at, 'total_minor': after.total_minor + 1}", 1),),
             (NOM + 'test_n2_to_n5_issue_and_catch_up',)),
    Mutation('M-IF11-lifecycle-can-go-back', ((L, "ISSUED_FAMILY.index(position) > ISSUED_FAMILY.index(current)", "ISSUED_FAMILY.index(position) != ISSUED_FAMILY.index(current)", 1),),
             (TAB + 'TestDueFunctions.test_a_scan_never_moves_back', GOLD)),
    Mutation('M-IF11-due-soon-window-off-by-one', ((F, "    if due - timedelta(days=due_soon_days) <= today:", "    if due - timedelta(days=due_soon_days) < today:", 1),),
             (TAB + 'TestDueFunctions.test_position_grid', FACTS + 'test_position_and_lateness_over_a_wide_grid')),
    Mutation('M-IF12-cycle-incremented-by-two', ((L, "(1 if target == OVERDUE else 0)", "(2 if target == OVERDUE else 0)", 1),), (NOM + 'test_n2_to_n5_issue_and_catch_up',)),
    Mutation('M-IF12-rule-a-missing', ((L, "(1 if target == OVERDUE else 0)", "0", 1),), (NOM + 'test_n2_to_n5_issue_and_catch_up', GOLD)),
    Mutation('M-IF12-rule-b-counted-twice', ((S, "final = replace(final, collection_cycle=final.collection_cycle + 1)", "final = replace(final, collection_cycle=final.collection_cycle + 2)", 1),),
             (GOLD, NOM + 'test_n15_to_n17_reversals')),
    Mutation('M-IF13-scan-without-event', ((L, "events=(event,), result={'invoice_id': inv.id, 'lifecycle_state'", "events=(), result={'invoice_id': inv.id, 'lifecycle_state'", 1),),
             (PRO + 'TestProperties.test_random_sequences_keep_every_invariant_and_every_refusal_is_closed', GOLD)),
    Mutation('M-IF14-void-with-open-dispute', ((L, "    if inv.open_dispute is not None:\n        raise reject('INVOICE_HAS_OPEN_DISPUTE')", "    if False:\n        raise reject('INVOICE_HAS_OPEN_DISPUTE')", 1),),
             (REFU + 'test_c5_c6_void_guards',)),
    Mutation('M-IF15-second-open-dispute', ((D, "    if inv.open_dispute is not None:\n        raise reject('DISPUTE_ALREADY_OPEN')", "    if False:\n        raise reject('DISPUTE_ALREADY_OPEN')", 1),),
             (REFU + 'test_c8_c19_dispute_guards',)),
    Mutation('M-IF16-scan-touches-paid-invoices', ((L, "    if inv.lifecycle_state not in ISSUED_FAMILY or inv.settlement_state == PAID:", "    if inv.lifecycle_state not in ISSUED_FAMILY:", 1),),
             (NOM + 'test_n6_to_n9_scans', GOLD)),
    Mutation('M-IF16-no-recalculation-after-reversal', ((S, "    if before == PAID and after_settlement != PAID:", "    if False and before == PAID and after_settlement != PAID:", 1),), (GOLD,)),
    Mutation('M-IP1-payment-overallocated', ((A, "    if total > payment_available(payment):", "    if False:", 1),), (REFU + 'test_c9_to_c14_allocation_guards',)),
    Mutation('M-IP2-allocated-off-by-one', ((A, "    allocated = payment.allocated_minor - amount", "    allocated = payment.allocated_minor - amount + 1", 1),),
             (NOM + 'test_n15_to_n17_reversals',)),
    Mutation('M-IP3-status-never-allocated', ((PF, "    if allocated < amount:\n        return PARTIALLY_ALLOCATED", "    if allocated <= amount:\n        return PARTIALLY_ALLOCATED", 1),),
             (FACTS + 'test_settlement_and_status_match_the_reference', NOM + 'test_n11_to_n14_allocations')),
    Mutation('M-IP4-reversed-payment-accepts-allocation', ((A, "    if payment.status == REVERSED:\n        raise reject('ALLOCATION_PAYMENT_REVERSED')", "    if False:\n        raise reject('ALLOCATION_PAYMENT_REVERSED')", 1),),
             (REFU + 'test_c13_c15_c17_reversal_guards',)),
    Mutation('M-IP5-amount-rewritten', ((A, "set={'allocated_minor': allocated, 'status': status})))", "set={'allocated_minor': allocated, 'status': status, 'amount_minor': allocated + 1})))", 1),),
             (NOM + 'test_n11_to_n14_allocations',)),
    Mutation('M-IA1-reversal-without-reason', ((A, "SOURCE_MANUAL if reverses is None else SOURCE_REVERSAL, reason, as_of)", "SOURCE_MANUAL if reverses is None else SOURCE_REVERSAL, None, as_of)", 1),),
             (NOM + 'test_n15_to_n17_reversals',)),
    Mutation('M-IA2-reversal-beyond-origin', ((A, "    if amount > reversible(payment.ledger, origin.id):", "    if False:", 1),), (REFU + 'test_c13_c15_c17_reversal_guards',)),
    Mutation('M-IA3-allocation-to-unpayable-invoice', ((A, "        if not inv.is_payable:", "        if False:", 1),), (REFU + 'test_c9_to_c14_allocation_guards',)),
    Mutation('M-IA4-customer-unchecked', ((A, "        if inv.customer_id != payment.customer_id:", "        if False:", 1),), (REFU + 'test_c9_to_c14_allocation_guards',)),
    Mutation('M-IA5-ledger-rewritten', ((A, "RowChange(expect=None, set={}, appends=appends)", "RowChange(expect=None, set={'ledger': ()}, appends=appends)", 1),),
             (DEC + 'TestAppendOnlyRegistry.test_every_write_to_the_registry_is_an_append_and_the_ledger_prefix_is_preserved',)),
    Mutation('M-IA6-invoice-overallocated', ((A, "        if l.amount_minor > inv.outstanding_minor:", "        if False:", 1),), (REFU + 'test_c9_to_c14_allocation_guards',)),
    Mutation('M-IX1-reversal-adds-money', ((S, "    paid = inv.paid_minor + delta", "    paid = inv.paid_minor + abs(delta)", 1),), (NOM + 'test_n15_to_n17_reversals', GOLD)),
    Mutation('M-IX3-reverse-payment-forgets-allocations',
             ((PF, "    return tuple(r for r in p.ledger if r.amount_minor > 0 and reversible(p.ledger, r.id) > 0)", "    return tuple(r for r in p.ledger if r.amount_minor > 0 and reversible(p.ledger, r.id) > 0)[:1]", 1),),
             (NOM + 'test_n15_to_n17_reversals', PRO + 'TestProperties.test_reverse_payment_returns_every_touched_invoice_to_its_previous_sums')),
    Mutation('M-IN1-nondeterministic-result', ((D, "from typing import Mapping\n", "from typing import Mapping\nimport itertools\n_C = itertools.count()\n", 1),
                                               (D, "result={'dispute_id': dispute_id}, outcome='OK')", "result={'dispute_id': dispute_id, 'n': next(_C)}, outcome='OK')", 1)),
             (PRO + 'TestProperties.test_every_decision_is_deterministic',)),
    Mutation('M-IN2-input-mutated', ((L, "    _check_invoice_id(inv, command)\n    transition(LIFECYCLE_TRANSITIONS, inv.lifecycle_state, ISSUED)",
                                      "    state['touched'] = True\n    _check_invoice_id(inv, command)\n    transition(LIFECYCLE_TRANSITIONS, inv.lifecycle_state, ISSUED)", 1),),
             (PUR + 'TestPurity.test_the_input_state_is_read_only',)),
    Mutation('M-IN3-utc-day-instead-of-local-day', ((CAL, ".astimezone(ZoneInfo(timezone)).date()", ".astimezone(ZoneInfo('UTC')).date()", 1),),
             (TAB + 'TestDueFunctions.test_local_day_in_the_organisation_timezone', FACTS + 'test_business_date_matches_the_reference')),
    Mutation('M-IN5-undeclared-event', ((L, "InvoiceCancelled(customer_id=inv.customer_id, reason_code=reason)", "InvoiceVoided(customer_id=inv.customer_id, reason_code=reason)", 1),),
             (PUR + 'TestContractFit.test_events_stay_within_the_declared_emits', NOM + 'test_n18_to_n21_dispute_void_cancel')),
]
