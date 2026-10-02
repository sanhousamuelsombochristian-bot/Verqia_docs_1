"""Module Registry : propriété, dépendances, requêtes publiées. Commandes et événements sont DÉRIVÉS de commands.py.

Chaque module déclare quatre choses obligatoires : ce qu'il possède (`owns`), ce qu'il expose en écriture (commandes,
dérivées), ce qu'il expose en lecture (`queries`), les événements qu'il produit et consomme (dérivés).

`deps` : modules dont il importe le paquet `contracts` (TA §2.3). Le générateur calcule les dépendances REQUISES à partir
des appels, des abonnements et des ports implémentés, et les compare à `deps`.
"""

# nom -> dict(group, layers, owns, queries, deps, note)
MODULES = {
    'kernel': dict(group='Socle', layers='pur', owns=[], queries=[], deps=[], note='bibliothèque pure : Money, CallContext, DomainError, calendrier ouvré, ports partagés'),
    'platform': dict(group='Socle', layers='infrastructure', owns=['idempotency_keys'], queries=[], deps=['kernel'], note='adaptateurs TransactionManager, LockManager, Clock, IdGenerator ; gabarits SQL'),
    'events': dict(group='Socle', layers='mince', owns=['events', 'event_receipts'], queries=[], deps=['kernel', 'platform'], note='outbox, relais, registres'),
    'audit': dict(group='Socle', layers='mince', owns=['audit_logs'], queries=[], deps=['kernel', 'platform'], note='AuditWriter, anonymisation'),
    'identity': dict(group='Identité', layers='mince', owns=['users', 'memberships'], queries=['MemberDirectory', 'RoleOf'], deps=['kernel', 'organizations'], note='implémente le port de provisioning'),
    'organizations': dict(group='Identité', layers='complet', owns=['organizations', 'org_settings', 'org_holidays'], queries=['OrgStatus', 'OrgSettings', 'CalendarReader'], deps=['kernel'], note='racine du tenant ; déclare ProvisioningStep'),
    'customers': dict(group='Sources', layers='complet', owns=['customers', 'customer_contacts'], queries=['CustomerFacts', 'ContactDirectory'], deps=['kernel', 'organizations', 'rules'], note=''),
    'invoices': dict(group='Sources', layers='complet', owns=['invoices', 'invoice_items', 'invoice_disputes', 'invoice_state_history'], queries=['InvoiceFacts', 'OpenInvoicesOfCustomer', 'SettledInvoicesOfCustomer', 'EverIssuedOfCustomer'], deps=['kernel', 'organizations', 'customers', 'rules'], note=''),
    'payments': dict(group='Sources', layers='complet', owns=['payments', 'payment_allocations', 'payment_reversals'], queries=['PaymentFacts', 'UnallocatedPayments', 'ReversedPaymentsOfCustomer'], deps=['kernel', 'organizations', 'customers', 'invoices', 'rules'], note='C12 : AllocatePayment'),
    'promises': dict(group='Sources', layers='complet', owns=['promises', 'promise_history'], queries=['PromiseFacts', 'BrokenPromisesOfCustomer'], deps=['kernel', 'organizations', 'customers', 'invoices', 'payments', 'rules'], note=''),
    'imports': dict(group='Sources', layers='complet', owns=['import_batches', 'import_rows'], queries=['ImportHeldFact', 'ImportReleaseFacts'], deps=['kernel', 'organizations', 'customers', 'invoices', 'payments', 'rules'], note='C12 : NormalizeImportBatch'),
    'rules': dict(group='Décision', layers='pur', owns=[], queries=['Evaluate', 'Explain'], deps=['kernel'], note='sans table ; déclare les fournisseurs de faits'),
    'risk': dict(group='Projections', layers='complet', owns=['risk_profiles', 'risk_snapshots'], queries=['RiskLevel'], deps=['kernel', 'organizations', 'invoices', 'payments', 'promises', 'rules'], note="tranche Risk V1 : `customers` retiré (risk-1.0 ne lit aucun fait client, RISK_DOMAIN_V1.md RD2)"),
    'priority': dict(group='Projections', layers='complet', owns=['priority_items', 'priority_snapshots'], queries=['PriorityLevel'], deps=['kernel', 'organizations', 'invoices', 'payments', 'promises', 'risk', 'collection', 'rules'], note="tranche Priority V1 : `customers` retiré (prio-1.0 ne lit aucun fait client, PRIORITY_DOMAIN_V1.md PD2.2, DV3-8) ; `payments` requis par l'abonnement de `RequestPriorityRecalc` (PAYMENT_CREATED/ALLOCATED/ALLOCATION_REVERSED), `rules` requis (fournisseur de faits, FACT_PROVIDERS) — aucun des deux n'est lu par `RecomputePriority` elle-même (PD2.2)"),
    'cashflow': dict(group='Projections', layers='complet', owns=['cashflow_runs', 'cashflow_lines'], queries=['CashflowCurrent'], deps=['kernel', 'organizations', 'customers', 'invoices', 'payments', 'promises', 'risk'], note=''),
    'approvals': dict(group='Action', layers='mince', owns=['approvals'], queries=['PendingApprovals'], deps=['kernel'], note='déclare ApprovalTargetReader (implémenté par collection et automation)'),
    'collection': dict(group='Action', layers='complet', owns=['collection_actions', 'collection_holds', 'collection_action_attempts'], queries=['CollectionFacts', 'ActionsOfInvoice'],
                       deps=['kernel', 'rules', 'notifications', 'approvals', 'organizations', 'customers', 'invoices', 'payments', 'promises'], note=''),
    'notifications': dict(group='Action', layers='mince', owns=['notifications', 'notification_deliveries', 'message_templates'], queries=['DeliveryStatus'], deps=['kernel', 'organizations', 'customers', 'identity', 'approvals'], note='NotificationSender (port)'),
    'automation': dict(group='Orchestration', layers='complet', owns=['automations', 'automation_versions', 'automation_executions', 'automation_execution_steps'], queries=['ReleaseProgress'],
                       deps=['kernel', 'rules', 'collection', 'notifications', 'approvals', 'organizations', 'customers', 'invoices', 'payments', 'promises', 'risk', 'priority', 'imports'], note=''),
    'billing': dict(group='Commerce', layers='vide', owns=['plans', 'subscriptions'], queries=[], deps=['kernel', 'organizations'], note='S7 non spécifié : emplacement réservé'),
    'jobs': dict(group='Pilotage', layers='pilote', owns=[], queries=[], deps=['kernel'], note='compose des cas d\'usage publiés ; aucune règle'),
    'config': dict(group='Pilotage', layers='pilote', owns=[], queries=[], deps=['kernel'], note='racine de composition'),
}

