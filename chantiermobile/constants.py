"""
Centralized constants for ChantierMobile application
This file contains all shared constants, choices, and configuration values
to avoid hardcoding throughout the codebase.
"""

from django.utils.translation import gettext_lazy as _
from django.db import models


class UserRoles(models.TextChoices):
    """User role choices for cabinet assignments"""
    DIRECTOR = 'DIRECTOR', _('Directeur de Cabinet')
    DIRECTEUR_TECHNIQUE = 'DIRECTEUR_TECHNIQUE', _('Directeur Technique')
    DIRECTEUR_GENERAL = 'DIRECTEUR_GENERAL', _('Directeur Général')
    CHIEF_ENGINEER = 'CHIEF_ENGINEER', _('Chef des Ingénieurs')
    ENGINEER = 'ENGINEER', _('Ingénieur')
    FINANCIER = 'FINANCIER', _('Financier')
    ACCOUNTANT = 'ACCOUNTANT', _('Comptable')
    CASHIER = 'CASHIER', _('Caissier')
    MAGASINIER = 'MAGASINIER', _('Magasinier')
    WORKER = 'WORKER', _('Ouvrier')


# Roles empowered to give the second/final authorization on a state-of-need
# (état de besoin) or an avenant — the "Directeur Technique ou le Directeur
# Général" step named explicitly in the client's spec. DIRECTOR (Directeur
# de Cabinet) is included so existing single-cabinet setups that never
# created a dedicated DT/DG role keep working.
FINAL_AUTHORIZATION_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL']


class ApprovalStatus(models.TextChoices):
    """Common approval status choices used across multiple models"""
    PENDING = 'PENDING', _('En attente d\'approbation')
    APPROVED = 'APPROVED', _('Approuvé')
    REJECTED = 'REJECTED', _('Rejeté')


class ExpenseStatus(models.TextChoices):
    """Expense specific status choices"""
    PENDING = 'PENDING', _('En attente d\'approbation')
    APPROVED = 'APPROVED', _('Approuvé')
    REJECTED = 'REJECTED', _('Rejeté')
    PAID = 'PAID', _('Payé')


class MaterialRequestStatus(models.TextChoices):
    """Material request (état de besoin) status choices — a two-stage
    approval: the magasinier validates the request first, then a
    Directeur Technique/Général (or Directeur de Cabinet) gives the
    final authorization."""
    PENDING = 'PENDING', _('En attente')
    VALIDATED = 'VALIDATED', _('Validé par le magasinier')
    APPROVED = 'APPROVED', _('Approuvé')
    REJECTED = 'REJECTED', _('Rejeté')
    ORDERED = 'ORDERED', _('Commandé')
    DELIVERED = 'DELIVERED', _('Livré')


class SiteStatus(models.TextChoices):
    """Site/Project status choices"""
    PLANNING = 'PLANNING', _('En planification')
    ACTIVE = 'ACTIVE', _('Actif')
    PAUSED = 'PAUSED', _('En pause')
    COMPLETED = 'COMPLETED', _('Complété')
    CANCELLED = 'CANCELLED', _('Annulé')


class InvoiceStatus(models.TextChoices):
    """Invoice status choices"""
    DRAFT = 'DRAFT', _('Brouillon')
    SENT = 'SENT', _('Envoyé')
    PAID = 'PAID', _('Payé')
    OVERDUE = 'OVERDUE', _('En retard')
    CANCELLED = 'CANCELLED', _('Annulé')


class PaymentMethod(models.TextChoices):
    """Payment method choices"""
    BANK_TRANSFER = 'BANK_TRANSFER', _('Virement bancaire')
    CHECK = 'CHECK', _('Chèque')
    CASH = 'CASH', _('Espèces')
    MOBILE_MONEY = 'MOBILE_MONEY', _('Mobile Money')


