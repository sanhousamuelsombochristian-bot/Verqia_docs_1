"""Command Registry : tout cas d'usage, handler, travail et service, avec ses écritures, ses verrous, ses événements.

`src` : `EC-nn` / `SM` / `INV` = nom ou comportement figé dans un document ; `NOM FIGÉ` = nom créé par les registres et figé en revue (20 noms, convention de nommage : `NAMING` dans build_registry.py).
`writes` : états métier écrits (clés de STATES). Un état n'est écrit que par les cas d'usage de son module propriétaire,
sauf les trois exceptions C12 (`c12=True`).
"""
from collections import namedtuple

Cmd = namedtuple('Cmd', 'module name kind src lock emits writes idem subscribes calls implements c12 txn')


def C(module, name, kind, src, lock=None, emits=(), writes=(), idem='', subscribes=(), calls=(), implements=(), c12=False, txn='une'):
    return Cmd(module, name, kind, src, lock, tuple(emits), tuple(writes), idem, tuple(subscribes), tuple(calls), tuple(implements), c12, txn)


# clé d'état -> (module propriétaire, nature, description)
STATES = {
    'organizations.record': ('organizations', 'état', 'organisation : nom, fuseau, devise'),
    'organizations.status': ('organizations', 'état', 'PROVISIONING / ACTIVE / SUSPENDED / CLOSED (PROVISIONING : amendement)'),
    'organizations.settings': ('organizations', 'état', 'org_settings, org_holidays'),
    'identity.user': ('identity', 'état', 'utilisateur'),
    'identity.membership': ('identity', 'état', 'appartenance et rôle'),
    'customers.record': ('customers', 'état', 'client et contacts'),
    'customers.status': ('customers', 'état', 'ACTIVE / INACTIVE / ARCHIVED'),
    'invoices.body': ('invoices', 'état', 'facture DRAFT, lignes'),
    'invoices.lifecycle': ('invoices', 'état', 'lifecycle_state'),
    'invoices.settlement': ('invoices', 'cache', 'paid_minor, settlement_state, settled_on (cache des allocations)'),
    'invoices.collection_cycle': ('invoices', 'cache', 'compteur de cycle de recouvrement'),
    'invoices.dispute': ('invoices', 'état', 'invoice_disputes'),
    'payments.record': ('payments', 'état', 'paiement à la création'),
    'payments.allocated': ('payments', 'cache', 'allocated_minor, status'),
    'payments.allocations': ('payments', 'append', 'payment_allocations, payment_reversals (source de vérité du solde)'),
    'promises.status': ('promises', 'état', 'ACTIVE / FULFILLED / BROKEN / CANCELLED'),
    'imports.batch': ('imports', 'état', 'import_batches.status et staging'),
    'collection.action_status': ('collection', 'état', 'collection_actions.status'),
    'collection.attempts': ('collection', 'append', 'collection_action_attempts'),
    'collection.hold_status': ('collection', 'état', 'collection_holds'),
    'approvals.status': ('approvals', 'état', 'approvals.status'),
    'notifications.status': ('notifications', 'état', 'notifications.status, deliveries'),
    'automation.definition': ('automation', 'état', 'automations, automation_versions'),
    'automation.execution': ('automation', 'état', 'automation_executions.status et étapes'),
    'risk.profile': ('risk', 'projection', 'risk_profiles, risk_snapshots'),
    'priority.item': ('priority', 'projection', 'priority_items, priority_snapshots'),
    'cashflow.run': ('cashflow', 'projection', 'cashflow_runs (is_current), cashflow_lines'),
    'billing.subscription': ('billing', 'état', 'subscriptions (S7)'),
    'events.publication': ('events', 'état', 'published_at, available_at, publish_attempts'),
    'events.receipts': ('events', 'état', 'event_receipts'),
    'audit.log': ('audit', 'append', 'audit_logs'),
    'platform.idempotency': ('platform', 'état', 'idempotency_keys'),
}

# Événements de rafraîchissement (Rule Engine §2.3 / Risk-Priority-Cashflow §1.4) : vérifiés contre le document
RISK_REFRESH = ['INVOICE_ISSUED', 'INVOICE_OVERDUE', 'INVOICE_PARTIALLY_PAID', 'INVOICE_PAID', 'INVOICE_SETTLEMENT_REVERTED', 'INVOICE_VOIDED',
                'PAYMENT_ALLOCATED', 'PAYMENT_ALLOCATION_REVERSED', 'PAYMENT_REVERSED', 'PROMISE_BROKEN', 'PROMISE_FULFILLED']
PRIORITY_REFRESH = ['INVOICE_ISSUED', 'INVOICE_DUE_SOON', 'INVOICE_DUE', 'INVOICE_OVERDUE', 'INVOICE_PARTIALLY_PAID', 'INVOICE_PAID',
                    'INVOICE_SETTLEMENT_REVERTED', 'INVOICE_VOIDED', 'INVOICE_CANCELLED', 'INVOICE_DISPUTED', 'INVOICE_DISPUTE_RESOLVED',
                    'PAYMENT_CREATED', 'PAYMENT_ALLOCATED', 'PAYMENT_ALLOCATION_REVERSED', 'PAYMENT_REVERSED', 'PROMISE_CREATED',
                    'PROMISE_BROKEN', 'PROMISE_FULFILLED', 'PROMISE_CANCELLED', 'COLLECTION_HOLD_PLACED', 'COLLECTION_HOLD_RELEASED',
                    'COLLECTION_ACTION_EXECUTED', 'RISK_CHANGED']
