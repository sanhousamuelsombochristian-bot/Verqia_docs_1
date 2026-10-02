"""Lock Registry : ordre des verrous DÉRIVÉ des opérations, pas décrété.

Chaque opération déclare la suite de ressources qu'elle acquiert. Le générateur construit le graphe de précédence,
vérifie qu'il est sans cycle et en tire un ordre canonique. Une nouvelle opération qui créerait un cycle fait échouer la CI.

Modes :
  A  verrou consultatif de transaction (première instruction, toujours avant toute ligne)
  K  insertion d'une clé d'idempotence (première écriture d'une commande d'API)
  S  FOR SHARE : lecture protectrice (le parent ne change pas pendant la transaction)
  U  FOR NO KEY UPDATE : modification de la ligne (verrou de ligne standard)
  G  UPDATE gardé (`WHERE état = ancien`) : verrou de ligne pris à l'écriture
  I  INSERT : clé unique et clé étrangère (un INSERT attend une insertion concurrente de la même clé)
"""

MODES = {'A', 'K', 'S', 'U', 'G', 'I'}

# ressource -> (table(s), remarque)
RESOURCES = {
    'advisory': ('verrou consultatif (travail, organisation) ou (moteur, sujet)', 'toujours en premier'),
    'idempotency_keys': ('idempotency_keys', 'première écriture d\'une commande d\'API (TD32)'),
    'organizations': ('organizations, org_settings', ''),
    'identity_members': ('users, memberships', ''),
    'subscriptions': ('subscriptions', 'Billing (S7) : emplacement réservé'),
    'import_batches': ('import_batches, import_rows', ''),
    'customers': ('customers, customer_contacts', ''),
    'payments': ('payments, payment_allocations, payment_reversals', ''),
    'invoices': ('invoices, invoice_items', ''),
    'invoice_disputes': ('invoice_disputes', ''),
    'promises': ('promises', ''),
    'collection_holds': ('collection_holds', ''),
    'automations': ('automations, automation_versions', ''),
    'automation_executions': ('automation_executions, automation_execution_steps', ''),
    'collection_actions': ('collection_actions, collection_action_attempts', ''),
    'approvals': ('approvals', ''),
    'notifications': ('notifications, notification_deliveries', ''),
    'projections': ('risk_*, priority_*, cashflow_*', 'écrites par leur moteur seulement'),
    'event_receipts': ('event_receipts', 'dernier : le reçu est écrit avec l\'effet (EC-02 (5))'),
}

# Préférence d'affichage pour l'ordre canonique (n'ajoute AUCUNE contrainte : seules les opérations comptent).
PREFERRED = ['advisory', 'idempotency_keys', 'organizations', 'identity_members', 'subscriptions', 'import_batches',
             'customers', 'payments', 'invoices', 'invoice_disputes', 'promises', 'collection_holds', 'automations',
             'automation_executions', 'collection_actions', 'approvals', 'notifications', 'projections', 'event_receipts']

# Chaîne gelée (Engine Contracts EC5) et ordre proposé au premier jet de TD27 : comparés à l'ordre dérivé.
FROZEN_EC5 = ['payments', 'invoices', 'promises', 'collection_actions', 'automation_executions', 'notifications']
FIRST_DRAFT_TD27 = ['organizations', 'customers', 'import_batches', 'payments', 'invoices', 'promises', 'collection_holds',
                    'approvals', 'collection_actions', 'automation_executions', 'notifications']