class ExpenseNature(models.TextChoices):
    """Whether an expense pays for a material/purchase or for labor
    (main-d'œuvre) — drives whether the Personnel field is shown/required
    on the expense form."""
    MATERIEL = 'MATERIEL', _('Matériel')
    MAIN_DOEUVRE = 'MAIN_DOEUVRE', _("Main d'œuvre")
    AUTRE = 'AUTRE', _('Autre')


class CaisseType(models.TextChoices):
    """Which cash register (caisse) a purchase was funded from. A simple
    tag used for filtering/report purposes — not a balance-tracked ledger."""
    PRINCIPALE = 'PRINCIPALE', _('Caisse principale')
    SECONDAIRE = 'SECONDAIRE', _('Caisse secondaire')


class CaisseTransactionType(models.TextChoices):
    """Movement direction on a balance-tracked Caisse ledger entry."""
    ENTREE = 'ENTREE', _('Entrée')
    SORTIE = 'SORTIE', _('Sortie')


class PayrollListStatus(models.TextChoices):
    """Progressive worker-payment workflow: architecte prépare -> soumet à
    la caisse -> la caisse débourse."""
    BROUILLON = 'BROUILLON', _('Brouillon')
    SOUMISE = 'SOUMISE', _('Soumise à la caisse')
    PAYEE = 'PAYEE', _('Payée')


class AvenantStatus(models.TextChoices):
    """Project change-order (avenant) authorization workflow."""
    PENDING = 'PENDING', _("En attente d'autorisation")
    APPROVED = 'APPROVED', _('Autorisé')
    REJECTED = 'REJECTED', _('Rejeté')


class PurchasePaymentMethod(models.TextChoices):
    """How a PurchaseOrder was funded — caisse cash-on-hand, or a wire
    transfer initiated by the financier."""
    CAISSE = 'CAISSE', _('Caisse')
    VIREMENT = 'VIREMENT', _('Virement bancaire')


class DevisStatus(models.TextChoices):
    """Devis (quote/estimate) status choices"""
    BROUILLON = 'BROUILLON', _('Brouillon')
    ENVOYE = 'ENVOYE', _('Envoyé au client')
    ACCEPTE = 'ACCEPTE', _('Accepté')
    REFUSE = 'REFUSE', _('Refusé')
    EXPIRE = 'EXPIRE', _('Expiré')


class SituationStatus(models.TextChoices):
    """Situation de travaux (progress billing statement) status choices"""
    BROUILLON = 'BROUILLON', _('Brouillon')
    VALIDEE = 'VALIDEE', _('Validée')
    FACTUREE = 'FACTUREE', _('Facturée')


class PriceItemType(models.TextChoices):
    """Category of a price library item (Bibliothèque de Prix)"""
    LABOR = 'LABOR', _("Main d'œuvre")
    MATERIAL = 'MATERIAL', _('Matériau')
    EQUIPMENT = 'EQUIPMENT', _('Matériel')
    SERVICE = 'SERVICE', _('Prestation')
    WORK_ITEM = 'WORK_ITEM', _('Ouvrage (composite)')


class DQEStatus(models.TextChoices):
    """DQE (Détail Quantitatif Estimatif) status choices"""
    DRAFT = 'DRAFT', _('Brouillon')
    VALIDATED = 'VALIDATED', _('Validé')
    ARCHIVED = 'ARCHIVED', _('Archivé')


class PurchaseOrderStatus(models.TextChoices):
    """Purchase order (bon de commande) status choices"""
    BROUILLON = 'BROUILLON', _('Brouillon')
    ENVOYEE = 'ENVOYEE', _('Envoyée au fournisseur')
    RECUE_PARTIELLE = 'RECUE_PARTIELLE', _('Reçue partiellement')
    RECUE = 'RECUE', _('Reçue')
    ANNULEE = 'ANNULEE', _('Annulée')


