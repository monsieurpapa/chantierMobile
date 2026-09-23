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

    Deliberately superuser-only: this runs on *every* request that renders
    a template, so it must stay free for the common case. Extending it to
    also query a regular user's own cabinet memberships on every page load
    was tried and reverted — it broke the app's query-count budget (see
    tests/test_performance.py), for a switcher most users would never use
    (multi-cabinet *regular* staff are the rare case, not the default).
    A regular multi-cabinet user's cabinet ambiguity on *creation* forms
    (PriceLibraryItemCreateView, DQECreateView, ...) is instead resolved
    locally on those specific forms — see get_session_cabinet's docstring
    in core/mixins.py, which regular users can still populate via
    accounts:switch_cabinet even though no navbar UI links to it for them.
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
