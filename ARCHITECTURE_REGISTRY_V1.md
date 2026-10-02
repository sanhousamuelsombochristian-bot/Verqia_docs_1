# VERQIA — Architecture Registry V1.2

## Journal des amendements (depuis le gel V1 du 2026-09-18)

| # | Date | Objet | Nature | Validé |
|---|---|---|---|---|
| A1 | 2026-09-19 | `PORT_REGISTRY` : les 17 ports publics (12 du noyau + `ProvisioningStep`, `FactProvider`, `ApprovalTargetReader`, `NotificationSender`, `JobRunner`) | ajout de données ; nécessaire à la propriété P3 (Module Contracts) ; aucune entrée existante modifiée | implicitement, avec Module Contracts V1 |
| A2 | 2026-09-19 | dépendances `imports → risk, priority, cashflow` et `automation → cashflow` (émission d'une demande `REQUEST` : classe canonique chez le moteur destinataire) | donnée : `deps` du Module Registry (constat §8, option 1) ; TD10 intact : dépendance vers `contracts`, jamais vers l'implémentation | oui, 2026-09-19 |
| A3 | 2026-09-19 | le générateur compte l'émission d'un événement d'un autre module comme dépendance requise | outil (vérification) ; aucune donnée | oui, avec A2 |
| A4 | 2026-09-19 | `events.OutboxPublisher` : champ `txn` `une` → `trois : réclamer par bail ; chaque handler dans sa transaction ; poser publié` | donnée : texte de transaction, aligné sur TD33 (frozen) ; aucune écriture, aucun verrou, aucun événement modifié | à valider avec Application Contract V1 |

Rien d'autre n'a changé dans les quatre registres depuis le gel.

Statut : **généré** par `architecture_registry/build_registry.py` à partir de `commands.py`, `modules.py`, `locks.py` et du catalogue d'événements des Invariants. **Ne pas modifier à la main.** **V1 gelé** avec `TECHNICAL_ARCHITECTURE_V1.md` (2026-09-18) : toute modification passe par un amendement daté.

Ces quatre registres rendent l'architecture **exécutable** : les tests d'architecture (`AR-*`) sont générés depuis eux. Ordre de travail : registres → tests d'architecture → structure Django → schéma PostgreSQL.

- **Erreurs** : 0 · **Constats** (écarts à décider) : 1

| Registre | Contenu | Éléments |
|---|---|---:|
| Module | propriété, dépendances, requêtes | 22 |
| Commande | cas d'usage, handlers, travaux, services | 122 |
| Événement | catalogue des Invariants, producteurs, consommateurs | 77 |
| Verrou | ressources, opérations, échelle dérivée | 19 ressources · 48 opérations |

## 1. Module Registry

Chaque module déclare : **ce qu'il possède**, **ce qu'il écrit** (commandes), **ce qu'il lit** (requêtes publiées), **ce qu'il publie et consomme** (événements). Les colonnes commandes et événements sont dérivées du Command Registry.

| Module | Groupe | Couches | Possède | Requêtes publiées | Dépend de (contracts) |
|---|---|---|---|---|---|
| `kernel` | Socle | pur | — | — | — |
| `platform` | Socle | infrastructure | `idempotency_keys` | — | `kernel` |
| `events` | Socle | mince | `events`, `event_receipts` | — | `kernel`, `platform` |
| `audit` | Socle | mince | `audit_logs` | — | `kernel`, `platform` |
| `identity` | Identité | mince | `users`, `memberships` | `MemberDirectory`, `RoleOf` | `kernel`, `organizations` |
| `organizations` | Identité | complet | `organizations`, `org_settings`, `org_holidays` | `OrgStatus`, `OrgSettings`, `CalendarReader` | `kernel`, `rules` |
| `customers` | Sources | complet | `customers`, `customer_contacts` | `CustomerFacts`, `ContactDirectory` | `kernel`, `organizations`, `rules` |
| `invoices` | Sources | complet | `invoices`, `invoice_items`, `invoice_disputes`, `invoice_state_history` | `InvoiceFacts`, `OpenInvoicesOfCustomer`, `SettledInvoicesOfCustomer`, `EverIssuedOfCustomer` | `kernel`, `organizations`, `customers`, `rules` |
| `payments` | Sources | complet | `payments`, `payment_allocations`, `payment_reversals` | `PaymentFacts`, `UnallocatedPayments`, `ReversedPaymentsOfCustomer` | `kernel`, `organizations`, `customers`, `invoices`, `rules` |
| `promises` | Sources | complet | `promises`, `promise_history` | `PromiseFacts`, `BrokenPromisesOfCustomer` | `kernel`, `organizations`, `customers`, `invoices`, `payments`, `rules` |
| `imports` | Sources | complet | `import_batches`, `import_rows` | `ImportHeldFact`, `ImportReleaseFacts` | `kernel`, `organizations`, `customers`, `invoices`, `payments`, `rules`, `risk`, `priority`, `cashflow` |
| `rules` | Décision | pur | — | `Evaluate`, `Explain` | `kernel` |
| `risk` | Projections | complet | `risk_profiles`, `risk_snapshots` | `RiskLevel` | `kernel`, `organizations`, `invoices`, `payments`, `promises`, `rules` |
| `priority` | Projections | complet | `priority_items`, `priority_snapshots` | `PriorityLevel` | `kernel`, `organizations`, `invoices`, `payments`, `promises`, `risk`, `collection`, `rules` |
| `cashflow` | Projections | complet | `cashflow_runs`, `cashflow_lines` | `CashflowCurrent` | `kernel`, `organizations`, `customers`, `invoices`, `payments`, `promises`, `risk` |
| `approvals` | Action | mince | `approvals` | `PendingApprovals` | `kernel` |
| `collection` | Action | complet | `collection_actions`, `collection_holds`, `collection_action_attempts` | `CollectionFacts`, `ActionsOfInvoice` | `kernel`, `rules`, `notifications`, `approvals`, `organizations`, `customers`, `invoices`, `promises` |
| `notifications` | Action | mince | `notifications`, `notification_deliveries`, `message_templates` | `DeliveryStatus` | `kernel`, `organizations`, `customers`, `identity`, `approvals` |
| `automation` | Orchestration | complet | `automations`, `automation_versions`, `automation_executions`, `automation_execution_steps` | `ReleaseProgress` | `kernel`, `rules`, `collection`, `notifications`, `approvals`, `organizations`, `customers`, `invoices`, `payments`, `promises`, `risk`, `priority`, `imports`, `cashflow` |
| `billing` | Commerce | vide | `plans`, `subscriptions` | — | `kernel`, `organizations` |
| `jobs` | Pilotage | pilote | — | — | `kernel` |
| `config` | Pilotage | pilote | — | — | `kernel` |

### 1.1 Publication et consommation par module

| Module | Commandes et travaux | Événements produits | Événements consommés |
|---|---|---|---|
| `kernel` | — | — | — |
| `platform` | StoreIdempotencyKey, PartitionManager, TechnicalPurge | — | — |
| `events` | OutboxPublisher, ReplayDeadEvent, EmitEvent | — | — |
| `audit` | AnonymizeAuditLogs, WriteAuditLog | — | — |
| `identity` | CreateUser, ChangeUserStatus, AddMember, ProvisionOwnerMembership, ChangeMemberRole, RemoveMember, AnonymizeUser | MEMBER_ADDED, MEMBER_REMOVED, MEMBER_ROLE_CHANGED, USER_CREATED, USER_STATUS_CHANGED | — |
| `organizations` | CreateOrganization, CompleteProvisioning, ResumeProvisioning, UpdateOrganization, ChangeOrgSettings, SuspendOrganization, ReactivateOrganization, CloseOrganization | ORGANIZATION_CLOSED, ORGANIZATION_CREATED, ORGANIZATION_REACTIVATED, ORGANIZATION_SUSPENDED, ORGANIZATION_UPDATED, ORG_SETTINGS_CHANGED | — |
| `customers` | CreateCustomer, UpdateCustomer, DeactivateCustomer, ArchiveCustomer, ReactivateCustomer, AddCustomerContact, UpdateCustomerContact, AnonymizeCustomer | CUSTOMER_ARCHIVED, CUSTOMER_CONTACT_ADDED, CUSTOMER_CONTACT_UPDATED, CUSTOMER_CREATED, CUSTOMER_DEACTIVATED, CUSTOMER_REACTIVATED, CUSTOMER_UPDATED | — |
| `invoices` | CreateInvoice, IssueInvoice, CancelInvoice, VoidInvoice, OpenInvoiceDispute, ResolveInvoiceDispute, InvoiceLifecycleScan, ApplySettlement | INVOICE_CANCELLED, INVOICE_CREATED, INVOICE_DISPUTED, INVOICE_DISPUTE_RESOLVED, INVOICE_DUE, INVOICE_DUE_SOON, INVOICE_ISSUED, INVOICE_OVERDUE, INVOICE_PAID, INVOICE_PARTIALLY_PAID, INVOICE_SETTLEMENT_REVERTED, INVOICE_VOIDED | — |
| `payments` | CreatePayment, AllocatePayment, ReverseAllocation, ReversePayment | PAYMENT_ALLOCATED, PAYMENT_ALLOCATION_REVERSED, PAYMENT_CREATED, PAYMENT_REVERSED | — |
| `promises` | CreatePromise, CancelPromise, FulfillPromiseOnInvoicePaid, FulfillPromiseOnAllocation, CancelPromiseOnInvoiceEnded, CancelPromiseOnCustomerArchived, PromiseBreachScan | PROMISE_BROKEN, PROMISE_CANCELLED, PROMISE_CREATED, PROMISE_FULFILLED | CUSTOMER_ARCHIVED, INVOICE_CANCELLED, INVOICE_PAID, INVOICE_VOIDED, PAYMENT_ALLOCATED |
| `imports` | UploadImportBatch, ValidateImportBatch, ApproveImportBatch, CommitImportBatch, CancelImportBatch, NormalizeImportBatch, StartImportRelease, CompleteImportRelease, PurgeImportStaging | CASHFLOW_RECALCULATION_REQUESTED, IMPORT_BATCH_APPROVED, IMPORT_BATCH_CANCELLED, IMPORT_BATCH_COMMITTED, IMPORT_BATCH_FAILED, IMPORT_BATCH_NORMALIZED, IMPORT_BATCH_READY, IMPORT_BATCH_RELEASED, IMPORT_BATCH_UPLOADED, PRIORITY_RECALCULATION_REQUESTED, RISK_RECALCULATION_REQUESTED | IMPORT_BATCH_COMMITTED, IMPORT_BATCH_NORMALIZED, IMPORT_BATCH_UPLOADED |
| `rules` | — | — | — |
| `risk` | RequestRiskRecalc, RecomputeRisk, RequestDailyRiskRefresh | RISK_CHANGED, RISK_RECALCULATION_REQUESTED | INVOICE_ISSUED, INVOICE_OVERDUE, INVOICE_PAID, INVOICE_PARTIALLY_PAID, INVOICE_SETTLEMENT_REVERTED, INVOICE_VOIDED, PAYMENT_ALLOCATED, PAYMENT_ALLOCATION_REVERSED, PAYMENT_REVERSED, PROMISE_BROKEN, PROMISE_FULFILLED, RISK_RECALCULATION_REQUESTED |
| `priority` | RequestPriorityRecalc, RecomputePriority, RequestDailyPriorityRefresh | PRIORITY_CHANGED, PRIORITY_RECALCULATION_REQUESTED | COLLECTION_ACTION_EXECUTED, COLLECTION_HOLD_PLACED, COLLECTION_HOLD_RELEASED, INVOICE_CANCELLED, INVOICE_DISPUTED, INVOICE_DISPUTE_RESOLVED, INVOICE_DUE, INVOICE_DUE_SOON, INVOICE_ISSUED, INVOICE_OVERDUE, INVOICE_PAID, INVOICE_PARTIALLY_PAID, INVOICE_SETTLEMENT_REVERTED, INVOICE_VOIDED, PAYMENT_ALLOCATED, PAYMENT_ALLOCATION_REVERSED, PAYMENT_CREATED, PAYMENT_REVERSED, PRIORITY_RECALCULATION_REQUESTED, PROMISE_BROKEN, PROMISE_CANCELLED, PROMISE_CREATED, PROMISE_FULFILLED, RISK_CHANGED |
| `cashflow` | RequestCashflowRecalc, RunCashflow, CashflowScheduler | CASHFLOW_RECALCULATION_REQUESTED, CASHFLOW_UPDATED | CASHFLOW_RECALCULATION_REQUESTED, INVOICE_CANCELLED, INVOICE_ISSUED, INVOICE_PAID, INVOICE_PARTIALLY_PAID, INVOICE_SETTLEMENT_REVERTED, INVOICE_VOIDED, ORG_SETTINGS_CHANGED, PAYMENT_ALLOCATED, PAYMENT_ALLOCATION_REVERSED, PAYMENT_CREATED, PAYMENT_REVERSED, PROMISE_BROKEN, PROMISE_CANCELLED, PROMISE_CREATED, PROMISE_FULFILLED |
| `approvals` | RequestApproval, DecideApproval, ApprovalExpiryScan | APPROVAL_GRANTED, APPROVAL_REJECTED, APPROVAL_REQUESTED | — |
| `collection` | CreateCollectionAction, AdvanceProposedAction, ResumeProposedActions, CreateManualAction, AuthorizeOverride, CancelCollectionAction, ClaimTask, CompleteTask, RescheduleAction, ExecuteDueAction, ReapActions, SuppressOnInvoicePaid, SuppressOnInvoiceEnded, SuppressOnInvoiceDisputed, SuppressOnPromiseCreated, SuppressOnHoldPlaced, SuppressOnCustomerInactive, SuppressOnOrgSuspended, OnApprovalDecided, OnNotificationResult, PlaceHold, ReleaseHold, HoldExpiryScan, ScanReconciliationReviews, ReadApprovalTarget | COLLECTION_ACTION_CANCELLED, COLLECTION_ACTION_EXECUTED, COLLECTION_ACTION_FAILED, COLLECTION_ACTION_PROPOSED, COLLECTION_ACTION_SCHEDULED, COLLECTION_ACTION_SUPPRESSED, COLLECTION_HOLD_PLACED, COLLECTION_HOLD_RELEASED | APPROVAL_GRANTED, APPROVAL_REJECTED, COLLECTION_HOLD_PLACED, CUSTOMER_ARCHIVED, CUSTOMER_DEACTIVATED, INVOICE_CANCELLED, INVOICE_DISPUTED, INVOICE_PAID, INVOICE_VOIDED, NOTIFICATION_FAILED, NOTIFICATION_SENT, ORGANIZATION_CLOSED, ORGANIZATION_SUSPENDED, PROMISE_CREATED |
| `notifications` | CreateNotification, HandleSendResult, NotifyApprovers, CleanNotificationPayloads | NOTIFICATION_CREATED, NOTIFICATION_FAILED, NOTIFICATION_SENT | APPROVAL_REQUESTED |
| `automation` | ProvisionDefaultAutomations, ReadApprovalTarget, CreateAutomation, CreateAutomationVersion, ActivateAutomation, PauseAutomation, DisableAutomation, ArchiveAutomation, DispatchEvent, ScanTimeTriggers, RunExecutionStep, PauseOrCancelOnSubjectChange, OnAutomationPausedOrDisabled, ResumeOnCauseLifted, OnApprovalDecidedForExecution, ResumeReconciliationPaused, ReleaseImportTranche, ReapExecutions, RetryExecution | AUTOMATION_ACTIVATED, AUTOMATION_ARCHIVED, AUTOMATION_CREATED, AUTOMATION_DISABLED, AUTOMATION_EXECUTION_CANCELLED, AUTOMATION_EXECUTION_COMPLETED, AUTOMATION_EXECUTION_FAILED, AUTOMATION_EXECUTION_STARTED, AUTOMATION_PAUSED, AUTOMATION_VERSION_CREATED, CASHFLOW_RECALCULATION_REQUESTED, PRIORITY_RECALCULATION_REQUESTED, RISK_RECALCULATION_REQUESTED | APPROVAL_GRANTED, APPROVAL_REJECTED, AUTOMATION_ACTIVATED, AUTOMATION_DISABLED, AUTOMATION_PAUSED, COLLECTION_HOLD_PLACED, COLLECTION_HOLD_RELEASED, CUSTOMER_ARCHIVED, CUSTOMER_DEACTIVATED, CUSTOMER_REACTIVATED, IMPORT_BATCH_RELEASED, INVOICE_CANCELLED, INVOICE_DISPUTED, INVOICE_DISPUTE_RESOLVED, INVOICE_DUE, INVOICE_DUE_SOON, INVOICE_ISSUED, INVOICE_OVERDUE, INVOICE_PAID, INVOICE_PARTIALLY_PAID, INVOICE_SETTLEMENT_REVERTED, INVOICE_VOIDED, ORGANIZATION_CLOSED, ORGANIZATION_REACTIVATED, ORGANIZATION_SUSPENDED, PAYMENT_ALLOCATED, PAYMENT_ALLOCATION_REVERSED, PAYMENT_CREATED, PAYMENT_REVERSED, PRIORITY_CHANGED, PROMISE_BROKEN, PROMISE_CANCELLED, PROMISE_CREATED, PROMISE_FULFILLED, RISK_CHANGED |
| `billing` | ProvisionTrialSubscription | SUBSCRIPTION_CHANGED | — |
| `jobs` | ImportReleaser, ReconciliationWindowScan | — | — |
| `config` | — | — | — |

### 1.2 Dépendances requises et raison (appels, lectures, ports, événements)

| Module | Dépendances requises et raison |
|---|---|
| `identity` | **organizations** (implémente organizations.ProvisioningStep) |
| `organizations` | **rules** (fournisseur de faits) |
| `customers` | **organizations** (lecture organizations.OrgStatus) ; **rules** (fournisseur de faits) |
| `invoices` | **customers** (appel customers.CustomerFacts, appel customers.CustomerFacts, lecture customers.CustomerFacts) ; **organizations** (appel organizations.OrgStatus, appel organizations.OrgStatus, appel organizations.OrgStatus …) ; **rules** (fournisseur de faits) |
| `payments` | **customers** (appel customers.CustomerFacts, lecture customers.CustomerFacts) ; **invoices** (appel invoices.ApplySettlement, appel invoices.InvoiceFacts, appel invoices.ApplySettlement …) ; **organizations** (appel organizations.OrgStatus, appel organizations.OrgStatus, appel organizations.OrgStatus …) ; **rules** (fournisseur de faits) |
| `promises` | **customers** (lecture customers.CustomerFacts, événement CUSTOMER_ARCHIVED) ; **invoices** (lecture invoices.InvoiceFacts, événement INVOICE_PAID, événement INVOICE_VOIDED …) ; **organizations** (lecture organizations.OrgStatus) ; **payments** (événement PAYMENT_ALLOCATED) ; **rules** (fournisseur de faits) |
| `imports` | **cashflow** (émet CASHFLOW_RECALCULATION_REQUESTED (classe canonique dans cashflow)) ; **customers** (appel customers.CreateCustomer) ; **invoices** (appel invoices.CreateInvoice) ; **organizations** (lecture organizations.OrgStatus) ; **payments** (appel payments.CreatePayment, appel payments.AllocatePayment) ; **priority** (émet PRIORITY_RECALCULATION_REQUESTED (classe canonique dans priority)) ; **risk** (émet RISK_RECALCULATION_REQUESTED (classe canonique dans risk)) ; **rules** (fournisseur de faits) |
| `risk` | **invoices** (appel invoices.OpenInvoicesOfCustomer, appel invoices.SettledInvoicesOfCustomer, appel invoices.EverIssuedOfCustomer …) ; **organizations** (appel organizations.CalendarReader, appel organizations.OrgSettings, lecture organizations.CalendarReader …) ; **payments** (appel payments.ReversedPaymentsOfCustomer, lecture payments.ReversedPaymentsOfCustomer, événement PAYMENT_ALLOCATED …) ; **promises** (appel promises.BrokenPromisesOfCustomer, lecture promises.BrokenPromisesOfCustomer, événement PROMISE_BROKEN …) ; **rules** (fournisseur de faits) |
| `priority` | **collection** (appel collection.CollectionFacts, lecture collection.CollectionFacts, événement COLLECTION_HOLD_PLACED …) ; **invoices** (appel invoices.InvoiceFacts, lecture invoices.InvoiceFacts, événement INVOICE_ISSUED …) ; **organizations** (appel organizations.OrgSettings, lecture organizations.OrgSettings) ; **payments** (événement PAYMENT_CREATED, événement PAYMENT_ALLOCATED, événement PAYMENT_ALLOCATION_REVERSED …) ; **promises** (appel promises.PromiseFacts, lecture promises.PromiseFacts, événement PROMISE_CREATED …) ; **risk** (appel risk.RiskLevel, lecture risk.RiskLevel, événement RISK_CHANGED) ; **rules** (fournisseur de faits) |
| `cashflow` | **customers** (lecture customers.CustomerFacts) ; **invoices** (lecture invoices.InvoiceFacts, événement INVOICE_ISSUED, événement INVOICE_PAID …) ; **organizations** (lecture organizations.CalendarReader, événement ORG_SETTINGS_CHANGED) ; **payments** (lecture payments.PaymentFacts, événement PAYMENT_CREATED, événement PAYMENT_ALLOCATED …) ; **promises** (lecture promises.PromiseFacts, événement PROMISE_CREATED, événement PROMISE_BROKEN …) ; **risk** (lecture risk.RiskLevel) |
| `collection` | **approvals** (appel own:approvals.RequestApproval, implémente approvals.ApprovalTargetReader, événement APPROVAL_GRANTED …) ; **customers** (lecture customers.ContactDirectory, événement CUSTOMER_DEACTIVATED, événement CUSTOMER_ARCHIVED) ; **invoices** (appel invoices.InvoiceFacts, lecture invoices.InvoiceFacts, événement INVOICE_PAID …) ; **notifications** (appel own:notifications.CreateNotification, appel own:notifications.CreateNotification, événement NOTIFICATION_SENT …) ; **organizations** (appel organizations.CalendarReader, appel organizations.OrgSettings, appel organizations.CalendarReader …) ; **promises** (événement PROMISE_CREATED) ; **rules** (appel rules.Evaluate, appel rules.Evaluate, appel rules.Evaluate …) |
| `notifications` | **approvals** (événement APPROVAL_REQUESTED) ; **customers** (lecture customers.ContactDirectory) ; **identity** (lecture identity.MemberDirectory) ; **organizations** (lecture organizations.OrgSettings) |
| `automation` | **approvals** (implémente approvals.ApprovalTargetReader, appel own:approvals.RequestApproval, événement APPROVAL_GRANTED …) ; **cashflow** (émet CASHFLOW_RECALCULATION_REQUESTED (classe canonique dans cashflow)) ; **collection** (appel own:collection.CreateCollectionAction, événement COLLECTION_HOLD_PLACED, événement COLLECTION_HOLD_RELEASED) ; **customers** (lecture customers.CustomerFacts, événement CUSTOMER_DEACTIVATED, événement CUSTOMER_ARCHIVED …) ; **imports** (appel imports.ImportReleaseFacts, lecture imports.ImportReleaseFacts, événement IMPORT_BATCH_RELEASED) ; **invoices** (lecture invoices.InvoiceFacts, événement INVOICE_ISSUED, événement INVOICE_DUE_SOON …) ; **notifications** (appel own:notifications.CreateNotification) ; **organizations** (implémente organizations.ProvisioningStep, lecture organizations.CalendarReader, événement ORGANIZATION_SUSPENDED …) ; **payments** (lecture payments.PaymentFacts, événement PAYMENT_CREATED, événement PAYMENT_ALLOCATED …) ; **priority** (émet PRIORITY_RECALCULATION_REQUESTED (classe canonique dans priority), événement PRIORITY_CHANGED) ; **promises** (lecture promises.PromiseFacts, événement PROMISE_CREATED, événement PROMISE_FULFILLED …) ; **risk** (émet RISK_RECALCULATION_REQUESTED (classe canonique dans risk), événement RISK_CHANGED) ; **rules** (appel rules.Evaluate, appel rules.Evaluate) |
| `billing` | **organizations** (implémente organizations.ProvisioningStep) |

## 2. Command Registry

`src` : `EC-nn`, `SM`, `INV`… = figé dans un document ; **`NOM FIGÉ`** = nom créé par les registres et figé en revue ; `PROPOSED` = nom encore provisoire. `lock` renvoie au Lock Registry. `writes` : états écrits (§2.2). Un appel préfixé `own:` s'exécute dans **sa propre transaction**.

| Module | Commande | Type | Source | Transaction | Verrou | Écrit | Émet | Idempotence | Appelle |
|---|---|---|---|---|---|---|---|---|---|
| `organizations` | **CreateOrganization** | command | INV C12 (amendé) | une par étape (plan de provisioning) | CreateOrganization | organizations.record, organizations.settings, organizations.status | — | clé d'idempotence | own:organizations.ProvisioningStep, own:organizations.CompleteProvisioning |
| `organizations` | **CompleteProvisioning** | system | NOM FIGÉ | une | CompleteProvisioning | organizations.status | ORGANIZATION_CREATED | garde d'état PROVISIONING → ACTIVE | — |
| `organizations` | **ResumeProvisioning** | job | NOM FIGÉ | une | — | — | — | idempotence par étape | own:organizations.ProvisioningStep, own:organizations.CompleteProvisioning |
| `organizations` | **UpdateOrganization** | command | NOM FIGÉ | une | ChangeOrganization | organizations.record | ORGANIZATION_UPDATED | version | — |
| `organizations` | **ChangeOrgSettings** | command | NOM FIGÉ | une | ChangeOrganization | organizations.settings | ORG_SETTINGS_CHANGED | version | — |
| `organizations` | **SuspendOrganization** | command | SM §1 | une | ChangeOrganization | organizations.status | ORGANIZATION_SUSPENDED | garde d'état | — |
| `organizations` | **ReactivateOrganization** | command | SM §1 | une | ChangeOrganization | organizations.status | ORGANIZATION_REACTIVATED | garde d'état | — |
| `organizations` | **CloseOrganization** | command | SM §1 | une | ChangeOrganization | organizations.status | ORGANIZATION_CLOSED | garde d'état | — |
| `automation` | **ProvisionDefaultAutomations** | service | NOM FIGÉ | une | InstallDefaults | automation.definition | AUTOMATION_CREATED | (organisation, étape) | implémente organizations.ProvisioningStep |
| `identity` | **CreateUser** | command | NOM FIGÉ | une | IdentityCommand | identity.user | USER_CREATED | e-mail unique | — |
| `identity` | **ChangeUserStatus** | command | SM §15 | une | IdentityCommand | identity.user | USER_STATUS_CHANGED | garde d'état | — |
| `identity` | **AddMember** | command | NOM FIGÉ | une | IdentityCommand | identity.membership | MEMBER_ADDED | unicité (organisation, utilisateur) | — |
| `identity` | **ProvisionOwnerMembership** | service | NOM FIGÉ | une | ProvisionOwner | identity.membership | MEMBER_ADDED | (organisation, étape) | implémente organizations.ProvisioningStep |
| `identity` | **ChangeMemberRole** | command | SM §15 | une | IdentityCommand | identity.membership | MEMBER_ROLE_CHANGED | version | — |
| `identity` | **RemoveMember** | command | SM §15 | une | IdentityCommand | identity.membership | MEMBER_REMOVED | garde d'état | — |
| `customers` | **CreateCustomer** | command | NOM FIGÉ | une | CustomerCommand | customers.record | CUSTOMER_CREATED | external_ref unique | — |
| `customers` | **UpdateCustomer** | command | NOM FIGÉ | une | CustomerCommand | customers.record | CUSTOMER_UPDATED | version | — |
| `customers` | **DeactivateCustomer** | command | SM §2 | une | CustomerCommand | customers.status | CUSTOMER_DEACTIVATED | garde d'état | — |
| `customers` | **ArchiveCustomer** | command | SM §2 | une | CustomerCommand | customers.status | CUSTOMER_ARCHIVED | garde d'état | — |
| `customers` | **ReactivateCustomer** | command | SM §2 | une | CustomerCommand | customers.status | CUSTOMER_REACTIVATED | garde d'état | — |
| `customers` | **AddCustomerContact** | command | NOM FIGÉ | une | CustomerCommand | customers.record | CUSTOMER_CONTACT_ADDED | unicité contact actif | — |
| `customers` | **UpdateCustomerContact** | command | NOM FIGÉ | une | CustomerCommand | customers.record | CUSTOMER_CONTACT_UPDATED | version | — |
| `invoices` | **CreateInvoice** | command | EC-06 | une | CreateInvoice | invoices.body | INVOICE_CREATED | clé d'idempotence | customers.CustomerFacts, organizations.OrgStatus |
| `invoices` | **IssueInvoice** | command | EC-06 | une | IssueInvoice | invoices.lifecycle, invoices.collection_cycle | INVOICE_ISSUED, INVOICE_DUE_SOON, INVOICE_DUE, INVOICE_OVERDUE | garde d'état | customers.CustomerFacts, organizations.OrgStatus |
| `invoices` | **CancelInvoice** | command | EC-06 | une | InvoiceTransition | invoices.lifecycle | INVOICE_CANCELLED | garde d'état | — |
| `invoices` | **VoidInvoice** | command | EC-06 | une | InvoiceTransition | invoices.lifecycle | INVOICE_VOIDED | garde d'état | — |
| `invoices` | **OpenInvoiceDispute** | command | SM §4 | une | InvoiceDisputeCommand | invoices.dispute | INVOICE_DISPUTED | clé d'idempotence | — |
| `invoices` | **ResolveInvoiceDispute** | command | SM §4 | une | InvoiceDisputeCommand | invoices.dispute | INVOICE_DISPUTE_RESOLVED | garde d'état | — |
| `invoices` | **InvoiceLifecycleScan** | job | EC-03 | une par facture | InvoiceTransition | invoices.lifecycle, invoices.collection_cycle | INVOICE_DUE_SOON, INVOICE_DUE, INVOICE_OVERDUE | UPDATE … WHERE état = ancien | organizations.OrgStatus |
| `invoices` | **ApplySettlement** | service | EC-05 | une · **C12** | PaymentSettlement | invoices.settlement, invoices.collection_cycle, invoices.lifecycle | INVOICE_PARTIALLY_PAID, INVOICE_PAID, INVOICE_SETTLEMENT_REVERTED, INVOICE_DUE_SOON, INVOICE_DUE, INVOICE_OVERDUE | dans la transaction de l'appelant | organizations.OrgStatus |
| `payments` | **CreatePayment** | command | NOM FIGÉ | une | CreatePayment | payments.record | PAYMENT_CREATED | clé d'idempotence | customers.CustomerFacts, organizations.OrgStatus |
| `payments` | **AllocatePayment** | command | EC-05 | une · **C12** | PaymentSettlement | payments.allocations, payments.allocated, invoices.settlement, invoices.collection_cycle | PAYMENT_ALLOCATED | clé d'idempotence | invoices.ApplySettlement, invoices.InvoiceFacts, organizations.OrgStatus |
| `payments` | **ReverseAllocation** | command | EC-05 | une · **C12** | PaymentSettlement | payments.allocations, payments.allocated, invoices.settlement, invoices.collection_cycle, invoices.lifecycle | PAYMENT_ALLOCATION_REVERSED | clé d'idempotence | invoices.ApplySettlement, organizations.OrgStatus |
| `payments` | **ReversePayment** | command | EC-05 | une · **C12** | PaymentSettlement | payments.allocations, payments.allocated, invoices.settlement, invoices.collection_cycle, invoices.lifecycle | PAYMENT_REVERSED, PAYMENT_ALLOCATION_REVERSED | clé d'idempotence | invoices.ApplySettlement, organizations.OrgStatus |
| `promises` | **CreatePromise** | command | SM §7 | une | CreatePromise | promises.status | PROMISE_CREATED | clé d'idempotence | — |
| `promises` | **CancelPromise** | command | SM §7 | une | PromiseTransition | promises.status | PROMISE_CANCELLED | garde d'état | — |
| `promises` | **FulfillPromiseOnInvoicePaid** | handler | SM §7 | une | PromiseTransition | promises.status | PROMISE_FULFILLED | reçu | — |
| `promises` | **FulfillPromiseOnAllocation** | handler | SM §7 | une | PromiseTransition | promises.status | PROMISE_FULFILLED | reçu | — |
| `promises` | **CancelPromiseOnInvoiceEnded** | handler | SM §7 | une | PromiseTransition | promises.status | PROMISE_CANCELLED | reçu | — |
| `promises` | **CancelPromiseOnCustomerArchived** | handler | SM §7 | une | PromiseTransition | promises.status | PROMISE_CANCELLED | reçu | — |
| `promises` | **PromiseBreachScan** | job | EC-03 | une | PromiseTransition | promises.status | PROMISE_BROKEN | UPDATE … WHERE état = ancien | — |
| `imports` | **UploadImportBatch** | command | SM §14 | une | ImportBatchTransition | imports.batch | IMPORT_BATCH_UPLOADED | file_hash unique | — |
| `imports` | **ValidateImportBatch** | handler | SM §14 | une | ValidateImportBatch | imports.batch | IMPORT_BATCH_READY, IMPORT_BATCH_FAILED | garde d'état | — |
| `imports` | **ApproveImportBatch** | command | SM §14 | une | ImportBatchTransition | imports.batch | IMPORT_BATCH_APPROVED | garde d'état | — |
| `imports` | **CommitImportBatch** | command | SM §14 | une | ImportBatchTransition | imports.batch | IMPORT_BATCH_COMMITTED | garde d'état | — |
| `imports` | **CancelImportBatch** | command | SM §14 | une | ImportBatchTransition | imports.batch | IMPORT_BATCH_CANCELLED | garde d'état | — |
| `imports` | **NormalizeImportBatch** | handler | EC-07 | une · **C12** | NormalizeImportBatch | imports.batch, customers.record, invoices.body, invoices.lifecycle, invoices.settlement, payments.record, payments.allocations, payments.allocated | IMPORT_BATCH_NORMALIZED, IMPORT_BATCH_FAILED, RISK_RECALCULATION_REQUESTED, PRIORITY_RECALCULATION_REQUESTED, CASHFLOW_RECALCULATION_REQUESTED | garde d'état COMMITTED → NORMALIZING | customers.CreateCustomer, invoices.CreateInvoice, payments.CreatePayment, payments.AllocatePayment |
| `imports` | **StartImportRelease** | handler | SM §16 | une | StartImportRelease | imports.batch | — | garde d'état NORMALIZED → RELEASING | — |
| `imports` | **CompleteImportRelease** | system | NOM FIGÉ | une | ImportBatchTransition | imports.batch | IMPORT_BATCH_RELEASED | garde d'état RELEASING → RELEASED | — |
| `collection` | **CreateCollectionAction** | command | EC-11 | une par module propriétaire : action, puis approbation, puis transition | CreateCollectionAction | collection.action_status | COLLECTION_ACTION_PROPOSED, COLLECTION_ACTION_SUPPRESSED | dedup_key | rules.Evaluate, own:collection.AdvanceProposedAction |
| `collection` | **AdvanceProposedAction** | system | NOM FIGÉ | une | AdvanceProposedAction | collection.action_status | COLLECTION_ACTION_SCHEDULED, COLLECTION_ACTION_SUPPRESSED | garde d'état PROPOSED | rules.Evaluate, organizations.CalendarReader, organizations.OrgSettings, own:approvals.RequestApproval |
| `collection` | **ResumeProposedActions** | job | NOM FIGÉ | une | AdvanceProposedAction | collection.action_status | — | garde d'état PROPOSED | own:collection.AdvanceProposedAction |
| `collection` | **CreateManualAction** | command | EC-11 | une par module propriétaire | CreateCollectionAction | collection.action_status | COLLECTION_ACTION_PROPOSED, COLLECTION_ACTION_SUPPRESSED | manual:{clé} | rules.Evaluate, collection.AuthorizeOverride, own:collection.AdvanceProposedAction |
| `collection` | **AuthorizeOverride** | service | EC-10 | une | — | — | — | sans effet propre ; audit à la création puis à chaque vérification | — |
| `collection` | **CancelCollectionAction** | command | SM §8 | une | CollectionReaction | collection.action_status | COLLECTION_ACTION_CANCELLED | garde d'état | — |
| `collection` | **ClaimTask** | command | EC-11 | une | ClaimTask | collection.action_status | — | une seule réclamation gagne (UPDATE … WHERE assigned_to IS NULL) | — |
| `collection` | **CompleteTask** | command | SM §8 | une | CollectionReaction | collection.action_status | COLLECTION_ACTION_EXECUTED | garde d'état | — |
| `collection` | **RescheduleAction** | command | EC-11, Invariants §7.1 | une | RescheduleAction | collection.action_status | — | garde d'état | organizations.CalendarReader, organizations.OrgSettings |
| `collection` | **ExecuteDueAction** | worker | EC-11 | claim + revalidation ; notification ; envoi hors transaction ; résultat | ExecuteDueAction | collection.action_status, collection.attempts | COLLECTION_ACTION_SUPPRESSED | claim gardé | rules.Evaluate, collection.AuthorizeOverride, own:notifications.CreateNotification |
| `collection` | **ReapActions** | job | EC-03 | une | ReapActions | collection.action_status, collection.attempts | — | transition gardée | — |
| `collection` | **SuppressOnInvoicePaid** | handler | Collection §12 | une | CollectionReaction | collection.action_status | COLLECTION_ACTION_SUPPRESSED | reçu | — |
| `collection` | **SuppressOnInvoiceEnded** | handler | Collection §12 | une | CollectionReaction | collection.action_status | COLLECTION_ACTION_SUPPRESSED | reçu | — |
| `collection` | **SuppressOnInvoiceDisputed** | handler | Collection §12, D1 | une | CollectionReaction | collection.action_status | COLLECTION_ACTION_SUPPRESSED | reçu | invoices.InvoiceFacts |
| `collection` | **SuppressOnPromiseCreated** | handler | Collection §12 | une | CollectionReaction | collection.action_status | COLLECTION_ACTION_SUPPRESSED | reçu | — |
| `collection` | **SuppressOnHoldPlaced** | handler | Collection §12 | une | CollectionReaction | collection.action_status | COLLECTION_ACTION_SUPPRESSED | reçu | — |
| `collection` | **SuppressOnCustomerInactive** | handler | Collection §12 | une | CollectionReaction | collection.action_status | COLLECTION_ACTION_SUPPRESSED | reçu | — |
| `collection` | **SuppressOnOrgSuspended** | handler | Collection §12 | une | CollectionReaction | collection.action_status | COLLECTION_ACTION_SUPPRESSED | reçu | — |
| `collection` | **OnApprovalDecided** | handler | Collection §6 | une | CollectionReaction | collection.action_status | COLLECTION_ACTION_SCHEDULED, COLLECTION_ACTION_CANCELLED | reçu | — |
| `collection` | **OnNotificationResult** | handler | Collection §8 | une | CollectionReaction | collection.action_status, collection.attempts | COLLECTION_ACTION_EXECUTED, COLLECTION_ACTION_FAILED, COLLECTION_ACTION_SCHEDULED | reçu | — |
| `collection` | **PlaceHold** | command | SM §9 | une | PlaceHold | collection.hold_status | COLLECTION_HOLD_PLACED | clé d'idempotence + EXCLUDE | — |
| `collection` | **ReleaseHold** | command | SM §9 | une | ReleaseHold | collection.hold_status | COLLECTION_HOLD_RELEASED | garde d'état | — |
| `collection` | **HoldExpiryScan** | job | EC-03 | une | ReleaseHold | collection.hold_status | COLLECTION_HOLD_RELEASED | UPDATE … WHERE état = ancien | — |
| `collection` | **ScanReconciliationReviews** | job | Collection V1.2 §8.2 | par organisation | — | — | — | dedup_key | own:notifications.CreateNotification |
| `approvals` | **RequestApproval** | service | EC-13 | une | RequestApproval | approvals.status | APPROVAL_REQUESTED | par cible et étape | approvals.ApprovalTargetReader |
| `approvals` | **DecideApproval** | command | EC-13 | une | DecideApproval | approvals.status | APPROVAL_GRANTED, APPROVAL_REJECTED | une seule décision | approvals.ApprovalTargetReader |
| `approvals` | **ApprovalExpiryScan** | job | EC-13 | une | ApprovalExpiryScan | approvals.status | — | UPDATE … WHERE état = ancien | approvals.ApprovalTargetReader |
| `collection` | **ReadApprovalTarget** | service | NOM FIGÉ | une | — | — | — | lecture seule | implémente approvals.ApprovalTargetReader |
| `automation` | **ReadApprovalTarget** | service | NOM FIGÉ | une | — | — | — | lecture seule | implémente approvals.ApprovalTargetReader |
| `notifications` | **CreateNotification** | service | EC-04 | une | CreateNotification | notifications.status | NOTIFICATION_CREATED | dedup_key | — |
| `notifications` | **HandleSendResult** | worker | EC-04 | une, hors envoi | HandleSendResult | notifications.status | NOTIFICATION_SENT, NOTIFICATION_FAILED | (notification_id, attempt_no) | — |
| `notifications` | **NotifyApprovers** | handler | NOM FIGÉ | une | NotifyApprovers | notifications.status | NOTIFICATION_CREATED | dedup_key | — |
| `automation` | **CreateAutomation** | command | EC-12 | une | AutomationDefinitionCommand | automation.definition | AUTOMATION_CREATED | clé d'idempotence | — |
| `automation` | **CreateAutomationVersion** | command | EC-12 | une | AutomationDefinitionCommand | automation.definition | AUTOMATION_VERSION_CREATED | version | — |
| `automation` | **ActivateAutomation** | command | EC-12 | une | ActivateAutomation | automation.definition, automation.execution | AUTOMATION_ACTIVATED | garde d'état + empreinte | — |
| `automation` | **PauseAutomation** | command | EC-12 | une | AutomationDefinitionCommand | automation.definition | AUTOMATION_PAUSED | garde d'état | — |
| `automation` | **DisableAutomation** | command | EC-12 | une | AutomationDefinitionCommand | automation.definition | AUTOMATION_DISABLED | garde d'état | — |
| `automation` | **ArchiveAutomation** | command | EC-12 | une | AutomationDefinitionCommand | automation.definition | AUTOMATION_ARCHIVED | garde d'état | — |
| `automation` | **DispatchEvent** | handler | EC-12 | une | DispatchEvent | automation.execution | — | trigger_key = event:{id} | — |
| `automation` | **ScanTimeTriggers** | job | EC-12 | une | DispatchEvent | automation.execution | — | trigger_key temporel | — |
| `automation` | **RunExecutionStep** | worker | EC-12 | trois : réclamer, effet dans la transaction du module propriétaire, enregistrer | RecordExecutionStep | automation.execution | AUTOMATION_EXECUTION_STARTED, AUTOMATION_EXECUTION_COMPLETED, AUTOMATION_EXECUTION_FAILED, RISK_RECALCULATION_REQUESTED, PRIORITY_RECALCULATION_REQUESTED, CASHFLOW_RECALCULATION_REQUESTED | effets idempotents + garde d'état | rules.Evaluate, own:collection.CreateCollectionAction, own:notifications.CreateNotification, own:approvals.RequestApproval |
| `automation` | **PauseOrCancelOnSubjectChange** | handler | SM §16 | une | ChangeExecutionState | automation.execution | AUTOMATION_EXECUTION_CANCELLED | reçu | — |
| `automation` | **OnAutomationPausedOrDisabled** | handler | SM §12 | une | ChangeExecutionState | automation.execution | AUTOMATION_EXECUTION_CANCELLED | reçu | — |
| `automation` | **ResumeOnCauseLifted** | handler | Automation §7 | une | ChangeExecutionState | automation.execution | — | reçu | — |
| `automation` | **OnApprovalDecidedForExecution** | handler | Automation §6 | une | ChangeExecutionState | automation.execution | — | reçu | — |
| `automation` | **ResumeReconciliationPaused** | job | Collection V1.2 §8.2 | par organisation | ChangeExecutionState | automation.execution | — | garde d'état | rules.Evaluate |
| `automation` | **ReleaseImportTranche** | system | Automation §10.1 | une par tranche | ReleaseTranche | automation.execution | — | trigger_key = import-release:… | imports.ImportReleaseFacts |
| `jobs` | **ImportReleaser** | job | Automation §10.1 | une par pas | — | — | — | composition ; chaque pas est idempotent | own:automation.ReleaseImportTranche, own:imports.CompleteImportRelease, automation.ReleaseProgress |
| `jobs` | **ReconciliationWindowScan** | job | Collection V1.2 §8.2 | une par pas | — | — | — | composition ; chaque pas est idempotent | own:collection.ScanReconciliationReviews, own:automation.ResumeReconciliationPaused |
| `automation` | **ReapExecutions** | job | EC-03 | une | ReapExecutions | automation.execution | — | transition gardée | — |
| `automation` | **RetryExecution** | command | EC-12 | une | DispatchEvent | automation.execution | — | trigger_key = retry:{id} | — |
| `risk` | **RequestRiskRecalc** | handler | EC-14 | une | — | — | RISK_RECALCULATION_REQUESTED | regroupement par cible | — |
| `risk` | **RecomputeRisk** | handler | EC-14 | une | ProjectionRecompute | risk.profile | RISK_CHANGED | input_hash | organizations.CalendarReader, organizations.OrgSettings, invoices.OpenInvoicesOfCustomer, invoices.SettledInvoicesOfCustomer, invoices.EverIssuedOfCustomer, payments.ReversedPaymentsOfCustomer, promises.BrokenPromisesOfCustomer |
| `risk` | **RequestDailyRiskRefresh** | job | EC-03 | une | — | — | RISK_RECALCULATION_REQUESTED | regroupement par cible | — |
| `priority` | **RequestPriorityRecalc** | handler | EC-14 | une | — | — | PRIORITY_RECALCULATION_REQUESTED | regroupement par cible | — |
| `priority` | **RecomputePriority** | handler | EC-14 | une | ProjectionRecompute | priority.item | PRIORITY_CHANGED | input_hash | organizations.OrgSettings, invoices.InvoiceFacts, risk.RiskLevel, promises.PromiseFacts, collection.CollectionFacts |
| `priority` | **RequestDailyPriorityRefresh** | job | EC-03 | une | — | — | PRIORITY_RECALCULATION_REQUESTED | regroupement par cible | — |
| `cashflow` | **RequestCashflowRecalc** | handler | EC-14 | une | — | — | CASHFLOW_RECALCULATION_REQUESTED | portée : organisation ; horizons 30 et 90 jours, scénario BASE ; regroupement 5 min (Cashflow §4.8) ; ORG_SETTINGS_CHANGED filtré sur CASHFLOW_ORG_SETTINGS_RELEVANT | — |
| `cashflow` | **RunCashflow** | handler | EC-14 | une | RunCashflow | cashflow.run | CASHFLOW_UPDATED | input_hash + promotion monotone | — |
| `cashflow` | **CashflowScheduler** | job | EC-03 | une | — | — | CASHFLOW_RECALCULATION_REQUESTED | input_hash | — |
| `billing` | **ProvisionTrialSubscription** | service | NOM FIGÉ (S7) | une | ProvisionTrial | billing.subscription | SUBSCRIPTION_CHANGED | (organisation, étape) | implémente organizations.ProvisioningStep |
| `events` | **OutboxPublisher** | worker | EC-03 | trois : réclamer par bail ; chaque handler dans sa transaction ; poser publié | JobStep | events.publication, events.receipts | — | bail + reçus | — |
| `events` | **ReplayDeadEvent** | command | EC-02 | une | ReplayDeadEvent | events.receipts | — | clé d'idempotence | — |
| `customers` | **AnonymizeCustomer** | system | INV §17 | une | Anonymize | customers.record | — | anonymized_at ; audit PII_ANONYMIZED | — |
| `identity` | **AnonymizeUser** | system | INV §17 | une | IdentityCommand | identity.user | — | anonymized_at ; audit PII_ANONYMIZED | — |
| `audit` | **AnonymizeAuditLogs** | system | INV §17 | une | — | audit.log | — | colonnes before, after, reason seulement | — |
| `notifications` | **CleanNotificationPayloads** | system | INV §17 | une | HandleSendResult | notifications.status | — | anonymized_at | — |
| `imports` | **PurgeImportStaging** | job | INV §16 | une | ImportBatchTransition | imports.batch | — | borne par date | — |
| `platform` | **StoreIdempotencyKey** | service | EC-05 §5 | une | — | platform.idempotency | — | UNIQUE (organisation, clé, route) | — |
| `events` | **EmitEvent** | service | EC-01 | une | — | events.publication | — | suit le cas d usage | — |
| `audit` | **WriteAuditLog** | service | INV D3 | une | — | audit.log | — | dans la transaction | — |
| `platform` | **PartitionManager** | job | EC-03 | une | — | — | — | IF NOT EXISTS | — |
| `platform` | **TechnicalPurge** | job | EC-03 | une | — | — | — | borne par date | — |

### 2.1 Handlers : abonnements

| Handler | Événements | Reçu | Reprise |
|---|---|---|---|
| `promises.FulfillPromiseOnInvoicePaid` | INVOICE_PAID | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `promises.FulfillPromiseOnAllocation` | PAYMENT_ALLOCATED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `promises.CancelPromiseOnInvoiceEnded` | INVOICE_VOIDED, INVOICE_CANCELLED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `promises.CancelPromiseOnCustomerArchived` | CUSTOMER_ARCHIVED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `imports.ValidateImportBatch` | IMPORT_BATCH_UPLOADED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `imports.NormalizeImportBatch` | IMPORT_BATCH_COMMITTED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `imports.StartImportRelease` | IMPORT_BATCH_NORMALIZED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `collection.SuppressOnInvoicePaid` | INVOICE_PAID | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `collection.SuppressOnInvoiceEnded` | INVOICE_VOIDED, INVOICE_CANCELLED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `collection.SuppressOnInvoiceDisputed` | INVOICE_DISPUTED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `collection.SuppressOnPromiseCreated` | PROMISE_CREATED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `collection.SuppressOnHoldPlaced` | COLLECTION_HOLD_PLACED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `collection.SuppressOnCustomerInactive` | CUSTOMER_DEACTIVATED, CUSTOMER_ARCHIVED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `collection.SuppressOnOrgSuspended` | ORGANIZATION_SUSPENDED, ORGANIZATION_CLOSED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `collection.OnApprovalDecided` | APPROVAL_GRANTED, APPROVAL_REJECTED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `collection.OnNotificationResult` | NOTIFICATION_SENT, NOTIFICATION_FAILED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `notifications.NotifyApprovers` | APPROVAL_REQUESTED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `automation.DispatchEvent` | INVOICE_ISSUED, INVOICE_DUE_SOON, INVOICE_DUE, INVOICE_OVERDUE, INVOICE_PARTIALLY_PAID, INVOICE_PAID, INVOICE_SETTLEMENT_REVERTED, INVOICE_DISPUTED, INVOICE_DISPUTE_RESOLVED, INVOICE_VOIDED, PRIORITY_CHANGED, PAYMENT_CREATED, PAYMENT_ALLOCATED, PAYMENT_ALLOCATION_REVERSED, PAYMENT_REVERSED, PROMISE_CREATED, PROMISE_FULFILLED, PROMISE_BROKEN, PROMISE_CANCELLED, RISK_CHANGED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `automation.PauseOrCancelOnSubjectChange` | INVOICE_PAID, INVOICE_VOIDED, INVOICE_CANCELLED, INVOICE_DISPUTED, PROMISE_CREATED, COLLECTION_HOLD_PLACED, CUSTOMER_DEACTIVATED, CUSTOMER_ARCHIVED, ORGANIZATION_SUSPENDED, ORGANIZATION_CLOSED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `automation.OnAutomationPausedOrDisabled` | AUTOMATION_PAUSED, AUTOMATION_DISABLED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `automation.ResumeOnCauseLifted` | INVOICE_DISPUTE_RESOLVED, PROMISE_FULFILLED, PROMISE_BROKEN, PROMISE_CANCELLED, COLLECTION_HOLD_RELEASED, CUSTOMER_REACTIVATED, ORGANIZATION_REACTIVATED, IMPORT_BATCH_RELEASED, AUTOMATION_ACTIVATED, PAYMENT_ALLOCATED, PAYMENT_REVERSED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `automation.OnApprovalDecidedForExecution` | APPROVAL_GRANTED, APPROVAL_REJECTED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `risk.RequestRiskRecalc` | INVOICE_ISSUED, INVOICE_OVERDUE, INVOICE_PARTIALLY_PAID, INVOICE_PAID, INVOICE_SETTLEMENT_REVERTED, INVOICE_VOIDED, PAYMENT_ALLOCATED, PAYMENT_ALLOCATION_REVERSED, PAYMENT_REVERSED, PROMISE_BROKEN, PROMISE_FULFILLED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `risk.RecomputeRisk` | RISK_RECALCULATION_REQUESTED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `priority.RequestPriorityRecalc` | INVOICE_ISSUED, INVOICE_DUE_SOON, INVOICE_DUE, INVOICE_OVERDUE, INVOICE_PARTIALLY_PAID, INVOICE_PAID, INVOICE_SETTLEMENT_REVERTED, INVOICE_VOIDED, INVOICE_CANCELLED, INVOICE_DISPUTED, INVOICE_DISPUTE_RESOLVED, PAYMENT_CREATED, PAYMENT_ALLOCATED, PAYMENT_ALLOCATION_REVERSED, PAYMENT_REVERSED, PROMISE_CREATED, PROMISE_BROKEN, PROMISE_FULFILLED, PROMISE_CANCELLED, COLLECTION_HOLD_PLACED, COLLECTION_HOLD_RELEASED, COLLECTION_ACTION_EXECUTED, RISK_CHANGED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `priority.RecomputePriority` | PRIORITY_RECALCULATION_REQUESTED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `cashflow.RequestCashflowRecalc` | INVOICE_ISSUED, INVOICE_PAID, INVOICE_PARTIALLY_PAID, INVOICE_SETTLEMENT_REVERTED, INVOICE_VOIDED, INVOICE_CANCELLED, PAYMENT_CREATED, PAYMENT_ALLOCATED, PAYMENT_ALLOCATION_REVERSED, PAYMENT_REVERSED, PROMISE_CREATED, PROMISE_BROKEN, PROMISE_FULFILLED, PROMISE_CANCELLED, ORG_SETTINGS_CHANGED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |
| `cashflow.RunCashflow` | CASHFLOW_RECALCULATION_REQUESTED | `(event_id, handler_name)` | 10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD |

### 2.2 Propriété des écritures

**Règle.** Un état métier n'est écrit que par les cas d'usage **de son module propriétaire**, par la **fonction de transition du Domain**. Seules les opérations nommées de C12 franchissent un module. Aucun autre code ne peut assigner ces états (`invoice.outstanding_minor` est une colonne générée : elle ne peut littéralement pas être assignée).

| État | Propriétaire | Nature | Écrit par | Détail |
|---|---|---|---|---|
| `organizations.record` | `organizations` | état | CreateOrganization, UpdateOrganization | organisation : nom, fuseau, devise |
| `organizations.status` | `organizations` | état | CreateOrganization, CompleteProvisioning, SuspendOrganization, ReactivateOrganization, CloseOrganization | PROVISIONING / ACTIVE / SUSPENDED / CLOSED (PROVISIONING : amendement) |
| `organizations.settings` | `organizations` | état | CreateOrganization, ChangeOrgSettings | org_settings, org_holidays |
| `identity.user` | `identity` | état | CreateUser, ChangeUserStatus, AnonymizeUser | utilisateur |
| `identity.membership` | `identity` | état | AddMember, ProvisionOwnerMembership, ChangeMemberRole, RemoveMember | appartenance et rôle |
| `customers.record` | `customers` | état | CreateCustomer, UpdateCustomer, AddCustomerContact, UpdateCustomerContact, NormalizeImportBatch (C12), AnonymizeCustomer | client et contacts |
| `customers.status` | `customers` | état | DeactivateCustomer, ArchiveCustomer, ReactivateCustomer | ACTIVE / INACTIVE / ARCHIVED |
| `invoices.body` | `invoices` | état | CreateInvoice, NormalizeImportBatch (C12) | facture DRAFT, lignes |
| `invoices.lifecycle` | `invoices` | état | IssueInvoice, CancelInvoice, VoidInvoice, InvoiceLifecycleScan, ApplySettlement, ReverseAllocation (C12), ReversePayment (C12), NormalizeImportBatch (C12) | lifecycle_state |
| `invoices.settlement` | `invoices` | cache | ApplySettlement, AllocatePayment (C12), ReverseAllocation (C12), ReversePayment (C12), NormalizeImportBatch (C12) | paid_minor, settlement_state, settled_on (cache des allocations) |
| `invoices.collection_cycle` | `invoices` | cache | IssueInvoice, InvoiceLifecycleScan, ApplySettlement, AllocatePayment (C12), ReverseAllocation (C12), ReversePayment (C12) | compteur de cycle de recouvrement |
| `invoices.dispute` | `invoices` | état | OpenInvoiceDispute, ResolveInvoiceDispute | invoice_disputes |
| `payments.record` | `payments` | état | CreatePayment, NormalizeImportBatch (C12) | paiement à la création |
| `payments.allocated` | `payments` | cache | AllocatePayment, ReverseAllocation, ReversePayment, NormalizeImportBatch (C12) | allocated_minor, status |
| `payments.allocations` | `payments` | append | AllocatePayment, ReverseAllocation, ReversePayment, NormalizeImportBatch (C12) | payment_allocations, payment_reversals (source de vérité du solde) |
| `promises.status` | `promises` | état | CreatePromise, CancelPromise, FulfillPromiseOnInvoicePaid, FulfillPromiseOnAllocation, CancelPromiseOnInvoiceEnded, CancelPromiseOnCustomerArchived, PromiseBreachScan | ACTIVE / FULFILLED / BROKEN / CANCELLED |
| `imports.batch` | `imports` | état | UploadImportBatch, ValidateImportBatch, ApproveImportBatch, CommitImportBatch, CancelImportBatch, NormalizeImportBatch, StartImportRelease, CompleteImportRelease, PurgeImportStaging | import_batches.status et staging |
| `collection.action_status` | `collection` | état | CreateCollectionAction, AdvanceProposedAction, ResumeProposedActions, CreateManualAction, CancelCollectionAction, ClaimTask, CompleteTask, RescheduleAction, ExecuteDueAction, ReapActions, SuppressOnInvoicePaid, SuppressOnInvoiceEnded, SuppressOnInvoiceDisputed, SuppressOnPromiseCreated, SuppressOnHoldPlaced, SuppressOnCustomerInactive, SuppressOnOrgSuspended, OnApprovalDecided, OnNotificationResult | collection_actions.status |
| `collection.attempts` | `collection` | append | ExecuteDueAction, ReapActions, OnNotificationResult | collection_action_attempts |
| `collection.hold_status` | `collection` | état | PlaceHold, ReleaseHold, HoldExpiryScan | collection_holds |
| `approvals.status` | `approvals` | état | RequestApproval, DecideApproval, ApprovalExpiryScan | approvals.status |
| `notifications.status` | `notifications` | état | CreateNotification, HandleSendResult, NotifyApprovers, CleanNotificationPayloads | notifications.status, deliveries |
| `automation.definition` | `automation` | état | ProvisionDefaultAutomations, CreateAutomation, CreateAutomationVersion, ActivateAutomation, PauseAutomation, DisableAutomation, ArchiveAutomation | automations, automation_versions |
| `automation.execution` | `automation` | état | ActivateAutomation, DispatchEvent, ScanTimeTriggers, RunExecutionStep, PauseOrCancelOnSubjectChange, OnAutomationPausedOrDisabled, ResumeOnCauseLifted, OnApprovalDecidedForExecution, ResumeReconciliationPaused, ReleaseImportTranche, ReapExecutions, RetryExecution | automation_executions.status et étapes |
| `risk.profile` | `risk` | projection | RecomputeRisk | risk_profiles, risk_snapshots |
| `priority.item` | `priority` | projection | RecomputePriority | priority_items, priority_snapshots |
| `cashflow.run` | `cashflow` | projection | RunCashflow | cashflow_runs (is_current), cashflow_lines |
| `billing.subscription` | `billing` | état | ProvisionTrialSubscription | subscriptions (S7) |
| `events.publication` | `events` | état | OutboxPublisher, EmitEvent | published_at, available_at, publish_attempts |
| `events.receipts` | `events` | état | OutboxPublisher, ReplayDeadEvent | event_receipts |
| `audit.log` | `audit` | append | AnonymizeAuditLogs, WriteAuditLog | audit_logs |
| `platform.idempotency` | `platform` | état | StoreIdempotencyKey | idempotency_keys |

## 3. Event Registry

Politique commune : un événement est **publiable** dès le `COMMIT` ; chaque handler a son **propre** reçu et sa **propre** reprise (`10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD`) ; aucun handler ne suppose d'ordre ; le schéma vit dans `schemas/<TYPE>.v1.json`.

| Événement | Catégorie | Agrégat | Producteur(s) | Consommateur(s) | Politique de reçu |
|---|---|---|---|---|---|
| `ORGANIZATION_CREATED` | MUTATION | organization | `organizations` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `ORGANIZATION_UPDATED` | MUTATION | organization | `organizations` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `ORG_SETTINGS_CHANGED` | MUTATION | organization | `organizations` | `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `CUSTOMER_CREATED` | MUTATION | customer | `customers` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `CUSTOMER_UPDATED` | MUTATION | customer | `customers` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `CUSTOMER_CONTACT_ADDED` | MUTATION | customer | `customers` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `CUSTOMER_CONTACT_UPDATED` | MUTATION | customer | `customers` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `USER_CREATED` | MUTATION | user | `identity` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `MEMBER_ADDED` | MUTATION | membership | `identity` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `MEMBER_ROLE_CHANGED` | MUTATION | membership | `identity` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `INVOICE_CREATED` | MUTATION | invoice | `invoices` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `INVOICE_DISPUTED` | MUTATION | invoice | `invoices` | `collection.SuppressOnInvoiceDisputed`, `automation.DispatchEvent`, `automation.PauseOrCancelOnSubjectChange`, `priority.RequestPriorityRecalc` | diffusé à tous les abonnés |
| `PAYMENT_CREATED` | MUTATION | payment | `payments` | `automation.DispatchEvent`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `PAYMENT_ALLOCATED` | MUTATION | payment | `payments` | `promises.FulfillPromiseOnAllocation`, `automation.DispatchEvent`, `automation.ResumeOnCauseLifted`, `risk.RequestRiskRecalc`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `PAYMENT_ALLOCATION_REVERSED` | MUTATION | payment | `payments` | `automation.DispatchEvent`, `risk.RequestRiskRecalc`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `PROMISE_CREATED` | MUTATION | promise | `promises` | `collection.SuppressOnPromiseCreated`, `automation.DispatchEvent`, `automation.PauseOrCancelOnSubjectChange`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `COLLECTION_ACTION_PROPOSED` | MUTATION | collection_action | `collection` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `COLLECTION_HOLD_PLACED` | MUTATION | hold | `collection` | `collection.SuppressOnHoldPlaced`, `automation.PauseOrCancelOnSubjectChange`, `priority.RequestPriorityRecalc` | diffusé à tous les abonnés |
| `APPROVAL_REQUESTED` | MUTATION | approval | `approvals` | `notifications.NotifyApprovers` | diffusé à tous les abonnés |
| `NOTIFICATION_CREATED` | MUTATION | notification | `notifications` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `AUTOMATION_CREATED` | MUTATION | automation | `automation` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `AUTOMATION_VERSION_CREATED` | MUTATION | automation | `automation` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `IMPORT_BATCH_UPLOADED` | MUTATION | import_batch | `imports` | `imports.ValidateImportBatch` | diffusé à tous les abonnés |
| `ORGANIZATION_SUSPENDED` | TRANSITION | organization | `organizations` | `collection.SuppressOnOrgSuspended`, `automation.PauseOrCancelOnSubjectChange` | diffusé à tous les abonnés |
| `ORGANIZATION_REACTIVATED` | TRANSITION | organization | `organizations` | `automation.ResumeOnCauseLifted` | diffusé à tous les abonnés |
| `ORGANIZATION_CLOSED` | TRANSITION | organization | `organizations` | `collection.SuppressOnOrgSuspended`, `automation.PauseOrCancelOnSubjectChange` | diffusé à tous les abonnés |
| `CUSTOMER_ARCHIVED` | TRANSITION | customer | `customers` | `promises.CancelPromiseOnCustomerArchived`, `collection.SuppressOnCustomerInactive`, `automation.PauseOrCancelOnSubjectChange` | diffusé à tous les abonnés |
| `CUSTOMER_REACTIVATED` | TRANSITION | customer | `customers` | `automation.ResumeOnCauseLifted` | diffusé à tous les abonnés |
| `CUSTOMER_DEACTIVATED` | TRANSITION | customer | `customers` | `collection.SuppressOnCustomerInactive`, `automation.PauseOrCancelOnSubjectChange` | diffusé à tous les abonnés |
| `USER_STATUS_CHANGED` | TRANSITION | user | `identity` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `MEMBER_REMOVED` | TRANSITION | membership | `identity` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `INVOICE_ISSUED` | TRANSITION | invoice | `invoices` | `automation.DispatchEvent`, `risk.RequestRiskRecalc`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `INVOICE_DUE_SOON` | TRANSITION | invoice | `invoices` | `automation.DispatchEvent`, `priority.RequestPriorityRecalc` | diffusé à tous les abonnés |
| `INVOICE_DUE` | TRANSITION | invoice | `invoices` | `automation.DispatchEvent`, `priority.RequestPriorityRecalc` | diffusé à tous les abonnés |
| `INVOICE_OVERDUE` | TRANSITION | invoice | `invoices` | `automation.DispatchEvent`, `risk.RequestRiskRecalc`, `priority.RequestPriorityRecalc` | diffusé à tous les abonnés |
| `INVOICE_PARTIALLY_PAID` | TRANSITION | invoice | `invoices` | `automation.DispatchEvent`, `risk.RequestRiskRecalc`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `INVOICE_PAID` | TRANSITION | invoice | `invoices` | `promises.FulfillPromiseOnInvoicePaid`, `collection.SuppressOnInvoicePaid`, `automation.DispatchEvent`, `automation.PauseOrCancelOnSubjectChange`, `risk.RequestRiskRecalc`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `INVOICE_SETTLEMENT_REVERTED` | TRANSITION | invoice | `invoices` | `automation.DispatchEvent`, `risk.RequestRiskRecalc`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `INVOICE_CANCELLED` | TRANSITION | invoice | `invoices` | `promises.CancelPromiseOnInvoiceEnded`, `collection.SuppressOnInvoiceEnded`, `automation.PauseOrCancelOnSubjectChange`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `INVOICE_VOIDED` | TRANSITION | invoice | `invoices` | `promises.CancelPromiseOnInvoiceEnded`, `collection.SuppressOnInvoiceEnded`, `automation.DispatchEvent`, `automation.PauseOrCancelOnSubjectChange`, `risk.RequestRiskRecalc`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `INVOICE_DISPUTE_RESOLVED` | TRANSITION | invoice | `invoices` | `automation.DispatchEvent`, `automation.ResumeOnCauseLifted`, `priority.RequestPriorityRecalc` | diffusé à tous les abonnés |
| `PAYMENT_REVERSED` | TRANSITION | payment | `payments` | `automation.DispatchEvent`, `automation.ResumeOnCauseLifted`, `risk.RequestRiskRecalc`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `PROMISE_FULFILLED` | TRANSITION | promise | `promises` | `automation.DispatchEvent`, `automation.ResumeOnCauseLifted`, `risk.RequestRiskRecalc`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `PROMISE_BROKEN` | TRANSITION | promise | `promises` | `automation.DispatchEvent`, `automation.ResumeOnCauseLifted`, `risk.RequestRiskRecalc`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `PROMISE_CANCELLED` | TRANSITION | promise | `promises` | `automation.DispatchEvent`, `automation.ResumeOnCauseLifted`, `priority.RequestPriorityRecalc`, `cashflow.RequestCashflowRecalc` | diffusé à tous les abonnés |
| `COLLECTION_ACTION_SCHEDULED` | TRANSITION | collection_action | `collection` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `COLLECTION_ACTION_EXECUTED` | TRANSITION | collection_action | `collection` | `priority.RequestPriorityRecalc` | diffusé à tous les abonnés |
| `COLLECTION_ACTION_FAILED` | TRANSITION | collection_action | `collection` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `COLLECTION_ACTION_CANCELLED` | TRANSITION | collection_action | `collection` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `COLLECTION_ACTION_SUPPRESSED` | TRANSITION | collection_action | `collection` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `COLLECTION_HOLD_RELEASED` | TRANSITION | hold | `collection` | `automation.ResumeOnCauseLifted`, `priority.RequestPriorityRecalc` | diffusé à tous les abonnés |
| `APPROVAL_GRANTED` | TRANSITION | approval | `approvals` | `collection.OnApprovalDecided`, `automation.OnApprovalDecidedForExecution` | diffusé à tous les abonnés |
| `APPROVAL_REJECTED` | TRANSITION | approval | `approvals` | `collection.OnApprovalDecided`, `automation.OnApprovalDecidedForExecution` | diffusé à tous les abonnés |
| `AUTOMATION_ACTIVATED` | TRANSITION | automation | `automation` | `automation.ResumeOnCauseLifted` | diffusé à tous les abonnés |
| `AUTOMATION_PAUSED` | TRANSITION | automation | `automation` | `automation.OnAutomationPausedOrDisabled` | diffusé à tous les abonnés |
| `AUTOMATION_DISABLED` | TRANSITION | automation | `automation` | `automation.OnAutomationPausedOrDisabled` | diffusé à tous les abonnés |
| `AUTOMATION_ARCHIVED` | TRANSITION | automation | `automation` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `AUTOMATION_EXECUTION_STARTED` | TRANSITION | automation_execution | `automation` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `AUTOMATION_EXECUTION_COMPLETED` | TRANSITION | automation_execution | `automation` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `AUTOMATION_EXECUTION_FAILED` | TRANSITION | automation_execution | `automation` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `AUTOMATION_EXECUTION_CANCELLED` | TRANSITION | automation_execution | `automation` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `NOTIFICATION_SENT` | TRANSITION | notification | `notifications` | `collection.OnNotificationResult` | diffusé à tous les abonnés |
| `NOTIFICATION_FAILED` | TRANSITION | notification | `notifications` | `collection.OnNotificationResult` | diffusé à tous les abonnés |
| `SUBSCRIPTION_CHANGED` | TRANSITION | subscription | `billing` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `IMPORT_BATCH_READY` | TRANSITION | import_batch | `imports` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `IMPORT_BATCH_APPROVED` | TRANSITION | import_batch | `imports` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `IMPORT_BATCH_COMMITTED` | TRANSITION | import_batch | `imports` | `imports.NormalizeImportBatch` | diffusé à tous les abonnés |
| `IMPORT_BATCH_NORMALIZED` | TRANSITION | import_batch | `imports` | `imports.StartImportRelease` | diffusé à tous les abonnés |
| `IMPORT_BATCH_RELEASED` | TRANSITION | import_batch | `imports` | `automation.ResumeOnCauseLifted` | diffusé à tous les abonnés |
| `IMPORT_BATCH_FAILED` | TRANSITION | import_batch | `imports` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `IMPORT_BATCH_CANCELLED` | TRANSITION | import_batch | `imports` | — | diffusé à tous les abonnés (aucun abonné en V1) |
| `RISK_RECALCULATION_REQUESTED` | REQUEST | Risk Engine | `automation`, `imports`, `risk` | `risk.RecomputeRisk` | un seul destinataire ; regroupement 2 s ; reçus `PROCESSED` + `SKIPPED` |
| `PRIORITY_RECALCULATION_REQUESTED` | REQUEST | Priority Engine | `automation`, `imports`, `priority` | `priority.RecomputePriority` | un seul destinataire ; regroupement 2 s ; reçus `PROCESSED` + `SKIPPED` |
| `CASHFLOW_RECALCULATION_REQUESTED` | REQUEST | Cashflow Engine | `automation`, `cashflow`, `imports` | `cashflow.RunCashflow` | un seul destinataire ; regroupement 2 s ; reçus `PROCESSED` + `SKIPPED` |
| `RISK_CHANGED` | RESULT | customer | `risk` | `automation.DispatchEvent`, `priority.RequestPriorityRecalc` | diffusé à tous les abonnés |
| `PRIORITY_CHANGED` | RESULT | invoice | `priority` | `automation.DispatchEvent` | diffusé à tous les abonnés |
| `CASHFLOW_UPDATED` | RESULT | cashflow_run | `cashflow` | — | diffusé à tous les abonnés (aucun abonné en V1) |

## 4. Lock Registry

**L'ordre est dérivé, pas décrété.** Chaque opération déclare la suite de ressources qu'elle acquiert ; le générateur en tire un graphe de précédence, vérifie qu'il est sans cycle, et produit l'échelle. Une opération nouvelle qui contredirait l'échelle fait échouer la porte.

Modes : `A` verrou consultatif de transaction (première instruction) · `K` clé d'idempotence · `S` `FOR SHARE` · `U` `FOR NO KEY UPDATE` · `G` `UPDATE` gardé · `I` `INSERT` (clé unique, clé étrangère).

### 4.1 Échelle publiée (compatible avec la chaîne gelée EC5)

Règle : une transaction n'acquiert une ressource que d'un rang **supérieur** à celles qu'elle détient déjà ; à l'intérieur d'une ressource, par identifiant croissant.

| Rang | Ressource | Tables | Remarque |
|---:|---|---|---|
| 10 | `advisory` | verrou consultatif (travail, organisation) ou (moteur, sujet) | toujours en premier |
| 20 | `idempotency_keys` | idempotency_keys | première écriture d'une commande d'API (TD32) |
| 30 | `organizations` | organizations, org_settings | — |
| 40 | `identity_members` | users, memberships | — |
| 50 | `subscriptions` | subscriptions | Billing (S7) : emplacement réservé |
| 60 | `import_batches` | import_batches, import_rows | — |
| 70 | `customers` | customers, customer_contacts | — |
| 80 | `payments` | payments, payment_allocations, payment_reversals | — |
| 90 | `invoices` | invoices, invoice_items | — |
| 100 | `invoice_disputes` | invoice_disputes | — |
| 110 | `promises` | promises | — |
| 120 | `collection_holds` | collection_holds | — |
| 130 | `automations` | automations, automation_versions | — |
| 140 | `collection_actions` | collection_actions, collection_action_attempts | — |
| 150 | `automation_executions` | automation_executions, automation_execution_steps | — |
| 160 | `approvals` | approvals | — |
| 170 | `notifications` | notifications, notification_deliveries | — |
| 180 | `projections` | risk_*, priority_*, cashflow_* | écrites par leur moteur seulement |
| 190 | `event_receipts` | event_receipts | dernier : le reçu est écrit avec l'effet (EC-02 (5)) |

Chaîne gelée EC5 : `payments → invoices → promises → collection_actions → automation_executions → notifications` → **compatible** avec toutes les opérations enregistrées.

### 4.2 Opérations enregistrées

| Opération | Module | Séquence d'acquisition | Source |
|---|---|---|---|
| **CreateOrganization** | `organizations` | `idempotency_keys`(K) → `organizations`(I) | plan de provisioning : une transaction par étape |
| **CompleteProvisioning** | `organizations` | `organizations`(G) | PROVISIONING vers ACTIVE |
| **ProvisionOwner** | `identity` | `identity_members`(I) | étape de provisioning |
| **ProvisionTrial** | `billing` | `subscriptions`(I) | étape de provisioning (S7) |
| **InstallDefaults** | `automation` | `automations`(I) | étape de provisioning |
| **ChangeOrganization** | `organizations` | `idempotency_keys`(K) → `organizations`(U) | SM §1 |
| **IdentityCommand** | `identity` | `idempotency_keys`(K) → `identity_members`(U) | SM §15 |
| **CustomerCommand** | `customers` | `idempotency_keys`(K) → `customers`(U) | SM §2 |
| **CreateInvoice** | `invoices` | `idempotency_keys`(K) → `customers`(S) → `invoices`(I) | EC-06 |
| **IssueInvoice** | `invoices` | `idempotency_keys`(K) → `customers`(S) → `invoices`(U) | EC-06 |
| **InvoiceTransition** | `invoices` | `invoices`(G) | EC-06 (job) |
| **InvoiceDisputeCommand** | `invoices` | `idempotency_keys`(K) → `invoices`(U) → `invoice_disputes`(U) | SM §4 |
| **CreatePayment** | `payments` | `idempotency_keys`(K) → `customers`(S) → `payments`(I) | Contrat §4 |
| **PaymentSettlement** | `payments` | `idempotency_keys`(K) → `payments`(U) → `invoices`(U) | EC-05 (id croissant) |
| **CreatePromise** | `promises` | `idempotency_keys`(K) → `customers`(S) → `invoices`(S) → `promises`(I) | SM §7 |
| **PromiseTransition** | `promises` | `promises`(U) | SM §7 |
| **PlaceHold** | `collection` | `idempotency_keys`(K) → `collection_holds`(I) | SM §9 |
| **ReleaseHold** | `collection` | `collection_holds`(G) | SM §9 |
| **NormalizeImportBatch** | `imports` | `import_batches`(U) → `customers`(I) → `payments`(I) → `invoices`(I) → `event_receipts`(I) | EC-07 |
| **ImportBatchTransition** | `imports` | `import_batches`(G) | SM §14 |
| **ValidateImportBatch** | `imports` | `import_batches`(G) → `event_receipts`(I) | SM §14 |
| **StartImportRelease** | `imports` | `import_batches`(G) → `event_receipts`(I) | SM §16 |
| **ReleaseTranche** | `automation` | `automation_executions`(I) | Automation §10.1 |
| **ActivateAutomation** | `automation` | `idempotency_keys`(K) → `automations`(U) → `automation_executions`(I) | EC-12 |
| **AutomationDefinitionCommand** | `automation` | `idempotency_keys`(K) → `automations`(U) | EC-12 |
| **DispatchEvent** | `automation` | `automation_executions`(I) → `event_receipts`(I) | EC-12 |
| **ClaimExecution** | `automation` | `automation_executions`(G) | EC-12 : PENDING/WAITING vers RUNNING (RUNNING est le bail ; le Reaper le reprend) |
| **RecordExecutionStep** | `automation` | `automation_executions`(U) | EC-12 : ligne d etape et nouvel etat ; l effet a eu lieu avant, dans la transaction du module proprietaire |
| **ChangeExecutionState** | `automation` | `automation_executions`(U) → `event_receipts`(I) | EC-12 |
| **ReapExecutions** | `automation` | `automation_executions`(G) | EC-03 |
| **ReapActions** | `collection` | `collection_actions`(G) | EC-03 |
| **CreateCollectionAction** | `collection` | `idempotency_keys`(K) → `collection_actions`(I) | EC-11 : l'approbation est demandée ensuite, dans la transaction du module approvals |
| **AdvanceProposedAction** | `collection` | `collection_actions`(U) | PROPOSED vers SCHEDULED ou PENDING_APPROVAL, après revalidation |
| **RequestApproval** | `approvals` | `approvals`(I) | EC-13 : transaction du module propriétaire |
| **ExecuteDueAction** | `collection` | `collection_actions`(U) | EC-11, X3 : claim et revalidation ; la notification est créée ensuite dans sa propre transaction |
| **CollectionReaction** | `collection` | `collection_actions`(U) → `event_receipts`(I) | Collection §12 |
| **ClaimTask** | `collection` | `collection_actions`(G) | EC-11 : réclamation gardée (UPDATE … WHERE assigned_to IS NULL) |
| **RescheduleAction** | `collection` | `collection_actions`(G) | EC-11, Invariants §7.1 : garde sur status ∈ {PROPOSED, SCHEDULED} avant modification de scheduled_for |
| **DecideApproval** | `approvals` | `idempotency_keys`(K) → `approvals`(U) | EC-13 |
| **ApprovalExpiryScan** | `approvals` | `approvals`(G) | EC-13 |
| **HandleSendResult** | `notifications` | `notifications`(U) | EC-04 |
| **CreateNotification** | `notifications` | `notifications`(I) | EC-04 |
| **NotifyApprovers** | `notifications` | `notifications`(I) → `event_receipts`(I) | notification APPROVAL_REQUESTED |
| **ProjectionRecompute** | `projections` | `advisory`(A) → `projections`(U) → `event_receipts`(I) | EC-14, TD29 |
| **RunCashflow** | `cashflow` | `advisory`(A) → `projections`(U) → `event_receipts`(I) | EC-14 |
| **JobStep** | `jobs` | `advisory`(A) | EC-03 (verrou travail, organisation) |
| **Anonymize** | `customers` | `customers`(U) | Contrat §17 |
| **ReplayDeadEvent** | `events` | `idempotency_keys`(K) → `event_receipts`(U) | EC-02 |

### 4.3 Arêtes de précédence et opérations qui les imposent

| Avant | Après | Imposée par |
|---|---|---|
| `advisory` | `projections` | ProjectionRecompute, RunCashflow |
| `automation_executions` | `event_receipts` | ChangeExecutionState, DispatchEvent |
| `automations` | `automation_executions` | ActivateAutomation |
| `collection_actions` | `event_receipts` | CollectionReaction |
| `customers` | `invoices` | CreateInvoice, CreatePromise, IssueInvoice |
| `customers` | `payments` | CreatePayment, NormalizeImportBatch |
| `idempotency_keys` | `approvals` | DecideApproval |
| `idempotency_keys` | `automations` | ActivateAutomation, AutomationDefinitionCommand |
| `idempotency_keys` | `collection_actions` | CreateCollectionAction |
| `idempotency_keys` | `collection_holds` | PlaceHold |
| `idempotency_keys` | `customers` | CreateInvoice, CreatePayment, CreatePromise, CustomerCommand, IssueInvoice |
| `idempotency_keys` | `event_receipts` | ReplayDeadEvent |
| `idempotency_keys` | `identity_members` | IdentityCommand |
| `idempotency_keys` | `invoices` | InvoiceDisputeCommand |
| `idempotency_keys` | `organizations` | ChangeOrganization, CreateOrganization |
| `idempotency_keys` | `payments` | PaymentSettlement |
| `import_batches` | `customers` | NormalizeImportBatch |
| `import_batches` | `event_receipts` | StartImportRelease, ValidateImportBatch |
| `invoices` | `event_receipts` | NormalizeImportBatch |
| `invoices` | `invoice_disputes` | InvoiceDisputeCommand |
| `invoices` | `promises` | CreatePromise |
| `notifications` | `event_receipts` | NotifyApprovers |
| `payments` | `invoices` | NormalizeImportBatch, PaymentSettlement |
| `projections` | `event_receipts` | ProjectionRecompute, RunCashflow |

## 5. Graphes de dépendances

Trois graphes **séparés**, parce qu'une dépendance d'événement n'est pas une dépendance d'appel : un module qui *écoute* un autre ne l'*appelle* pas. Le graphe des **appels** doit être sans cycle ; le graphe de **schéma** aussi (ordre des migrations).

### 5.1 Appels, lectures, ports et fournisseurs de faits (sans cycle)

| Niveau | Module | Appelle / lit / implémente |
|---:|---|---|
| 0 | `approvals` | — |
| 0 | `audit` | — |
| 0 | `events` | — |
| 0 | `kernel` | — |
| 0 | `platform` | — |
| 0 | `rules` | — |
| 1 | `organizations` | `rules` |
| 2 | `billing` | `organizations` |
| 2 | `customers` | `organizations`, `rules` |
| 2 | `identity` | `organizations` |
| 3 | `invoices` | `customers`, `organizations`, `rules` |
| 3 | `notifications` | `customers`, `identity`, `organizations` |
| 4 | `collection` | `approvals`, `customers`, `invoices`, `notifications`, `organizations`, `rules` |
| 4 | `payments` | `customers`, `invoices`, `organizations`, `rules` |
| 4 | `promises` | `customers`, `invoices`, `organizations`, `rules` |
| 5 | `risk` | `invoices`, `organizations`, `payments`, `promises`, `rules` |
| 6 | `cashflow` | `customers`, `invoices`, `organizations`, `payments`, `promises`, `risk` |
| 6 | `priority` | `collection`, `invoices`, `organizations`, `promises`, `risk`, `rules` |
| 7 | `imports` | `cashflow`, `customers`, `invoices`, `organizations`, `payments`, `priority`, `risk`, `rules` |
| 8 | `automation` | `approvals`, `cashflow`, `collection`, `customers`, `imports`, `invoices`, `notifications`, `organizations`, `payments`, `priority`, `promises`, `risk`, `rules` |

### 5.2 Événements (qui écoute qui)

| Module | Écoute les événements de |
|---|---|
| `automation` | `approvals` (2), `collection` (2), `customers` (3), `imports` (1), `invoices` (15), `organizations` (3), `payments` (6), `priority` (1), `promises` (8), `risk` (1) |
| `cashflow` | `invoices` (6), `organizations` (1), `payments` (4), `promises` (4) |
| `collection` | `approvals` (2), `customers` (2), `invoices` (4), `notifications` (2), `organizations` (2), `promises` (1) |
| `notifications` | `approvals` (1) |
| `priority` | `collection` (3), `invoices` (11), `payments` (4), `promises` (4), `risk` (1) |
| `promises` | `customers` (1), `invoices` (3), `payments` (1) |
| `risk` | `invoices` (6), `payments` (3), `promises` (2) |

### 5.3 Schéma (ordre des migrations)

| Module | Références de clé étrangère vers |
|---|---|
| `approvals` | `automation`, `collection`, `organizations` |
| `automation` | `organizations` |
| `billing` | `organizations` |
| `cashflow` | `customers`, `invoices`, `organizations`, `payments` |
| `collection` | `automation`, `customers`, `invoices`, `organizations` |
| `customers` | `organizations` |
| `identity` | `organizations` |
| `imports` | `identity`, `organizations` |
| `invoices` | `customers`, `imports`, `organizations` |
| `notifications` | `customers`, `identity`, `organizations` |
| `payments` | `customers`, `imports`, `invoices`, `organizations` |
| `priority` | `customers`, `invoices`, `organizations` |
| `promises` | `customers`, `invoices`, `organizations` |
| `risk` | `customers`, `organizations` |

### 5.4 Événements sans abonné, classés

A volontaire · B autre passe · C oublié (interdit : la porte échoue).

| Événement | Classe | Raison |
|---|---|---|
| `AUTOMATION_ARCHIVED` | A | journal ; une automatisation archivée n'a plus d'exécution (elle est désactivée avant, AUTOMATION_DISABLED) |
| `AUTOMATION_CREATED` | A | journal et interface de gestion des automatisations |
| `AUTOMATION_EXECUTION_CANCELLED` | A | suivi d'exécution : interface et compteurs, lus par requête |
| `AUTOMATION_EXECUTION_COMPLETED` | A | suivi d'exécution : interface et compteurs, lus par requête |
| `AUTOMATION_EXECUTION_FAILED` | A | alerte opérationnelle par l'observabilité (taux d'échec), retour manuel par RetryExecution |
| `AUTOMATION_EXECUTION_STARTED` | A | suivi d'exécution : interface et compteurs, lus par requête |
| `AUTOMATION_VERSION_CREATED` | A | journal et historique des versions |
| `CASHFLOW_UPDATED` | B | alertes de trésorerie : non utilisable comme déclencheur en V1 (Automation AU3), évolution prévue |
| `COLLECTION_ACTION_CANCELLED` | A | explication et historique des actions, lus par requête |
| `COLLECTION_ACTION_FAILED` | A | le repli humain est décidé dans `collection` au moment de l'échec, sans passer par un abonné |
| `COLLECTION_ACTION_PROPOSED` | A | explication et historique des actions, lus par requête |
| `COLLECTION_ACTION_SCHEDULED` | A | explication et historique des actions, lus par requête |
| `COLLECTION_ACTION_SUPPRESSED` | A | explication : la cause est dans `suppression_code`, lue par requête |
| `CUSTOMER_CONTACT_ADDED` | A | journal ; les garde-fous NO_CONTACT / NO_CONSENT relisent les contacts à l'exécution |
| `CUSTOMER_CONTACT_UPDATED` | A | journal ; les garde-fous NO_CONTACT / NO_CONSENT relisent les contacts à l'exécution |
| `CUSTOMER_CREATED` | A | journal ; les décisions relisent le client à la source (X1) |
| `CUSTOMER_UPDATED` | A | journal ; les décisions relisent le client à la source (X1) |
| `IMPORT_BATCH_APPROVED` | A | interface d'import et audit |
| `IMPORT_BATCH_CANCELLED` | A | interface d'import et audit |
| `IMPORT_BATCH_FAILED` | A | interface d'import et alerte opérationnelle |
| `IMPORT_BATCH_READY` | A | interface d'import : le lot attend l'approbation d'un administrateur |
| `INVOICE_CREATED` | A | journal ; une facture DRAFT n'est pas recouvrable (Rule Engine, étape 0) |
| `MEMBER_ADDED` | A | journal et audit ; le rôle est relu à chaque commande |
| `MEMBER_REMOVED` | A | journal et audit ; l appartenance est relue à chaque commande et à la revérification des grants |
| `MEMBER_ROLE_CHANGED` | A | journal et audit ; le rôle courant est relu à chaque commande et à la revérification des grants |
| `NOTIFICATION_CREATED` | A | l'envoi réclame les notifications dans la table (`SKIP LOCKED`) : pas d'abonné |
| `ORGANIZATION_CREATED` | A | journal ; émis à la fin du provisioning (PROVISIONING vers ACTIVE) |
| `ORGANIZATION_UPDATED` | A | journal |
| `SUBSCRIPTION_CHANGED` | B | Billing (S7) : autorisations issues de l'abonnement, à spécifier |
| `USER_CREATED` | A | journal et audit ; les droits sont relus à chaque commande (rôle courant) |
| `USER_STATUS_CHANGED` | A | journal et audit ; un utilisateur désactivé est refusé à l authentification et à la revérification des grants |

## 6. Noms de commandes

Le nom d'une commande fait partie du contrat. **Aucun nom provisoire n'entre dans la structure Django** : `build_registry.py --freeze` échoue tant qu'un nom est `PROPOSED`.

**Convention de nommage** (figée en revue) :

| Préfixe | Sens |
|---|---|
| `Provision*` | implémentation d'une ProvisioningStep |
| `Create/Add/Update/Change*` | commande métier, verbe aligné sur l'événement émis |
| `Start*` | démarrage d'un processus |
| `Complete*` | achèvement d'un processus |
| `Resume*` | reprise par balayage |
| `Read*` | service de lecture / port reader |
| `Notify*` | handler de notification |

L'unicité d'un nom n'est pas un invariant d'architecture : le couple `(module, nom)` identifie le composant (`ReadApprovalTarget` existe dans `collection` et dans `automation`).

| ID | Module | Nom | Type | Émet | Statut |
|---|---|---|---|---|---|
| N01 | `automation` | `ProvisionDefaultAutomations` | service | AUTOMATION_CREATED | **figé** |
| N02 | `automation` | `ReadApprovalTarget` | service | — | **figé** |
| N03 | `billing` | `ProvisionTrialSubscription` | service | SUBSCRIPTION_CHANGED | **figé** |
| N04 | `collection` | `AdvanceProposedAction` | system | COLLECTION_ACTION_SCHEDULED, COLLECTION_ACTION_SUPPRESSED | **figé** |
| N05 | `collection` | `ReadApprovalTarget` | service | — | **figé** |
| N06 | `collection` | `ResumeProposedActions` | job | — | **figé** |
| N07 | `customers` | `AddCustomerContact` | command | CUSTOMER_CONTACT_ADDED | **figé** |
| N08 | `customers` | `CreateCustomer` | command | CUSTOMER_CREATED | **figé** |
| N09 | `customers` | `UpdateCustomer` | command | CUSTOMER_UPDATED | **figé** |
| N10 | `customers` | `UpdateCustomerContact` | command | CUSTOMER_CONTACT_UPDATED | **figé** |
| N11 | `identity` | `AddMember` | command | MEMBER_ADDED | **figé** |
| N12 | `identity` | `CreateUser` | command | USER_CREATED | **figé** |
| N13 | `identity` | `ProvisionOwnerMembership` | service | MEMBER_ADDED | **figé** |
| N14 | `imports` | `CompleteImportRelease` | system | IMPORT_BATCH_RELEASED | **figé** |
| N15 | `notifications` | `NotifyApprovers` | handler | NOTIFICATION_CREATED | **figé** |
| N16 | `organizations` | `ChangeOrgSettings` | command | ORG_SETTINGS_CHANGED | **figé** |
| N17 | `organizations` | `CompleteProvisioning` | system | ORGANIZATION_CREATED | **figé** |
| N18 | `organizations` | `ResumeProvisioning` | job | — | **figé** |
| N19 | `organizations` | `UpdateOrganization` | command | ORGANIZATION_UPDATED | **figé** |
| N20 | `payments` | `CreatePayment` | command | PAYMENT_CREATED | **figé** |

## 7. Vérifications sur PostgreSQL réel (TA-12)

Serveur : **PostgreSQL 16.2 on x86_64-pc-mingw64**. Chaque ligne est une **expérience exécutée**, avec deux transactions concurrentes ; l'attendu vient des décisions du document d'architecture.

| # | Expérience | Attendu | Observé | Verdict |
|---|---|---|---|---|
| PG-01 | Une clé étrangère prend `FOR KEY SHARE` sur la ligne référencée : qui bloque l'insertion d'un enfant ? | seul `FOR UPDATE` bloque ; `FOR NO KEY UPDATE`, `FOR SHARE` et `FOR KEY SHARE` ne bloquent pas | FOR UPDATE : bloque ; FOR NO KEY UPDATE : ne bloque pas ; FOR SHARE : ne bloque pas ; FOR KEY SHARE : ne bloque pas | ✅ |
| PG-02 | Quel verrou prend un `UPDATE` selon la colonne modifiée ? (une modification d'état ne doit pas bloquer les insertions qui référencent la ligne) | colonne ordinaire : ne bloque pas ; les autres cas sont à MESURER (ils décident du mode de verrou réellement pris par les changements d'état) | colonne ordinaire (`name`) : ne bloque pas ; colonne du prédicat d'un index unique partiel (`status`) : ne bloque pas ; colonne clé d'un index unique partiel (`dedup_key`) : ne bloque pas | ✅ |
| PG-03 | Conflits entre modes de verrou de ligne (base de TD27) | deux `NO KEY UPDATE` et `SHARE` / `NO KEY UPDATE` conflictuent ; `KEY SHARE` / `NO KEY UPDATE` sont compatibles ; `UPDATE` / `KEY SHARE` conflictuent | FOR NO KEY UPDATE puis FOR NO KEY UPDATE : conflit ; FOR SHARE puis FOR NO KEY UPDATE : conflit ; FOR KEY SHARE puis FOR NO KEY UPDATE : compatible ; FOR UPDATE puis FOR KEY SHARE : conflit | ✅ |
| PG-04 | Ordre croisé et ordre commun sur deux lignes | ordre croisé : un interblocage détecté (`40P01`) ; même ordre : aucun | ordre croisé : ['deadlock', 'ok'] ; même ordre : ['ok', 'ok'] | ✅ |
| PG-05 | Verrou consultatif pris en PREMIÈRE instruction d'une transaction `REPEATABLE READ` (TD29) : quand l'instantané est-il pris ? | à la demande du verrou, avant l'attente : après l'attente, la transaction ne voit PAS ce que le détenteur précédent a validé pendant ce temps ; en `READ COMMITTED`, elle le voit | `REPEATABLE READ` : 0 ligne(s) visible(s) ; `READ COMMITTED` : 1 | ✅ |
| PG-06 | `UPDATE … WHERE état = ancien` : deux travailleurs réclament la même action (H4) | le premier obtient 1 ligne ; le second attend puis obtient 0 ligne | premier : 1 ligne ; second : 0 ligne | ✅ |
| PG-07 | Un `INSERT` sur une clé unique déjà insérée par une transaction non validée (l'`INSERT` est une acquisition, mode `I`) | le second attend la première ; après validation : violation d'unicité (traduite en `REPLAY`) | attente : oui ; après validation : violation d'unicité | ✅ |
| PG-08 | Réclamation concurrente par `FOR UPDATE SKIP LOCKED` (relais, `ExecutionWorker`) | deux travailleurs obtiennent deux lignes différentes | A : 1 ; B : 2 | ✅ |
| PG-09 | RLS échoue fermé et le réglage `set_config(..., true)` est local à la transaction (TD17, TD26) | sans organisation posée : 0 ligne ; avec : 1 ligne ; après COMMIT le réglage est vide et 0 ligne à nouveau (compatible pooler en mode transaction) | sans réglage : 0 ; avec : 1 ; après COMMIT : réglage « vide », 0 ligne(s) | ✅ |
| PG-10 | Les vérifications de clé étrangère ne passent pas par RLS (TD17 : les FK composites gardent l'intégrité même si RLS masque le parent) | le parent est invisible (0 ligne) mais l'insertion d'un enfant valide est acceptée | parent visible : 0 ligne(s) ; insertion de l'enfant : insertion acceptée | ✅ |

## 5. Constats (écarts à décider)

### Constats

- l'ordre proposé au premier jet de TD27 est incompatible avec les opérations (cycle : import_batches, customers, payments, invoices, invoice_disputes, promises, collection_holds, automation_executions, collection_actions, approvals, notifications, event_receipts)
- événements sans abonné déclaré en V1 (à confirmer : simple journal ou consommateur manquant) : AUTOMATION_ARCHIVED, AUTOMATION_CREATED, AUTOMATION_EXECUTION_CANCELLED, AUTOMATION_EXECUTION_COMPLETED, AUTOMATION_EXECUTION_FAILED, AUTOMATION_EXECUTION_STARTED, AUTOMATION_VERSION_CREATED, CASHFLOW_UPDATED, COLLECTION_ACTION_CANCELLED, COLLECTION_ACTION_FAILED, COLLECTION_ACTION_PROPOSED, COLLECTION_ACTION_SCHEDULED, COLLECTION_ACTION_SUPPRESSED, CUSTOMER_CONTACT_ADDED, CUSTOMER_CONTACT_UPDATED, CUSTOMER_CREATED, CUSTOMER_UPDATED, IMPORT_BATCH_APPROVED, IMPORT_BATCH_CANCELLED, IMPORT_BATCH_FAILED, IMPORT_BATCH_READY, INVOICE_CREATED, MEMBER_ADDED, MEMBER_REMOVED, MEMBER_ROLE_CHANGED, NOTIFICATION_CREATED, ORGANIZATION_CREATED, ORGANIZATION_UPDATED, SUBSCRIPTION_CHANGED, USER_CREATED, USER_STATUS_CHANGED
- commandes au nom **créé par les registres** (figé en revue, hors documents figés antérieurs) : 0 sur 122 : 
