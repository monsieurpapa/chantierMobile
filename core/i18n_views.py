"""
Language switching views for multilingual support
"""

from django.http import HttpResponseRedirect
from django.views.i18n import set_language as django_set_language
from django.conf import settings
from django.utils import translation
from django.contrib import messages


def set_language_view(request):
    """
    Set language and redirect to next page or referrer
    Supports POST method for CSRF protection
    """
    language = request.POST.get('language') or request.GET.get('language')
    
    # Validate language code
    if language not in dict(settings.LANGUAGES):
        language = settings.LANGUAGE_CODE
    
    # Activate language
    translation.activate(language)
    request.session[translation.LANGUAGE_SESSION_KEY] = language
    
    # Get redirect URL
    next_url = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER', '/')
    
    # Ensure next_url is safe
    if next_url.startswith('http'):
        next_url = '/'
    
    # Create response
    response = HttpResponseRedirect(next_url)
    response.set_cookie(settings.LANGUAGE_COOKIE_NAME, language, 
                       max_age=settings.LANGUAGE_COOKIE_AGE)
    
    return response


def get_language_info(request):
    """
    Get information about available languages for template context
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
    }