class StockMovementType(models.TextChoices):
    """Stock movement type choices"""
    IN = 'IN', _('Entrée')
    OUT = 'OUT', _('Sortie')
    ADJUSTMENT = 'ADJUSTMENT', _('Ajustement')
    TRANSFER = 'TRANSFER', _('Transfert')


class StockReportPeriod(models.TextChoices):
    """Periodicity for the stock report — "rapports périodiques
    (journalier/hebdomadaire/mensuel/trimestriel/annuel)" from the
    client's spec."""
    JOURNALIER = 'JOURNALIER', _('Journalier')
    HEBDOMADAIRE = 'HEBDOMADAIRE', _('Hebdomadaire')
    MENSUEL = 'MENSUEL', _('Mensuel')
    TRIMESTRIEL = 'TRIMESTRIEL', _('Trimestriel')
    ANNUEL = 'ANNUEL', _('Annuel')


class PersonnelType(models.TextChoices):
    """Employment relationship of a Personnel record"""
    EMPLOYE = 'EMPLOYE', _('Employé')
    TACHERON = 'TACHERON', _('Tâcheron (journalier)')
    PRESTATAIRE = 'PRESTATAIRE', _('Prestataire (sous-traitant)')


class AgentCategory(models.TextChoices):
    """Whether a Personnel record is field staff or office/administration
    staff — "agent de terrain ou d'administration" in the client's spec."""
    TERRAIN = 'TERRAIN', _('Agent de terrain')
    ADMINISTRATION = 'ADMINISTRATION', _("Agent d'administration")


class PersonnelStatus(models.TextChoices):
    """Eligibility status for a worker/agent."""
    ACTIF = 'ACTIF', _('Actif')
    INACTIF = 'INACTIF', _('Inactif')
    NON_ELIGIBLE = 'NON_ELIGIBLE', _('Non éligible')


class PersonnelPayrollType(models.TextChoices):
    """Which payroll track a Personnel's payments fall under — the two are
    kept strictly separate, each with its own tab, workflow and caisse
    category:

    - OUVRIER: paid progressively per chantier, capped by the
      SiteAssignment.convention_amount when one is set. Handled by the
      chantier-scoped "Liste de paie" / PayrollList ("Main d'œuvre" tab) —
      booked to the "Main d'œuvre Ouvriers" caisse category on décaissement.
    - INGENIEUR: paid a fixed monthly salary, not tied to a chantier.
      Handled by SalaryPaymentList/SalaryPaymentItem ("Ingénieurs & Staff"
      tab) — cabinet-scoped brouillon/soumise/payée workflow mirroring
      PayrollList, booked to the "Salaire Ingénieurs" caisse category on
      décaissement. Covers both engineers and administrative/office staff
      (AgentCategory.ADMINISTRATION), whether or not they're also assigned
      to a site.
    """
    OUVRIER = 'OUVRIER', _("Ouvrier (main d'œuvre)")
    INGENIEUR = 'INGENIEUR', _('Ingénieur / Staff')


class Trade(models.TextChoices):
    """Fixed trade/function list for ouvriers, as specified by the client."""
    MACON = 'MACON', _('Maçon')
    MENUISIER = 'MENUISIER', _('Menuisier')
    FERRAILLEUR = 'FERRAILLEUR', _('Ferrailleur')
    PLOMBIER = 'PLOMBIER', _('Plombier')
    ELECTRICIEN = 'ELECTRICIEN', _('Électricien')
    AJUSTEUR = 'AJUSTEUR', _('Ajusteur')
    PEINTRE = 'PEINTRE', _('Peintre')
    VITRIER = 'VITRIER', _('Vitrier')
    CARRELEUR = 'CARRELEUR', _('Carreleur')
    CONSULTANT = 'CONSULTANT', _('Consultant')


class LeaveType(models.TextChoices):
    """Kind of personnel absence."""
    CONGE = 'CONGE', _('Congé')
    JOUR_FERIE = 'JOUR_FERIE', _('Jour férié')
    MALADIE = 'MALADIE', _('Congé maladie')
    AUTRE = 'AUTRE', _('Autre')


