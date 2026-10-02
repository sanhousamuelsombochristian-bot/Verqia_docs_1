"""Catalogue des invariants de l'Application Contract V1 (AP-01 à AP-15) : LA source. Le document, le vérificateur de preuves (`verify_ap.py`) et les tests
en dérivent. Le contenu est celui du contrat gelé : il ne se réécrit pas pour faire coïncider des tests ; un nouvel invariant exige sa preuve (`ap_proofs.py`).

Chaque entrée : (identifiant, énoncé, vérifié par).
"""
INVARIANTS = [
    ('AP-01', 'Chaque entrée du Command Registry a exactement une spécification ; aucune spécification sans entrée', 'A1'),
    ('AP-02', 'Transaction, idempotence, événements, écritures et abonnements sont ceux du registre', 'A2'),
    ('AP-03', 'La séquence de verrous est celle du Lock Registry, en rang strictement croissant sur l\'échelle générée (jamais écrite à la main)', 'A3'),
    ('AP-04', 'Régime d\'organisation : `REQUIRED` pour tout cas d\'usage appelé, `EVENT` pour un handler, `ENUMERATOR` pour un travail ; exceptions fermées : relais d\'outbox (`RELAY`), gestionnaire de partitions (`NONE`)', 'A4'),
    ('AP-05', 'Un code d\'erreur cité existe à l\'Annexe A ; aucune erreur inventée par un cas d\'usage', 'A5'),
    ('AP-06', 'Toute commande **publique** (entrée `PUBLIC`, nature `command`) a un audit. Toute autre entrée (étape de provisioning, interne, réaction, travail) n\'en produit un que si elle figure dans la liste nominative de D3 ; un audit conditionnel porte son motif', 'A6, A10'),
    ('AP-07', 'Écritures, événements, audit, idempotence et reçu forment une seule unité ; aucun effet externe n\'y figure', 'A7'),
    ('AP-08', 'Tout appel inter-modules a : (1) une cible existante ; (2) une dépendance déclarée (TD10, pilotes `jobs` et `config` dispensés) ; (3) un sens compatible avec le graphe (jamais de retour vers un module qui dépend déjà de l\'appelant) ; (4) une transaction compatible avec TD58 : tout `own:` a sa phase ; (5) une cible `own:` qui possède réellement l\'état qu\'elle écrit', 'A8, A11'),
    ('AP-09', 'Les spécifications sont de la donnée : ni fonction, ni contrôle de flux, ni cadre logiciel', 'hygiène'),
    ('AP-10', 'Réclamer → Effet → Finaliser. Un cas d\'usage à réclamation (`CLAIM`) l\'ouvre en première phase ; l\'effet (`EFFECT`, dans la transaction du propriétaire, idempotent) n\'est autorisé qu\'après une réclamation valide ; `FINALIZE` clôt, dans le module de la réclamation, et ne finalise qu\'une exécution dont la réclamation correspond', 'A11'),
    ('AP-11', 'Les entrées sont distinguées : commande publique, étape de provisioning, interne, réaction, travail. Une étape de provisioning est un service idempotent par (organisation, étape), à verrou, dans sa transaction, sans audit direct', 'A10'),
    ('AP-12', '`REPLAY` n\'existe que pour une commande ; les issues d\'un handler sont celles de son reçu ; chaque nature n\'a que ses issues (§3.1)', 'A9'),
    ('AP-13', 'Un cas d\'usage composé déclare ses phases ordonnées, une transaction chacune ; un effet extérieur n\'est dans aucune transaction ; l\'état d\'un autre module n\'est écrit que dans sa transaction (TD55, TD58)', 'A11'),
]
INVARIANTS.append(('AP-14', 'Portée d\'idempotence, **typée** (`IdempotencyScope`, K2). Une commande qui insère la clé de requête `K` a la portée `ORGANIZATION` : `(organisation, clé, route)` (TD32). `CreateOrganization` est l\'exception nommée : `(acteur, clé, route)`, consultée avant toute création ; sur rejeu, le résultat mémorisé est restitué et aucun identifiant n\'est généré. La clé d\'idempotence est une identité technique de requête et n\'engendre jamais `organization_id`, identité métier', 'A12'))
INVARIANTS.append(('AP-15', 'Portée de transaction (K1). `TransactionScope` **`TENANT`** (`CallContext`, organisation obligatoire), **`SYSTEM`** (`SystemContext`, aucune organisation) ou **`NEW`** (`CreationContext`, organisation liée par `TenantContext.bind_new`). Elle est **déduite du régime d\'organisation** par le contrat (`SCOPE_OF_TENANT`), jamais choisie par l\'appelant : `SYSTEM` pour `RELAY` et `NONE`, `NEW` pour `NEW`. Ce sont trois régimes, pas trois variantes d\'un `organization_id` nul : `CallContext.organization_id` reste obligatoire, et une fois liée l\'organisation ne change plus dans l\'unité de travail', 'A13'))