# Événements déclencheurs d'une automatisation (Automation Engine §2)
AUTOMATION_TRIGGERS = ['INVOICE_ISSUED', 'INVOICE_DUE_SOON', 'INVOICE_DUE', 'INVOICE_OVERDUE', 'INVOICE_PARTIALLY_PAID', 'INVOICE_PAID',
                       'INVOICE_SETTLEMENT_REVERTED', 'INVOICE_DISPUTED', 'INVOICE_DISPUTE_RESOLVED', 'INVOICE_VOIDED', 'PRIORITY_CHANGED',
                       'PAYMENT_CREATED', 'PAYMENT_ALLOCATED', 'PAYMENT_ALLOCATION_REVERSED', 'PAYMENT_REVERSED',
                       'PROMISE_CREATED', 'PROMISE_FULFILLED', 'PROMISE_BROKEN', 'PROMISE_CANCELLED', 'RISK_CHANGED']
# Décision validée (revue 3) : déclencheurs explicites de recalcul Cashflow pour ORGANISATION / 30 j et 90 j / BASE, coalescence 5 min.
# Le Cashflow V1.1 (§4.8) ne les listait pas.
CASHFLOW_REFRESH_EVENTS = ['INVOICE_ISSUED', 'INVOICE_PAID', 'INVOICE_PARTIALLY_PAID', 'INVOICE_SETTLEMENT_REVERTED', 'INVOICE_VOIDED',
                             'INVOICE_CANCELLED', 'PAYMENT_CREATED', 'PAYMENT_ALLOCATED', 'PAYMENT_ALLOCATION_REVERSED', 'PAYMENT_REVERSED',
                             'PROMISE_CREATED', 'PROMISE_BROKEN', 'PROMISE_FULFILLED', 'PROMISE_CANCELLED']

# Champs d'`org_settings` que lit le modèle cash-1.0 et dont un changement impose un recalcul. Vérifié dans le document Risk / Priority /
# Cashflow V1.1 §4 : cash-1.0 ne lit AUCUN champ d'`org_settings` (il lit le fuseau et la devise de `organizations`, la date des promesses telle
# quelle, et des délais calculés sur les factures). L'ensemble est donc vide en V1 : le filtre existe pour que cash-2.0 y déclare ses champs.
CASHFLOW_ORG_SETTINGS_RELEVANT = ()

