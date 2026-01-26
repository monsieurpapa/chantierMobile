"""
Multilingual support utilities for ChantiérMobile
Provides helpers for managing French and English translations
"""

from django.utils.translation import gettext_lazy as _
from django.utils import translation

# Common translations dictionary for quick reference
TRANSLATIONS = {
    # Common actions
    'create': {
        'fr': 'Créer',
        'en': 'Create',
    },
    'edit': {
        'fr': 'Modifier',
        'en': 'Edit',
    },
    'delete': {
        'fr': 'Supprimer',
        'en': 'Delete',
    },
    'save': {
        'fr': 'Enregistrer',
        'en': 'Save',
    },
    'cancel': {
        'fr': 'Annuler',
        'en': 'Cancel',
    },
    'submit': {
        'fr': 'Soumettre',
        'en': 'Submit',
    },
    'approve': {
        'fr': 'Approuver',
        'en': 'Approve',
    },
    'reject': {
        'fr': 'Rejeter',
        'en': 'Reject',
    },
    'search': {
        'fr': 'Rechercher',
        'en': 'Search',
    },
    'filter': {
        'fr': 'Filtrer',
        'en': 'Filter',
    },
    'export': {
        'fr': 'Exporter',
        'en': 'Export',
    },
    'import': {
        'fr': 'Importer',
        'en': 'Import',
    },
    'back': {
        'fr': 'Retour',
        'en': 'Back',
    },
    'next': {
        'fr': 'Suivant',
        'en': 'Next',
    },
    'previous': {
        'fr': 'Précédent',
        'en': 'Previous',
    },
    'yes': {
        'fr': 'Oui',
        'en': 'Yes',
    },
    'no': {
        'fr': 'Non',
        'en': 'No',
    },
    
    # Common fields
    'name': {
        'fr': 'Nom',
        'en': 'Name',
    },
    'email': {
        'fr': 'E-mail',
        'en': 'Email',
    },
    'phone': {
        'fr': 'Téléphone',
        'en': 'Phone',
    },
    'address': {
        'fr': 'Adresse',
        'en': 'Address',
    },
    'date': {
        'fr': 'Date',
        'en': 'Date',
    },
    'description': {
        'fr': 'Description',
        'en': 'Description',
    },
    'status': {
        'fr': 'Statut',
        'en': 'Status',
    },
    'amount': {
        'fr': 'Montant',
        'en': 'Amount',
    },
    'total': {
        'fr': 'Total',
        'en': 'Total',
    },
    'price': {
        'fr': 'Prix',
        'en': 'Price',
    },
    'quantity': {
        'fr': 'Quantité',
        'en': 'Quantity',
    },
    'notes': {
        'fr': 'Notes',
        'en': 'Notes',
    },
    
    # Common messages
    'success': {
        'fr': 'Succès',
        'en': 'Success',
    },
    'error': {
        'fr': 'Erreur',
        'en': 'Error',
    },
    'warning': {
        'fr': 'Avertissement',
        'en': 'Warning',
    },
    'info': {
        'fr': 'Information',
        'en': 'Information',
    },
    'created_successfully': {
        'fr': 'Créé avec succès',
        'en': 'Created successfully',
    },
    'updated_successfully': {
        'fr': 'Mis à jour avec succès',
        'en': 'Updated successfully',
    },
    'deleted_successfully': {
        'fr': 'Supprimé avec succès',
        'en': 'Deleted successfully',
    },
    'please_confirm': {
        'fr': 'Veuillez confirmer',
        'en': 'Please confirm',
    },
    'are_you_sure': {
        'fr': 'Êtes-vous sûr?',
        'en': 'Are you sure?',
    },
}


def get_translated_text(key, language='en'):
    """
    Get translated text from TRANSLATIONS dictionary
    
    Args:
        key: Translation key
        language: 'fr' for French, 'en' for English
        
    Returns:
        Translated text or original key if not found
    """
    if key in TRANSLATIONS and language in TRANSLATIONS[key]:
        return TRANSLATIONS[key][language]
    return key


def set_language(request, language):
    """
    Set the language in the session and activate it
    
    Args:
        request: HttpRequest object
        language: 'fr' or 'en'
    """
    if language in ['fr', 'en']:
        request.session['django_language'] = language
        translation.activate(language)
        request.session[translation.LANGUAGE_SESSION_KEY] = language


def get_active_language(request):
    """
    Get the currently active language for a request
    
    Args:
        request: HttpRequest object
        
    Returns:
        'fr' or 'en'
    """
    return translation.get_language() or request.session.get('django_language', 'fr')