# Modules autorisés à tout importer (pilotes) : exclus du contrôle de dépendances requises.
DRIVERS = {'jobs', 'config'}

# Modules propriétaires des faits fournis à `rules` (fournisseurs de faits, TD12) : import de `rules.contracts`.
FACT_PROVIDERS = ['organizations', 'customers', 'invoices', 'payments', 'promises', 'imports', 'collection', 'risk', 'priority']

# Correspondance agrégat du catalogue -> module producteur ; exceptions par type d'événement.
AGGREGATE_OWNER = {'user': 'identity', 'membership': 'identity', 'organization': 'organizations', 'customer': 'customers', 'invoice': 'invoices', 'payment': 'payments', 'promise': 'promises',
                   'collection_action': 'collection', 'hold': 'collection', 'approval': 'approvals', 'notification': 'notifications',
                   'automation': 'automation', 'automation_execution': 'automation', 'import_batch': 'imports', 'subscription': 'billing',
                   'cashflow_run': 'cashflow'}
PRODUCER_OVERRIDE = {'RISK_CHANGED': 'risk', 'PRIORITY_CHANGED': 'priority', 'CASHFLOW_UPDATED': 'cashflow'}
# Événements REQUEST : producteurs multiples permis (déclenchés par des événements, des travaux, des étapes, une normalisation)


# Lectures publiées utilisées par un module (requêtes des autres modules). Elles comptent comme dépendances requises.
READS = {
    'customers': ['organizations.OrgStatus'],
    'invoices': ['organizations.OrgStatus', 'customers.CustomerFacts'],
    'payments': ['organizations.OrgStatus', 'customers.CustomerFacts'],
    'promises': ['organizations.OrgStatus', 'customers.CustomerFacts', 'invoices.InvoiceFacts'],
    'imports': ['organizations.OrgStatus'],
    # Risk V1 (RISK_DOMAIN_V1.md, RD2.3/RD2.4, DV2-1 à DV2-5, amendement 2026-09-22) : exactement les 7 lectures que
    # `reference_model/risk_ref.evaluate_risk` démontre nécessaires — aucune de plus (pas `customers.CustomerFacts` :
    # `risk-1.0` ne lit aucun fait client ; pas `invoices.InvoiceFacts`/`payments.PaymentFacts`/`promises.PromiseFacts`,
    # requêtes PAR ENTITÉ, remplacées par les requêtes PAR CLIENT/BORNÉES ci-dessous, DV2-2).
    'risk': ['organizations.CalendarReader', 'organizations.OrgSettings', 'invoices.OpenInvoicesOfCustomer',
             'invoices.SettledInvoicesOfCustomer', 'invoices.EverIssuedOfCustomer', 'payments.ReversedPaymentsOfCustomer',
             'promises.BrokenPromisesOfCustomer'],
    # Priority V1 (PRIORITY_DOMAIN_V1.md, PD2.2/PD2.3, DV3-8, amendement 2026-09-23) : exactement les 5 lectures que
    # `reference_model/priority_ref.evaluate_priority` démontre nécessaires — pas `organizations.CalendarReader`
    # (`prio-1.0` ne calcule aucune fenêtre temporelle, PD2.3) ; pas `customers.CustomerFacts`/`payments.PaymentFacts`
    # (aucun fait client ou paiement lu directement, PD2.2) ; `promises.PromiseFacts`/`collection.CollectionFacts`
    # potentiellement STUB (§ DV3-1/DV3-2 : Domain non encore écrit pour l'un, module non encore construit pour l'autre).
    'priority': ['organizations.OrgSettings', 'invoices.InvoiceFacts', 'promises.PromiseFacts', 'risk.RiskLevel', 'collection.CollectionFacts'],
    'cashflow': ['organizations.CalendarReader', 'customers.CustomerFacts', 'invoices.InvoiceFacts', 'payments.PaymentFacts', 'promises.PromiseFacts', 'risk.RiskLevel'],
    'notifications': ['organizations.OrgSettings', 'customers.ContactDirectory', 'identity.MemberDirectory'],
    'collection': ['organizations.CalendarReader', 'organizations.OrgSettings', 'customers.ContactDirectory', 'invoices.InvoiceFacts'],
    'automation': ['organizations.CalendarReader', 'invoices.InvoiceFacts', 'customers.CustomerFacts', 'payments.PaymentFacts', 'promises.PromiseFacts', 'imports.ImportReleaseFacts'],
    'identity': [],
}
for _n, _d in MODULES.items():
    _d['reads'] = READS.get(_n, [])