COMMANDS = [
    # ---------------------------------------------------------------- organizations
    C('organizations', 'CreateOrganization', 'command', 'INV C12 (amendé)', 'CreateOrganization', [], ['organizations.record', 'organizations.settings', 'organizations.status'], 'clé d\'idempotence',
      calls=['own:organizations.ProvisioningStep', 'own:organizations.CompleteProvisioning'], txn='une par étape (plan de provisioning)'),
    C('organizations', 'CompleteProvisioning', 'system', 'NOM FIGÉ', 'CompleteProvisioning', ['ORGANIZATION_CREATED'], ['organizations.status'], 'garde d\'état PROVISIONING → ACTIVE'),
    C('organizations', 'ResumeProvisioning', 'job', 'NOM FIGÉ', None, [], [], 'idempotence par étape', calls=['own:organizations.ProvisioningStep', 'own:organizations.CompleteProvisioning']),
    C('organizations', 'UpdateOrganization', 'command', 'NOM FIGÉ', 'ChangeOrganization', ['ORGANIZATION_UPDATED'], ['organizations.record'], 'version'),
    C('organizations', 'ChangeOrgSettings', 'command', 'NOM FIGÉ', 'ChangeOrganization', ['ORG_SETTINGS_CHANGED'], ['organizations.settings'], 'version'),
    C('organizations', 'SuspendOrganization', 'command', 'SM §1', 'ChangeOrganization', ['ORGANIZATION_SUSPENDED'], ['organizations.status'], 'garde d\'état'),
    C('organizations', 'ReactivateOrganization', 'command', 'SM §1', 'ChangeOrganization', ['ORGANIZATION_REACTIVATED'], ['organizations.status'], 'garde d\'état'),
    C('organizations', 'CloseOrganization', 'command', 'SM §1', 'ChangeOrganization', ['ORGANIZATION_CLOSED'], ['organizations.status'], 'garde d\'état'),
    C('automation', 'ProvisionDefaultAutomations', 'service', 'NOM FIGÉ', 'InstallDefaults', ['AUTOMATION_CREATED'], ['automation.definition'], '(organisation, étape)',
      implements=['organizations.ProvisioningStep']),
    # ---------------------------------------------------------------- identity
    C('identity', 'CreateUser', 'command', 'NOM FIGÉ', 'IdentityCommand', ['USER_CREATED'], ['identity.user'], 'e-mail unique'),
    C('identity', 'ChangeUserStatus', 'command', 'SM §15', 'IdentityCommand', ['USER_STATUS_CHANGED'], ['identity.user'], 'garde d\'état'),
    C('identity', 'AddMember', 'command', 'NOM FIGÉ', 'IdentityCommand', ['MEMBER_ADDED'], ['identity.membership'], 'unicité (organisation, utilisateur)'),
    C('identity', 'ProvisionOwnerMembership', 'service', 'NOM FIGÉ', 'ProvisionOwner', ['MEMBER_ADDED'], ['identity.membership'], '(organisation, étape)', implements=['organizations.ProvisioningStep']),
    C('identity', 'ChangeMemberRole', 'command', 'SM §15', 'IdentityCommand', ['MEMBER_ROLE_CHANGED'], ['identity.membership'], 'version'),
    C('identity', 'RemoveMember', 'command', 'SM §15', 'IdentityCommand', ['MEMBER_REMOVED'], ['identity.membership'], 'garde d\'état'),
    # ---------------------------------------------------------------- customers
    C('customers', 'CreateCustomer', 'command', 'NOM FIGÉ', 'CustomerCommand', ['CUSTOMER_CREATED'], ['customers.record'], 'external_ref unique'),
    C('customers', 'UpdateCustomer', 'command', 'NOM FIGÉ', 'CustomerCommand', ['CUSTOMER_UPDATED'], ['customers.record'], 'version'),
    C('customers', 'DeactivateCustomer', 'command', 'SM §2', 'CustomerCommand', ['CUSTOMER_DEACTIVATED'], ['customers.status'], 'garde d\'état'),
    C('customers', 'ArchiveCustomer', 'command', 'SM §2', 'CustomerCommand', ['CUSTOMER_ARCHIVED'], ['customers.status'], 'garde d\'état'),
    C('customers', 'ReactivateCustomer', 'command', 'SM §2', 'CustomerCommand', ['CUSTOMER_REACTIVATED'], ['customers.status'], 'garde d\'état'),
    C('customers', 'AddCustomerContact', 'command', 'NOM FIGÉ', 'CustomerCommand', ['CUSTOMER_CONTACT_ADDED'], ['customers.record'], 'unicité contact actif'),
    C('customers', 'UpdateCustomerContact', 'command', 'NOM FIGÉ', 'CustomerCommand', ['CUSTOMER_CONTACT_UPDATED'], ['customers.record'], 'version'),
    # ---------------------------------------------------------------- invoices
    C('invoices', 'CreateInvoice', 'command', 'EC-06', 'CreateInvoice', ['INVOICE_CREATED'], ['invoices.body'], 'clé d\'idempotence', calls=['customers.CustomerFacts', 'organizations.OrgStatus']),
    C('invoices', 'IssueInvoice', 'command', 'EC-06', 'IssueInvoice', ['INVOICE_ISSUED', 'INVOICE_DUE_SOON', 'INVOICE_DUE', 'INVOICE_OVERDUE'], ['invoices.lifecycle', 'invoices.collection_cycle'], 'garde d\'état',
      calls=['customers.CustomerFacts', 'organizations.OrgStatus']),
    C('invoices', 'CancelInvoice', 'command', 'EC-06', 'InvoiceTransition', ['INVOICE_CANCELLED'], ['invoices.lifecycle'], 'garde d\'état'),
    C('invoices', 'VoidInvoice', 'command', 'EC-06', 'InvoiceTransition', ['INVOICE_VOIDED'], ['invoices.lifecycle'], 'garde d\'état'),
    C('invoices', 'OpenInvoiceDispute', 'command', 'SM §4', 'InvoiceDisputeCommand', ['INVOICE_DISPUTED'], ['invoices.dispute'], 'clé d\'idempotence'),
    C('invoices', 'ResolveInvoiceDispute', 'command', 'SM §4', 'InvoiceDisputeCommand', ['INVOICE_DISPUTE_RESOLVED'], ['invoices.dispute'], 'garde d\'état'),
    C('invoices', 'InvoiceLifecycleScan', 'job', 'EC-03', 'InvoiceTransition', ['INVOICE_DUE_SOON', 'INVOICE_DUE', 'INVOICE_OVERDUE'], ['invoices.lifecycle', 'invoices.collection_cycle'], 'UPDATE … WHERE état = ancien', txn='une par facture', calls=['organizations.OrgStatus']),
    C('invoices', 'ApplySettlement', 'service', 'EC-05', 'PaymentSettlement', ['INVOICE_PARTIALLY_PAID', 'INVOICE_PAID', 'INVOICE_SETTLEMENT_REVERTED', 'INVOICE_DUE_SOON', 'INVOICE_DUE', 'INVOICE_OVERDUE'],
      ['invoices.settlement', 'invoices.collection_cycle', 'invoices.lifecycle'], 'dans la transaction de l\'appelant', c12=True, calls=['organizations.OrgStatus']),
    # ---------------------------------------------------------------- payments
    C('payments', 'CreatePayment', 'command', 'NOM FIGÉ', 'CreatePayment', ['PAYMENT_CREATED'], ['payments.record'], 'clé d\'idempotence', calls=['customers.CustomerFacts', 'organizations.OrgStatus']),
    C('payments', 'AllocatePayment', 'command', 'EC-05', 'PaymentSettlement', ['PAYMENT_ALLOCATED'], ['payments.allocations', 'payments.allocated', 'invoices.settlement', 'invoices.collection_cycle'],
      'clé d\'idempotence', calls=['invoices.ApplySettlement', 'invoices.InvoiceFacts', 'organizations.OrgStatus'], c12=True),
    C('payments', 'ReverseAllocation', 'command', 'EC-05', 'PaymentSettlement', ['PAYMENT_ALLOCATION_REVERSED'], ['payments.allocations', 'payments.allocated', 'invoices.settlement', 'invoices.collection_cycle', 'invoices.lifecycle'],
      'clé d\'idempotence', calls=['invoices.ApplySettlement', 'organizations.OrgStatus'], c12=True),
    C('payments', 'ReversePayment', 'command', 'EC-05', 'PaymentSettlement', ['PAYMENT_REVERSED', 'PAYMENT_ALLOCATION_REVERSED'], ['payments.allocations', 'payments.allocated', 'invoices.settlement', 'invoices.collection_cycle', 'invoices.lifecycle'],
      'clé d\'idempotence', calls=['invoices.ApplySettlement', 'organizations.OrgStatus'], c12=True),
    # ---------------------------------------------------------------- promises
    C('promises', 'CreatePromise', 'command', 'SM §7', 'CreatePromise', ['PROMISE_CREATED'], ['promises.status'], 'clé d\'idempotence'),
    C('promises', 'CancelPromise', 'command', 'SM §7', 'PromiseTransition', ['PROMISE_CANCELLED'], ['promises.status'], 'garde d\'état'),
    C('promises', 'FulfillPromiseOnInvoicePaid', 'handler', 'SM §7', 'PromiseTransition', ['PROMISE_FULFILLED'], ['promises.status'], 'reçu', subscribes=['INVOICE_PAID']),
    C('promises', 'FulfillPromiseOnAllocation', 'handler', 'SM §7', 'PromiseTransition', ['PROMISE_FULFILLED'], ['promises.status'], 'reçu', subscribes=['PAYMENT_ALLOCATED']),
    C('promises', 'CancelPromiseOnInvoiceEnded', 'handler', 'SM §7', 'PromiseTransition', ['PROMISE_CANCELLED'], ['promises.status'], 'reçu', subscribes=['INVOICE_VOIDED', 'INVOICE_CANCELLED']),
    C('promises', 'CancelPromiseOnCustomerArchived', 'handler', 'SM §7', 'PromiseTransition', ['PROMISE_CANCELLED'], ['promises.status'], 'reçu', subscribes=['CUSTOMER_ARCHIVED']),
    C('promises', 'PromiseBreachScan', 'job', 'EC-03', 'PromiseTransition', ['PROMISE_BROKEN'], ['promises.status'], 'UPDATE … WHERE état = ancien'),
    # ---------------------------------------------------------------- imports
    C('imports', 'UploadImportBatch', 'command', 'SM §14', 'ImportBatchTransition', ['IMPORT_BATCH_UPLOADED'], ['imports.batch'], 'file_hash unique'),
    C('imports', 'ValidateImportBatch', 'handler', 'SM §14', 'ValidateImportBatch', ['IMPORT_BATCH_READY', 'IMPORT_BATCH_FAILED'], ['imports.batch'], 'garde d\'état', subscribes=['IMPORT_BATCH_UPLOADED']),
    C('imports', 'ApproveImportBatch', 'command', 'SM §14', 'ImportBatchTransition', ['IMPORT_BATCH_APPROVED'], ['imports.batch'], 'garde d\'état'),
    C('imports', 'CommitImportBatch', 'command', 'SM §14', 'ImportBatchTransition', ['IMPORT_BATCH_COMMITTED'], ['imports.batch'], 'garde d\'état'),
    C('imports', 'CancelImportBatch', 'command', 'SM §14', 'ImportBatchTransition', ['IMPORT_BATCH_CANCELLED'], ['imports.batch'], 'garde d\'état'),
    C('imports', 'NormalizeImportBatch', 'handler', 'EC-07', 'NormalizeImportBatch', ['IMPORT_BATCH_NORMALIZED', 'IMPORT_BATCH_FAILED',
                                                                               'RISK_RECALCULATION_REQUESTED', 'PRIORITY_RECALCULATION_REQUESTED', 'CASHFLOW_RECALCULATION_REQUESTED'],
      ['imports.batch', 'customers.record', 'invoices.body', 'invoices.lifecycle', 'invoices.settlement', 'payments.record', 'payments.allocations', 'payments.allocated'],
      'garde d\'état COMMITTED → NORMALIZING', subscribes=['IMPORT_BATCH_COMMITTED'], calls=['customers.CreateCustomer', 'invoices.CreateInvoice', 'payments.CreatePayment', 'payments.AllocatePayment'], c12=True),
    C('imports', 'StartImportRelease', 'handler', 'SM §16', 'StartImportRelease', [], ['imports.batch'], 'garde d\'état NORMALIZED → RELEASING', subscribes=['IMPORT_BATCH_NORMALIZED']),
    C('imports', 'CompleteImportRelease', 'system', 'NOM FIGÉ', 'ImportBatchTransition', ['IMPORT_BATCH_RELEASED'], ['imports.batch'], 'garde d\'état RELEASING → RELEASED'),
    # ---------------------------------------------------------------- collection
    C('collection', 'CreateCollectionAction', 'command', 'EC-11', 'CreateCollectionAction', ['COLLECTION_ACTION_PROPOSED', 'COLLECTION_ACTION_SUPPRESSED'],
      ['collection.action_status'], 'dedup_key', calls=['rules.Evaluate', 'own:collection.AdvanceProposedAction'], txn='une par module propriétaire : action, puis approbation, puis transition'),
    C('collection', 'AdvanceProposedAction', 'system', 'NOM FIGÉ', 'AdvanceProposedAction', ['COLLECTION_ACTION_SCHEDULED', 'COLLECTION_ACTION_SUPPRESSED'],
      ['collection.action_status'], 'garde d\'état PROPOSED',
      calls=['rules.Evaluate', 'organizations.CalendarReader', 'organizations.OrgSettings', 'own:approvals.RequestApproval']),
    # B9 : le SlotCalculator (Collection §7) exige jours ouvrés/fériés (CalendarReader) ET fenêtre de communication + send_rate_per_hour (OrgSettings)
    C('collection', 'ResumeProposedActions', 'job', 'NOM FIGÉ', 'AdvanceProposedAction', [], ['collection.action_status'], 'garde d\'état PROPOSED', calls=['own:collection.AdvanceProposedAction']),
    C('collection', 'CreateManualAction', 'command', 'EC-11', 'CreateCollectionAction', ['COLLECTION_ACTION_PROPOSED', 'COLLECTION_ACTION_SUPPRESSED'],
      ['collection.action_status'], 'manual:{clé}', calls=['rules.Evaluate', 'collection.AuthorizeOverride', 'own:collection.AdvanceProposedAction'], txn='une par module propriétaire'),
    C('collection', 'AuthorizeOverride', 'service', 'EC-10', None, [], [], 'sans effet propre ; audit à la création puis à chaque vérification'),
    C('collection', 'CancelCollectionAction', 'command', 'SM §8', 'CollectionReaction', ['COLLECTION_ACTION_CANCELLED'], ['collection.action_status'], 'garde d\'état'),
    C('collection', 'ClaimTask', 'command', 'EC-11', 'ClaimTask', [],
      ['collection.action_status'], 'une seule réclamation gagne (UPDATE … WHERE assigned_to IS NULL)'),
    # AUDIT-01.a/.b (B8) : aucun événement ni audit dédié identifiés dans les sources auditées — emits=() ne vaut pas preuve d'absence, réserve ouverte
    C('collection', 'CompleteTask', 'command', 'SM §8', 'CollectionReaction', ['COLLECTION_ACTION_EXECUTED'],
      ['collection.action_status'], 'garde d\'état'),
    # AUDIT-01.c (B8) : aucun audit dédié identifié dans les sources auditées — réserve ouverte, pas une affirmation d'absence
    C('collection', 'RescheduleAction', 'command', 'EC-11, Invariants §7.1', 'RescheduleAction', [],
      ['collection.action_status'], 'garde d\'état',
      calls=['organizations.CalendarReader', 'organizations.OrgSettings']),      # B9 : même SlotCalculator qu'à la planification initiale (Collection §7)
    # AUDIT-01.e/.f (B8) : aucun événement identifié ; erreur de créneau cible invalide non normée dans les sources — réserves ouvertes, non closes par cet amendement
    C('collection', 'ExecuteDueAction', 'worker', 'EC-11', 'ExecuteDueAction', ['COLLECTION_ACTION_SUPPRESSED'], ['collection.action_status', 'collection.attempts'], 'claim gardé',
      calls=['rules.Evaluate', 'collection.AuthorizeOverride', 'own:notifications.CreateNotification'], txn='claim + revalidation ; notification ; envoi hors transaction ; résultat'),
    C('collection', 'ReapActions', 'job', 'EC-03', 'ReapActions', [], ['collection.action_status', 'collection.attempts'], 'transition gardée'),
    C('collection', 'SuppressOnInvoicePaid', 'handler', 'Collection §12', 'CollectionReaction', ['COLLECTION_ACTION_SUPPRESSED'], ['collection.action_status'], 'reçu', subscribes=['INVOICE_PAID']),
    C('collection', 'SuppressOnInvoiceEnded', 'handler', 'Collection §12', 'CollectionReaction', ['COLLECTION_ACTION_SUPPRESSED'], ['collection.action_status'], 'reçu', subscribes=['INVOICE_VOIDED', 'INVOICE_CANCELLED']),
    C('collection', 'SuppressOnInvoiceDisputed', 'handler', 'Collection §12, D1', 'CollectionReaction', ['COLLECTION_ACTION_SUPPRESSED'], ['collection.action_status'], 'reçu',
      subscribes=['INVOICE_DISPUTED'], calls=['invoices.InvoiceFacts']),      # AM-03 (DV4-8) : collectible_minor absent du payload de l'événement
    C('collection', 'SuppressOnPromiseCreated', 'handler', 'Collection §12', 'CollectionReaction', ['COLLECTION_ACTION_SUPPRESSED'], ['collection.action_status'], 'reçu', subscribes=['PROMISE_CREATED']),
    C('collection', 'SuppressOnHoldPlaced', 'handler', 'Collection §12', 'CollectionReaction', ['COLLECTION_ACTION_SUPPRESSED'], ['collection.action_status'], 'reçu', subscribes=['COLLECTION_HOLD_PLACED']),
    C('collection', 'SuppressOnCustomerInactive', 'handler', 'Collection §12', 'CollectionReaction', ['COLLECTION_ACTION_SUPPRESSED'], ['collection.action_status'], 'reçu', subscribes=['CUSTOMER_DEACTIVATED', 'CUSTOMER_ARCHIVED']),
    C('collection', 'SuppressOnOrgSuspended', 'handler', 'Collection §12', 'CollectionReaction', ['COLLECTION_ACTION_SUPPRESSED'], ['collection.action_status'], 'reçu', subscribes=['ORGANIZATION_SUSPENDED', 'ORGANIZATION_CLOSED']),
    C('collection', 'OnApprovalDecided', 'handler', 'Collection §6', 'CollectionReaction', ['COLLECTION_ACTION_SCHEDULED', 'COLLECTION_ACTION_CANCELLED'], ['collection.action_status'], 'reçu', subscribes=['APPROVAL_GRANTED', 'APPROVAL_REJECTED']),
    C('collection', 'OnNotificationResult', 'handler', 'Collection §8', 'CollectionReaction', ['COLLECTION_ACTION_EXECUTED', 'COLLECTION_ACTION_FAILED', 'COLLECTION_ACTION_SCHEDULED'], ['collection.action_status', 'collection.attempts'], 'reçu', subscribes=['NOTIFICATION_SENT', 'NOTIFICATION_FAILED']),
    C('collection', 'PlaceHold', 'command', 'SM §9', 'PlaceHold', ['COLLECTION_HOLD_PLACED'], ['collection.hold_status'], 'clé d\'idempotence + EXCLUDE'),
    C('collection', 'ReleaseHold', 'command', 'SM §9', 'ReleaseHold', ['COLLECTION_HOLD_RELEASED'], ['collection.hold_status'], 'garde d\'état'),
    C('collection', 'HoldExpiryScan', 'job', 'EC-03', 'ReleaseHold', ['COLLECTION_HOLD_RELEASED'], ['collection.hold_status'], 'UPDATE … WHERE état = ancien'),
    C('collection', 'ScanReconciliationReviews', 'job', 'Collection V1.2 §8.2', None, [], [], 'dedup_key', calls=['own:notifications.CreateNotification'], txn='par organisation'),
    # ---------------------------------------------------------------- approvals
    C('approvals', 'RequestApproval', 'service', 'EC-13', 'RequestApproval', ['APPROVAL_REQUESTED'], ['approvals.status'], 'par cible et étape', calls=['approvals.ApprovalTargetReader']),
    C('approvals', 'DecideApproval', 'command', 'EC-13', 'DecideApproval', ['APPROVAL_GRANTED', 'APPROVAL_REJECTED'], ['approvals.status'], 'une seule décision', calls=['approvals.ApprovalTargetReader']),
    C('approvals', 'ApprovalExpiryScan', 'job', 'EC-13', 'ApprovalExpiryScan', [], ['approvals.status'], 'UPDATE … WHERE état = ancien', calls=['approvals.ApprovalTargetReader']),
    C('collection', 'ReadApprovalTarget', 'service', 'NOM FIGÉ', None, [], [], 'lecture seule', implements=['approvals.ApprovalTargetReader']),
    C('automation', 'ReadApprovalTarget', 'service', 'NOM FIGÉ', None, [], [], 'lecture seule', implements=['approvals.ApprovalTargetReader']),
    # ---------------------------------------------------------------- notifications
    C('notifications', 'CreateNotification', 'service', 'EC-04', 'CreateNotification', ['NOTIFICATION_CREATED'], ['notifications.status'], 'dedup_key'),
    C('notifications', 'HandleSendResult', 'worker', 'EC-04', 'HandleSendResult', ['NOTIFICATION_SENT', 'NOTIFICATION_FAILED'], ['notifications.status'], '(notification_id, attempt_no)', txn='une, hors envoi'),
    C('notifications', 'NotifyApprovers', 'handler', 'NOM FIGÉ', 'NotifyApprovers', ['NOTIFICATION_CREATED'], ['notifications.status'], 'dedup_key', subscribes=['APPROVAL_REQUESTED']),
    # ---------------------------------------------------------------- automation
    C('automation', 'CreateAutomation', 'command', 'EC-12', 'AutomationDefinitionCommand', ['AUTOMATION_CREATED'], ['automation.definition'], 'clé d\'idempotence'),
    C('automation', 'CreateAutomationVersion', 'command', 'EC-12', 'AutomationDefinitionCommand', ['AUTOMATION_VERSION_CREATED'], ['automation.definition'], 'version'),
    C('automation', 'ActivateAutomation', 'command', 'EC-12', 'ActivateAutomation', ['AUTOMATION_ACTIVATED'], ['automation.definition', 'automation.execution'], 'garde d\'état + empreinte'),
    C('automation', 'PauseAutomation', 'command', 'EC-12', 'AutomationDefinitionCommand', ['AUTOMATION_PAUSED'], ['automation.definition'], 'garde d\'état'),
    C('automation', 'DisableAutomation', 'command', 'EC-12', 'AutomationDefinitionCommand', ['AUTOMATION_DISABLED'], ['automation.definition'], 'garde d\'état'),
    C('automation', 'ArchiveAutomation', 'command', 'EC-12', 'AutomationDefinitionCommand', ['AUTOMATION_ARCHIVED'], ['automation.definition'], 'garde d\'état'),
    C('automation', 'DispatchEvent', 'handler', 'EC-12', 'DispatchEvent', [], ['automation.execution'], 'trigger_key = event:{id}', subscribes=AUTOMATION_TRIGGERS),
    C('automation', 'ScanTimeTriggers', 'job', 'EC-12', 'DispatchEvent', [], ['automation.execution'], 'trigger_key temporel'),
    C('automation', 'RunExecutionStep', 'worker', 'EC-12', 'RecordExecutionStep', ['AUTOMATION_EXECUTION_STARTED', 'AUTOMATION_EXECUTION_COMPLETED', 'AUTOMATION_EXECUTION_FAILED', 'RISK_RECALCULATION_REQUESTED', 'PRIORITY_RECALCULATION_REQUESTED', 'CASHFLOW_RECALCULATION_REQUESTED'],
      ['automation.execution'], 'effets idempotents + garde d\'état', calls=['rules.Evaluate', 'own:collection.CreateCollectionAction', 'own:notifications.CreateNotification', 'own:approvals.RequestApproval'], txn='trois : réclamer, effet dans la transaction du module propriétaire, enregistrer'),
    C('automation', 'PauseOrCancelOnSubjectChange', 'handler', 'SM §16', 'ChangeExecutionState', ['AUTOMATION_EXECUTION_CANCELLED'], ['automation.execution'], 'reçu',
      subscribes=['INVOICE_PAID', 'INVOICE_VOIDED', 'INVOICE_CANCELLED', 'INVOICE_DISPUTED', 'PROMISE_CREATED', 'COLLECTION_HOLD_PLACED', 'CUSTOMER_DEACTIVATED', 'CUSTOMER_ARCHIVED', 'ORGANIZATION_SUSPENDED', 'ORGANIZATION_CLOSED']),
    C('automation', 'OnAutomationPausedOrDisabled', 'handler', 'SM §12', 'ChangeExecutionState', ['AUTOMATION_EXECUTION_CANCELLED'], ['automation.execution'], 'reçu', subscribes=['AUTOMATION_PAUSED', 'AUTOMATION_DISABLED']),
    C('automation', 'ResumeOnCauseLifted', 'handler', 'Automation §7', 'ChangeExecutionState', [], ['automation.execution'], 'reçu',
      subscribes=['INVOICE_DISPUTE_RESOLVED', 'PROMISE_FULFILLED', 'PROMISE_BROKEN', 'PROMISE_CANCELLED', 'COLLECTION_HOLD_RELEASED', 'CUSTOMER_REACTIVATED', 'ORGANIZATION_REACTIVATED', 'IMPORT_BATCH_RELEASED',
                  'AUTOMATION_ACTIVATED', 'PAYMENT_ALLOCATED', 'PAYMENT_REVERSED']),
    C('automation', 'OnApprovalDecidedForExecution', 'handler', 'Automation §6', 'ChangeExecutionState', [], ['automation.execution'], 'reçu', subscribes=['APPROVAL_GRANTED', 'APPROVAL_REJECTED']),
    C('automation', 'ResumeReconciliationPaused', 'job', 'Collection V1.2 §8.2', 'ChangeExecutionState', [], ['automation.execution'], 'garde d\'état', calls=['rules.Evaluate'], txn='par organisation'),
    C('automation', 'ReleaseImportTranche', 'system', 'Automation §10.1', 'ReleaseTranche', [], ['automation.execution'], 'trigger_key = import-release:…', calls=['imports.ImportReleaseFacts'], txn='une par tranche'),
    C('jobs', 'ImportReleaser', 'job', 'Automation §10.1', None, [], [], 'composition ; chaque pas est idempotent', calls=['own:automation.ReleaseImportTranche', 'own:imports.CompleteImportRelease', 'automation.ReleaseProgress'], txn='une par pas'),
    C('jobs', 'ReconciliationWindowScan', 'job', 'Collection V1.2 §8.2', None, [], [], 'composition ; chaque pas est idempotent', calls=['own:collection.ScanReconciliationReviews', 'own:automation.ResumeReconciliationPaused'], txn='une par pas'),
    C('automation', 'ReapExecutions', 'job', 'EC-03', 'ReapExecutions', [], ['automation.execution'], 'transition gardée'),
    C('automation', 'RetryExecution', 'command', 'EC-12', 'DispatchEvent', [], ['automation.execution'], 'trigger_key = retry:{id}'),
    # ---------------------------------------------------------------- risk / priority / cashflow
    C('risk', 'RequestRiskRecalc', 'handler', 'EC-14', None, ['RISK_RECALCULATION_REQUESTED'], [], 'regroupement par cible', subscribes=RISK_REFRESH),
    C('risk', 'RecomputeRisk', 'handler', 'EC-14', 'ProjectionRecompute', ['RISK_CHANGED'], ['risk.profile'], 'input_hash', subscribes=['RISK_RECALCULATION_REQUESTED'],
      calls=['organizations.CalendarReader', 'organizations.OrgSettings', 'invoices.OpenInvoicesOfCustomer', 'invoices.SettledInvoicesOfCustomer',
             'invoices.EverIssuedOfCustomer', 'payments.ReversedPaymentsOfCustomer', 'promises.BrokenPromisesOfCustomer']),      # RISK_DOMAIN_V1.md RD2.3/RD2.4, DV2-1
    C('risk', 'RequestDailyRiskRefresh', 'job', 'EC-03', None, ['RISK_RECALCULATION_REQUESTED'], [], 'regroupement par cible'),
    C('priority', 'RequestPriorityRecalc', 'handler', 'EC-14', None, ['PRIORITY_RECALCULATION_REQUESTED'], [], 'regroupement par cible', subscribes=PRIORITY_REFRESH),
    C('priority', 'RecomputePriority', 'handler', 'EC-14', 'ProjectionRecompute', ['PRIORITY_CHANGED'], ['priority.item'], 'input_hash', subscribes=['PRIORITY_RECALCULATION_REQUESTED'],
      calls=['organizations.OrgSettings', 'invoices.InvoiceFacts', 'risk.RiskLevel', 'promises.PromiseFacts', 'collection.CollectionFacts']),      # PRIORITY_DOMAIN_V1.md PD2.2/PD2.3, DV3-8
    C('priority', 'RequestDailyPriorityRefresh', 'job', 'EC-03', None, ['PRIORITY_RECALCULATION_REQUESTED'], [], 'regroupement par cible'),
    C('cashflow', 'RequestCashflowRecalc', 'handler', 'EC-14', None, ['CASHFLOW_RECALCULATION_REQUESTED'], [], 'portée : organisation ; horizons 30 et 90 jours, scénario BASE ; regroupement 5 min (Cashflow §4.8) ; ORG_SETTINGS_CHANGED filtré sur CASHFLOW_ORG_SETTINGS_RELEVANT', subscribes=CASHFLOW_REFRESH_EVENTS + ['ORG_SETTINGS_CHANGED']),
    C('cashflow', 'RunCashflow', 'handler', 'EC-14', 'RunCashflow', ['CASHFLOW_UPDATED'], ['cashflow.run'], 'input_hash + promotion monotone', subscribes=['CASHFLOW_RECALCULATION_REQUESTED']),
    C('cashflow', 'CashflowScheduler', 'job', 'EC-03', None, ['CASHFLOW_RECALCULATION_REQUESTED'], [], 'input_hash'),
    # ---------------------------------------------------------------- billing (S7)
    C('billing', 'ProvisionTrialSubscription', 'service', 'NOM FIGÉ (S7)', 'ProvisionTrial', ['SUBSCRIPTION_CHANGED'], ['billing.subscription'], '(organisation, étape)', implements=['organizations.ProvisioningStep']),
    # ---------------------------------------------------------------- socle
    C('events', 'OutboxPublisher', 'worker', 'EC-03', 'JobStep', [], ['events.publication', 'events.receipts'], 'bail + reçus', txn='trois : réclamer par bail ; chaque handler dans sa transaction ; poser publié'),
    C('events', 'ReplayDeadEvent', 'command', 'EC-02', 'ReplayDeadEvent', [], ['events.receipts'], 'clé d\'idempotence'),
    C('customers', 'AnonymizeCustomer', 'system', 'INV §17', 'Anonymize', [], ['customers.record'], 'anonymized_at ; audit PII_ANONYMIZED'),
    C('identity', 'AnonymizeUser', 'system', 'INV §17', 'IdentityCommand', [], ['identity.user'], 'anonymized_at ; audit PII_ANONYMIZED'),
    C('audit', 'AnonymizeAuditLogs', 'system', 'INV §17', None, [], ['audit.log'], 'colonnes before, after, reason seulement'),
    C('notifications', 'CleanNotificationPayloads', 'system', 'INV §17', 'HandleSendResult', [], ['notifications.status'], 'anonymized_at'),
    C('imports', 'PurgeImportStaging', 'job', 'INV §16', 'ImportBatchTransition', [], ['imports.batch'], 'borne par date'),
    C('platform', 'StoreIdempotencyKey', 'service', 'EC-05 §5', None, [], ['platform.idempotency'], 'UNIQUE (organisation, clé, route)'),
    C('events', 'EmitEvent', 'service', 'EC-01', None, [], ['events.publication'], 'suit le cas d usage'),
    C('audit', 'WriteAuditLog', 'service', 'INV D3', None, [], ['audit.log'], 'dans la transaction'),
    C('platform', 'PartitionManager', 'job', 'EC-03', None, [], [], 'IF NOT EXISTS'),
    C('platform', 'TechnicalPurge', 'job', 'EC-03', None, [], [], 'borne par date'),
]