class TaskStatus(models.TextChoices):
    """Task tracking status choices"""
    A_FAIRE = 'A_FAIRE', _('À faire')
    EN_COURS = 'EN_COURS', _('En cours')
    BLOQUEE = 'BLOQUEE', _('Bloquée')
    TERMINEE = 'TERMINEE', _('Terminée')


class TaskPriority(models.TextChoices):
    """Task priority choices"""
    BASSE = 'BASSE', _('Basse')
    NORMALE = 'NORMALE', _('Normale')
    HAUTE = 'HAUTE', _('Haute')
    URGENTE = 'URGENTE', _('Urgente')


class PlanningStatus(models.TextChoices):
    """Status of a site/phase planning submission awaiting review by the
    concerned engineer(s) — "Soumettre la planification aux ingénieurs
    concernés" from the client's spec."""
    BROUILLON = 'BROUILLON', _('Brouillon')
    SOUMISE = 'SOUMISE', _('Soumise')
    APPROUVEE = 'APPROUVEE', _('Approuvée')
    REJETEE = 'REJETEE', _('Rejetée')


class PhaseStatus(models.TextChoices):
    """Status of a ProjectPhase (étape) — closed by the site's lead
    engineer ("l'ingénieur principal clôture les étapes du projet")."""
    EN_COURS = 'EN_COURS', _('En cours')
    CLOTUREE = 'CLOTUREE', _('Clôturée')


# Form field placeholders and UI constants
class FormPlaceholders:
    """Centralized placeholder text for form fields"""
    
    # Common placeholders
    MATERIAL_NAME = _('Material Name')
    FIRST_NAME = _('First Name')
    LAST_NAME = _('Last Name')
    DESCRIPTION = _('Description')
    AMOUNT = '0.00'
    DATE_FORMAT = 'YYYY-MM-DD'
    
    # Specific placeholders
    MATERIAL_UNIT = _('e.g. kg, m3, liters')
    EXPENSE_DETAILS = _('Expense details...')
    PROJECT_SITE = _('Project / Site')
    CLIENT_NAME = _('Client Name')
    INVOICE_NUMBER = _('INV-000')
    TRANSACTION_REFERENCE = _('Transaction Reference')
    DEVIS_NUMBER = _('DEV-000')
    DESIGNATION = _('Désignation du poste')
    PURCHASE_ORDER_NUMBER = _('BC-000')
    SUPPLIER_NAME = _('Nom du fournisseur')
    TASK_TITLE = _('Titre de la tâche')
    
    # Personnel specific
    ROLE_EXAMPLE = _("e.g. Chef d'équipe")
    SKILL_NAME = _('Skill Name')
    
    # Project specific
    SITE_NAME = _('Site Name')
    LOCATION = _('Location / Address')
    PHASE_NAME = _('Phase Name (e.g. Foundation)')
    PROGRESS_DESCRIPTION = _('What was accomplished today?')


class FormHelpTexts:
    """Centralized help text for form fields"""
    
    MATERIAL_UNIT = _('e.g. kg, m3, liters')
    DEFAULT_DAILY_COST = _('Default daily cost')
    SPECIFIC_ROLE = _("Specific role on this site, e.g. Chef d'équipe")
    AGREED_RATE = _('Agreed rate for this specific assignment')
    CONTRACT_VALUE = _('Total contract value')
    TRANSACTION_ID = _('Transaction ID or Check Number')
    ADDITIONAL_NOTES = _('Additional notes or special instructions...')
    ITEM_NOTES = _('Notes for this item (optional)')


class DatePickerConfig:
    """Configuration for date picker widgets"""
    DATE_FORMAT = 'YYYY-MM-DD'
    DATEPATTERN = 'Y-m-d'
    DISABLE_MOBILE = True
    OPTIONS = '{"dateFormat":"Y-m-d","disableMobile":true}'


