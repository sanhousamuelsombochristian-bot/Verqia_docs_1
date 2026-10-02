"""Compléments du Event Registry : événements sans abonné et écarts avec le catalogue normatif.

Un événement sans abonné doit être CLASSÉ, pas simplement constaté :
  A  volontairement sans abonné : journal, explication, interface, audit (lecture par requête, jamais par handler)
  B  abonné hors du périmètre de cette passe : consommateur d'une passe ultérieure ou externe, à documenter
  C  oublié : à corriger AVANT le gel (la porte échoue tant qu'un C n'a pas de décision)
"""

NO_SUBSCRIBER = {
    'AUTOMATION_CREATED': ('A', 'journal et interface de gestion des automatisations'),
    'AUTOMATION_VERSION_CREATED': ('A', 'journal et historique des versions'),
    'AUTOMATION_ARCHIVED': ('A', 'journal ; une automatisation archivée n\'a plus d\'exécution (elle est désactivée avant, AUTOMATION_DISABLED)'),
    'AUTOMATION_EXECUTION_STARTED': ('A', 'suivi d\'exécution : interface et compteurs, lus par requête'),
    'AUTOMATION_EXECUTION_COMPLETED': ('A', 'suivi d\'exécution : interface et compteurs, lus par requête'),
    'AUTOMATION_EXECUTION_FAILED': ('A', 'alerte opérationnelle par l\'observabilité (taux d\'échec), retour manuel par RetryExecution'),
    'AUTOMATION_EXECUTION_CANCELLED': ('A', 'suivi d\'exécution : interface et compteurs, lus par requête'),
    'CASHFLOW_UPDATED': ('B', 'alertes de trésorerie : non utilisable comme déclencheur en V1 (Automation AU3), évolution prévue'),
    'COLLECTION_ACTION_PROPOSED': ('A', 'explication et historique des actions, lus par requête'),
    'COLLECTION_ACTION_SCHEDULED': ('A', 'explication et historique des actions, lus par requête'),
    'COLLECTION_ACTION_SUPPRESSED': ('A', 'explication : la cause est dans `suppression_code`, lue par requête'),
    'COLLECTION_ACTION_CANCELLED': ('A', 'explication et historique des actions, lus par requête'),
    'COLLECTION_ACTION_FAILED': ('A', 'le repli humain est décidé dans `collection` au moment de l\'échec, sans passer par un abonné'),
    'CUSTOMER_CREATED': ('A', 'journal ; les décisions relisent le client à la source (X1)'),
    'CUSTOMER_UPDATED': ('A', 'journal ; les décisions relisent le client à la source (X1)'),
    'CUSTOMER_CONTACT_ADDED': ('A', 'journal ; les garde-fous NO_CONTACT / NO_CONSENT relisent les contacts à l\'exécution'),
    'CUSTOMER_CONTACT_UPDATED': ('A', 'journal ; les garde-fous NO_CONTACT / NO_CONSENT relisent les contacts à l\'exécution'),
    'IMPORT_BATCH_READY': ('A', 'interface d\'import : le lot attend l\'approbation d\'un administrateur'),
    'IMPORT_BATCH_APPROVED': ('A', 'interface d\'import et audit'),
    'IMPORT_BATCH_CANCELLED': ('A', 'interface d\'import et audit'),
    'IMPORT_BATCH_FAILED': ('A', 'interface d\'import et alerte opérationnelle'),
    'INVOICE_CREATED': ('A', 'journal ; une facture DRAFT n\'est pas recouvrable (Rule Engine, étape 0)'),
    'NOTIFICATION_CREATED': ('A', 'l\'envoi réclame les notifications dans la table (`SKIP LOCKED`) : pas d\'abonné'),
    'ORGANIZATION_CREATED': ('A', 'journal ; émis à la fin du provisioning (PROVISIONING vers ACTIVE)'),
    'ORGANIZATION_UPDATED': ('A', 'journal'),
    'USER_CREATED': ('A', 'journal et audit ; les droits sont relus à chaque commande (rôle courant)'),
    'USER_STATUS_CHANGED': ('A', 'journal et audit ; un utilisateur désactivé est refusé à l authentification et à la revérification des grants'),
    'MEMBER_ADDED': ('A', 'journal et audit ; le rôle est relu à chaque commande'),
    'MEMBER_ROLE_CHANGED': ('A', 'journal et audit ; le rôle courant est relu à chaque commande et à la revérification des grants'),
    'MEMBER_REMOVED': ('A', 'journal et audit ; l appartenance est relue à chaque commande et à la revérification des grants'),
    'SUBSCRIPTION_CHANGED': ('B', 'Billing (S7) : autorisations issues de l\'abonnement, à spécifier'),
}

# Événements déclarés au contrat de données (§1 à §12) mais absents du catalogue des Invariants §10.3 :
# amendement du catalogue en attente. Tant qu'il n'est pas appliqué, ce sont des CONSTATS ; ensuite, des ERREURS.
PENDING_CATALOGUE_ADDITIONS = {}  # amendement appliqué : USER_* et MEMBER_* sont au catalogue des Invariants §10.3

# Événements techniques, hors catalogue normatif (aucun pour l'instant).
TECHNICAL_EVENTS = set()

# Un événement dont le nom finit par « Requested » n'est une DEMANDE (REQUEST) que si sa catégorie le dit. Ces faits, eux, décrivent
# quelque chose qui existe déjà ; l'exception est nommée et justifiée, jamais implicite.
FACT_EVENTS_NAMED_REQUESTED = {
    'APPROVAL_REQUESTED': "fait (MUTATION) : la demande d'approbation existe déjà en base ; ce n'est pas une demande adressée à un moteur",
}