MODULES['organizations']['deps'] = ['kernel', 'rules']
MODULES['collection']['deps'] = [d for d in MODULES['collection']['deps'] if d != 'payments']


# Dépendances de SCHÉMA : clés étrangères vers les tables d'un autre module (ordre des migrations).
# Déclarées ici ; à vérifier contre le contrat lors de l'écriture des migrations. Sens : référençant -> référencé.
SCHEMA_DEPS = {
    'identity': ['organizations'],
    'customers': ['organizations'],
    'imports': ['organizations', 'identity'],
    'invoices': ['organizations', 'customers', 'imports'],
    'payments': ['organizations', 'customers', 'invoices', 'imports'],
    'promises': ['organizations', 'customers', 'invoices'],
    'automation': ['organizations'],
    'collection': ['organizations', 'customers', 'invoices', 'automation'],
    'approvals': ['organizations', 'collection', 'automation'],
    'notifications': ['organizations', 'customers', 'identity'],
    'risk': ['organizations', 'customers'],
    'priority': ['organizations', 'customers', 'invoices'],
    'cashflow': ['organizations', 'customers', 'invoices', 'payments'],
    'billing': ['organizations'],
}


# Ports publics : une capacité requise ou fournie, jamais une implémentation (`DjangoXxx`, `RedisXxx`, `PostgresXxx` sont des adaptateurs).
# clé `module.Port` -> (module propriétaire, rôle). Un port n'appartient qu'au module qui le DÉCLARE ; les autres l'implémentent.
PORT_REGISTRY = {
    'kernel.Clock': ('kernel', "`as_of` de l'unité de travail (TD23)"),
    'kernel.IdGenerator': ('kernel', 'identifiants UUIDv7, instant tiré du Clock'),
    'kernel.TransactionManager': ('kernel', 'unité de travail : organisation, isolation, délais (TD25, TD26)'),
    'kernel.LockManager': ('kernel', 'verrous ordonnés par opération enregistrée (TD27)'),
    'kernel.TenantContext': ('kernel', "organisation courante ; refus si absente (TD17)"),
    'kernel.EventOutbox': ('kernel', "émettre un événement dans la transaction de l'appelant (EC-01)"),
    'kernel.AuditWriter': ('kernel', "écrire l'audit dans la transaction (D3)"),
    'kernel.IdempotencyStore': ('kernel', "clés d'idempotence des commandes (TD32)"),
    'kernel.RateLimiter': ('kernel', "limitation d'API et étranglement d'envoi (TD49)"),
    'kernel.Metrics': ('kernel', 'compteurs et histogrammes, sans donnée personnelle'),
    'kernel.Tracer': ('kernel', 'traces rattachées à la chaîne événement / exécution / action'),
    'kernel.Logger': ('kernel', 'journaux structurés, sans donnée personnelle'),
    'organizations.ProvisioningStep': ('organizations', "étape d'un plan de provisioning, implémentée par son propriétaire (TD59)"),
    'rules.FactProvider': ('rules', 'fournisseur de faits par famille, implémenté par le module propriétaire (TD12)'),
    'approvals.ApprovalTargetReader': ('approvals', "interroger la cible d'une approbation, implémenté par `collection` et `automation` (TD58)"),
    'notifications.NotificationSender': ('notifications', 'remise à un fournisseur externe, hors transaction (EC-04, X13)'),
    'jobs.JobRunner': ('jobs', "exécuter un travail périodique ou continu (§6 de l'architecture)"),
}

# Amendement 2026-09-19 (Module Contracts V1, constat §8, option 1) : un module qui ÉMET une demande (REQUEST) importe la classe canonique
# du moteur destinataire. Arêtes ajoutées : imports -> risk, priority, cashflow ; automation -> cashflow (risk et priority y étaient déjà).
for _m, _extra in (('imports', ['risk', 'priority', 'cashflow']), ('automation', ['cashflow'])):
    for _d in _extra:
        if _d not in MODULES[_m]['deps']:
            MODULES[_m]['deps'].append(_d)