# nom -> (module, [(ressource, mode)], drapeaux, source)
# drapeaux : api = commande d'API (clé d'idempotence en premier) ; handler = handler d'événement (reçu en dernier)
OPERATIONS = {
    'CreateOrganization': ('organizations', [('idempotency_keys', 'K'), ('organizations', 'I')], {'api'}, 'plan de provisioning : une transaction par étape'),
    'CompleteProvisioning': ('organizations', [('organizations', 'G')], set(), 'PROVISIONING vers ACTIVE'),
    'ProvisionOwner': ('identity', [('identity_members', 'I')], set(), 'étape de provisioning'),
    'ProvisionTrial': ('billing', [('subscriptions', 'I')], set(), 'étape de provisioning (S7)'),
    'InstallDefaults': ('automation', [('automations', 'I')], set(), 'étape de provisioning'),
    'ChangeOrganization': ('organizations', [('idempotency_keys', 'K'), ('organizations', 'U')], {'api'}, 'SM §1'),
    'IdentityCommand': ('identity', [('idempotency_keys', 'K'), ('identity_members', 'U')], {'api'}, 'SM §15'),
    'CustomerCommand': ('customers', [('idempotency_keys', 'K'), ('customers', 'U')], {'api'}, 'SM §2'),
    'CreateInvoice': ('invoices', [('idempotency_keys', 'K'), ('customers', 'S'), ('invoices', 'I')], {'api'}, 'EC-06'),
    'IssueInvoice': ('invoices', [('idempotency_keys', 'K'), ('customers', 'S'), ('invoices', 'U')], {'api'}, 'EC-06'),
    'InvoiceTransition': ('invoices', [('invoices', 'G')], set(), 'EC-06 (job)'),
    'InvoiceDisputeCommand': ('invoices', [('idempotency_keys', 'K'), ('invoices', 'U'), ('invoice_disputes', 'U')], {'api'}, 'SM §4'),
    'CreatePayment': ('payments', [('idempotency_keys', 'K'), ('customers', 'S'), ('payments', 'I')], {'api'}, 'Contrat §4'),
    'PaymentSettlement': ('payments', [('idempotency_keys', 'K'), ('payments', 'U'), ('invoices', 'U')], {'api'}, 'EC-05 (id croissant)'),
    'CreatePromise': ('promises', [('idempotency_keys', 'K'), ('customers', 'S'), ('invoices', 'S'), ('promises', 'I')], {'api'}, 'SM §7'),
    'PromiseTransition': ('promises', [('promises', 'U')], set(), 'SM §7'),
    'PlaceHold': ('collection', [('idempotency_keys', 'K'), ('collection_holds', 'I')], {'api'}, 'SM §9'),
    'ReleaseHold': ('collection', [('collection_holds', 'G')], set(), 'SM §9'),
    'NormalizeImportBatch': ('imports', [('import_batches', 'U'), ('customers', 'I'), ('payments', 'I'), ('invoices', 'I')], {'handler'}, 'EC-07'),
    'ImportBatchTransition': ('imports', [('import_batches', 'G')], set(), 'SM §14'),
    'ValidateImportBatch': ('imports', [('import_batches', 'G')], {'handler'}, 'SM §14'),
    'StartImportRelease': ('imports', [('import_batches', 'G')], {'handler'}, 'SM §16'),
    'ReleaseTranche': ('automation', [('automation_executions', 'I')], set(), 'Automation §10.1'),
    'ActivateAutomation': ('automation', [('idempotency_keys', 'K'), ('automations', 'U'), ('automation_executions', 'I')], {'api'}, 'EC-12'),
    'AutomationDefinitionCommand': ('automation', [('idempotency_keys', 'K'), ('automations', 'U')], {'api'}, 'EC-12'),
    'DispatchEvent': ('automation', [('automation_executions', 'I')], {'handler'}, 'EC-12'),
    'ClaimExecution': ('automation', [('automation_executions', 'G')], set(), 'EC-12 : PENDING/WAITING vers RUNNING (RUNNING est le bail ; le Reaper le reprend)'),
    'RecordExecutionStep': ('automation', [('automation_executions', 'U')], set(), 'EC-12 : ligne d etape et nouvel etat ; l effet a eu lieu avant, dans la transaction du module proprietaire'),
    'ChangeExecutionState': ('automation', [('automation_executions', 'U')], {'handler'}, 'EC-12'),
    'ReapExecutions': ('automation', [('automation_executions', 'G')], set(), 'EC-03'),
    'ReapActions': ('collection', [('collection_actions', 'G')], set(), 'EC-03'),
    'CreateCollectionAction': ('collection', [('idempotency_keys', 'K'), ('collection_actions', 'I')], {'api'}, 'EC-11 : l\'approbation est demandée ensuite, dans la transaction du module approvals'),
    'AdvanceProposedAction': ('collection', [('collection_actions', 'U')], set(), 'PROPOSED vers SCHEDULED ou PENDING_APPROVAL, après revalidation'),
    'RequestApproval': ('approvals', [('approvals', 'I')], set(), 'EC-13 : transaction du module propriétaire'),
    'ExecuteDueAction': ('collection', [('collection_actions', 'U')], set(), 'EC-11, X3 : claim et revalidation ; la notification est créée ensuite dans sa propre transaction'),
    'CollectionReaction': ('collection', [('collection_actions', 'U')], {'handler'}, 'Collection §12'),
    'ClaimTask': ('collection', [('collection_actions', 'G')], set(), 'EC-11 : réclamation gardée (UPDATE … WHERE assigned_to IS NULL)'),
    'RescheduleAction': ('collection', [('collection_actions', 'G')], set(), 'EC-11, Invariants §7.1 : garde sur status ∈ {PROPOSED, SCHEDULED} avant modification de scheduled_for'),
    'DecideApproval': ('approvals', [('idempotency_keys', 'K'), ('approvals', 'U')], {'api'}, 'EC-13'),
    'ApprovalExpiryScan': ('approvals', [('approvals', 'G')], set(), 'EC-13'),
    'HandleSendResult': ('notifications', [('notifications', 'U')], set(), 'EC-04'),
    'CreateNotification': ('notifications', [('notifications', 'I')], set(), 'EC-04'),
    'NotifyApprovers': ('notifications', [('notifications', 'I')], {'handler'}, 'notification APPROVAL_REQUESTED'),
    'ProjectionRecompute': ('projections', [('advisory', 'A'), ('projections', 'U')], {'handler'}, 'EC-14, TD29'),
    'RunCashflow': ('cashflow', [('advisory', 'A'), ('projections', 'U')], {'handler'}, 'EC-14'),
    'JobStep': ('jobs', [('advisory', 'A')], set(), 'EC-03 (verrou travail, organisation)'),
    'Anonymize': ('customers', [('customers', 'U')], set(), 'Contrat §17'),
    'ReplayDeadEvent': ('events', [('idempotency_keys', 'K'), ('event_receipts', 'U')], {'api'}, 'EC-02'),
}