class StatusBadgeClasses:
    """CSS classes for status badges"""
    
    # Site status badge classes
    SITE_STATUS = {
        SiteStatus.ACTIVE: 'bg-success',
        SiteStatus.PLANNING: 'bg-primary',
        SiteStatus.PAUSED: 'bg-warning',
        SiteStatus.COMPLETED: 'bg-secondary',
        SiteStatus.CANCELLED: 'bg-danger',
    }
    
    # Expense status badge classes
    EXPENSE_STATUS = {
        ExpenseStatus.PAID: 'bg-info',
        ExpenseStatus.APPROVED: 'bg-success',
        ExpenseStatus.REJECTED: 'bg-danger',
        ExpenseStatus.PENDING: 'bg-warning',
    }
    
    # Material request status badge classes
    MATERIAL_REQUEST_STATUS = {
        MaterialRequestStatus.APPROVED: 'bg-success',
        MaterialRequestStatus.DELIVERED: 'bg-info',
        MaterialRequestStatus.REJECTED: 'bg-danger',
        MaterialRequestStatus.PENDING: 'bg-warning',
        MaterialRequestStatus.VALIDATED: 'bg-primary',
        MaterialRequestStatus.ORDERED: 'bg-primary',
    }
    
    # Invoice status badge classes
    INVOICE_STATUS = {
        InvoiceStatus.PAID: 'bg-success',
        InvoiceStatus.SENT: 'bg-info',
        InvoiceStatus.OVERDUE: 'bg-danger',
        InvoiceStatus.DRAFT: 'bg-warning',
        InvoiceStatus.CANCELLED: 'bg-secondary',
    }

    # Devis status badge classes
    DEVIS_STATUS = {
        DevisStatus.ACCEPTE: 'bg-success',
        DevisStatus.ENVOYE: 'bg-info',
        DevisStatus.REFUSE: 'bg-danger',
        DevisStatus.EXPIRE: 'bg-secondary',
        DevisStatus.BROUILLON: 'bg-warning',
    }

    # Situation de travaux status badge classes
    SITUATION_STATUS = {
        SituationStatus.FACTUREE: 'bg-success',
        SituationStatus.VALIDEE: 'bg-info',
        SituationStatus.BROUILLON: 'bg-warning',
    }

    # Purchase order status badge classes
    PURCHASE_ORDER_STATUS = {
        PurchaseOrderStatus.RECUE: 'bg-success',
        PurchaseOrderStatus.RECUE_PARTIELLE: 'bg-info',
        PurchaseOrderStatus.ENVOYEE: 'bg-primary',
        PurchaseOrderStatus.ANNULEE: 'bg-danger',
        PurchaseOrderStatus.BROUILLON: 'bg-warning',
    }

    # Task status badge classes
    TASK_STATUS = {
        TaskStatus.TERMINEE: 'bg-success',
        TaskStatus.EN_COURS: 'bg-info',
        TaskStatus.BLOQUEE: 'bg-danger',
        TaskStatus.A_FAIRE: 'bg-warning',
    }

    # Task priority badge classes
    TASK_PRIORITY = {
        TaskPriority.URGENTE: 'bg-danger',
        TaskPriority.HAUTE: 'bg-warning',
        TaskPriority.NORMALE: 'bg-info',
        TaskPriority.BASSE: 'bg-secondary',
    }

    # Personnel type badge classes
    PERSONNEL_TYPE = {
        PersonnelType.EMPLOYE: 'bg-primary',
        PersonnelType.TACHERON: 'bg-warning',
        PersonnelType.PRESTATAIRE: 'bg-info',
    }

    # Personnel status badge classes
    PERSONNEL_STATUS = {
        PersonnelStatus.ACTIF: 'bg-success',
        PersonnelStatus.INACTIF: 'bg-secondary',
        PersonnelStatus.NON_ELIGIBLE: 'bg-danger',
    }

    # Leave request status badge classes (reuses ApprovalStatus)
    LEAVE_STATUS = {
        ApprovalStatus.APPROVED: 'bg-success',
        ApprovalStatus.REJECTED: 'bg-danger',
        ApprovalStatus.PENDING: 'bg-warning',
    }

    # Planning submission status badge classes
    PLANNING_STATUS = {
        PlanningStatus.APPROUVEE: 'bg-success',
        PlanningStatus.REJETEE: 'bg-danger',
        PlanningStatus.SOUMISE: 'bg-info',
        PlanningStatus.BROUILLON: 'bg-warning',
    }

    # Project phase status badge classes
    PHASE_STATUS = {
        PhaseStatus.CLOTUREE: 'bg-secondary',
        PhaseStatus.EN_COURS: 'bg-info',
    }


