"""
Context processors for multilingual support
Automatically adds language information to template context
"""

from django.conf import settings
from django.utils import translation


def language_context(request):
    """
    Add language information to template context
    Available in all templates via {{ current_language }}, {{ languages }}, {{ LANGUAGES }}
    """
    current_lang = translation.get_language() or settings.LANGUAGE_CODE
    
    languages = []
    for code, name in settings.LANGUAGES:
        languages.append({
            'code': code,
            'name': name,
            'is_active': code == current_lang,
        })
    
    return {
        'current_language': current_lang,
        'languages': languages,
        'LANGUAGE_CODE': current_lang,
        'LANGUAGES': settings.LANGUAGES,  # Make LANGUAGES available to templates
    }


def site_info_context(request):
    """
    Add general site information to template context
    """
    return {
        'LANGUAGE_COOKIE_NAME': settings.LANGUAGE_COOKIE_NAME,
    }