def op_sequence(name):
    module, seq, flags, _ = OPERATIONS[name]
    seq = list(seq)
    if 'handler' in flags:
        seq.append(('event_receipts', 'I'))
    return seq


def precedence_edges():
    """(avant, après) -> opérations qui l'imposent."""
    edges = {}
    for name in OPERATIONS:
        seq = [r for r, _ in op_sequence(name)]
        for a, b in zip(seq, seq[1:]):
            if a != b:
                edges.setdefault((a, b), []).append(name)
    return edges


def derive(extra_edges=(), preferred=PREFERRED):
    """Ordre topologique (Kahn), départagé par `preferred`. Renvoie (ordre, cycle_ou_None)."""
    edges = dict(precedence_edges())
    for a, b in extra_edges:
        edges.setdefault((a, b), []).append('(contrainte externe)')
    nodes = list(RESOURCES)
    succ = {n: set() for n in nodes}
    indeg = {n: 0 for n in nodes}
    for (a, b) in edges:
        if b not in succ[a]:
            succ[a].add(b)
            indeg[b] += 1
    order, ready = [], sorted([n for n in nodes if indeg[n] == 0], key=preferred.index)
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in sorted(succ[n], key=preferred.index):
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
        ready.sort(key=preferred.index)
    if len(order) == len(nodes):
        return order, None
    left = [n for n in nodes if n not in order]
    return order, left


def chain_edges(chain):
    return list(zip(chain, chain[1:]))


def violations(order, chain):
    """Arêtes d'une chaîne contredites par l'ordre `order`."""
    rank = {n: i for i, n in enumerate(order)}
    return [(a, b) for a, b in chain_edges(chain) if rank[a] > rank[b]]


def canonical():
    """Échelle publiée : ordre dérivé des opérations ET de la chaîne gelée EC5 (qui doit rester compatible)."""
    return derive(extra_edges=chain_edges(FROZEN_EC5))


def consistent(chain):
    """Une chaîne (ordre proposé ou gelé) est compatible si, ajoutée aux opérations, elle ne crée aucun cycle."""
    order, cycle = derive(extra_edges=chain_edges(chain))
    return cycle is None, cycle