class ValidationMessages:
    """Common validation messages"""
    
    REQUIRED_FIELD = _('This field is required.')
    INVALID_EMAIL = _('Enter a valid email address.')
    INVALID_DATE = _('Enter a valid date.')
    POSITIVE_NUMBER = _('Enter a positive number.')
    FUTURE_DATE = _('Date must be in the future.')
    PAST_DATE = _('Date must be in the past.')
    
    # Business logic validations
    END_DATE_AFTER_START = _('End date must be after start date.')
    BUDGET_EXCEEDED = _('Budget limit exceeded.')
    INSUFFICIENT_PERMISSIONS = _('You do not have permission to perform this action.')


class FileUploadConfig:
    """File upload configurations"""
    
    # Upload paths
    CABINET_LOGO_PATH = 'cabinets/logos/'
    EXPENSE_RECEIPT_PATH = 'expenses/receipts/'
    
    # File size limits (in bytes)
    MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
    MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10MB
    
    # Allowed file types
    ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif']
    ALLOWED_DOCUMENT_TYPES = ['application/pdf', 'image/jpeg', 'image/png']


class PaginationConfig:
    """Pagination settings"""
    
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100
    PAGE_SIZE_CHOICES = [
        (10, '10'),
        (20, '20'),
        (50, '50'),
        (100, '100'),
    ]


class CurrencyConfig:
    """Currency configuration"""
    
    DEFAULT_CURRENCY = 'USD'
    CURRENCY_SYMBOL = '$'
    DECIMAL_PLACES = 2


class ProjectConfig:
    """Project-specific configuration"""
    
    # Progress percentage validation
    MIN_PROGRESS = 0
    MAX_PROGRESS = 100
    
    # Default values
    DEFAULT_DAILY_RATE = 0
    MIN_DAILY_RATE = 0


# Export commonly used constants for easy import
__all__ = [
    # Choice classes
    'UserRoles',
    'ApprovalStatus', 
    'ExpenseStatus',
    'MaterialRequestStatus',
    'SiteStatus',
    'InvoiceStatus',
    'PaymentMethod',
    'ExpenseNature',
    'CaisseType',
    'CaisseTransactionType',
    'PayrollListStatus',
    'AvenantStatus',
    'PurchasePaymentMethod',
    'DevisStatus',
    'SituationStatus',
    'PriceItemType',
    'DQEStatus',
    'PurchaseOrderStatus',
    'StockMovementType',
    'PersonnelType',
    'AgentCategory',
    'PersonnelStatus',
    'Trade',
    'LeaveType',
    'FINAL_AUTHORIZATION_ROLES',
    'TaskStatus',
    'TaskPriority',
    'PlanningStatus',
    'PhaseStatus',
    'StockReportPeriod',

    # Configuration classes
    'FormPlaceholders',
    'FormHelpTexts',
    'DatePickerConfig',
    'StatusBadgeClasses',
    'ValidationMessages',
    'FileUploadConfig',
    'PaginationConfig',
    'CurrencyConfig',
    'ProjectConfig',
]
