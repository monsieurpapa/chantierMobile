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


def active_cabinet_context(request):
    """
    Inject active_cabinet and all_cabinets for superadmin cabinet switcher.
    """
    if not request.user.is_authenticated or not request.user.is_superuser:
        return {}

    from accounts.models import Cabinet

    cabinet_id = request.session.get('active_cabinet_id')
    active_cabinet = None

    if cabinet_id:
        try:
            active_cabinet = Cabinet.objects.get(pk=int(cabinet_id))
        except (Cabinet.DoesNotExist, ValueError, TypeError):
            try:
                del request.session['active_cabinet_id']
            except KeyError:
                pass

    return {
        'active_cabinet': active_cabinet,
        'all_cabinets': Cabinet.objects.order_by('name'),
    }
