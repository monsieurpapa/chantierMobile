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
    CHIEF_ENGINEER = 'CHIEF_ENGINEER', _('Chef des Ingénieurs')
    ENGINEER = 'ENGINEER', _('Ingénieur')
    ACCOUNTANT = 'ACCOUNTANT', _('Comptable')
    CASHIER = 'CASHIER', _('Caissier')
    WORKER = 'WORKER', _('Ouvrier')


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
    """Material request specific status choices"""
    PENDING = 'PENDING', _('En attente')
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
    'DevisStatus',
    'SituationStatus',
    'PriceItemType',
    'DQEStatus',
    'PurchaseOrderStatus',
    'StockMovementType',

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
