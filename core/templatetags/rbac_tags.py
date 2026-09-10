from django import template
from accounts.models import UserCabinetRole

register = template.Library()

@register.filter(name='has_role')
def has_role(user, role_names):
    """
    Usage: {% if request.user|has_role:'DIRECTOR,CHIEF_ENGINEER' %}

    Cached per (user, role_names) on the user instance — templates commonly
    call this once per row in a list (e.g. per-site action buttons), and the
    result never changes within a single request, so re-querying each time
    is pure N+1.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    cache = getattr(user, '_has_role_cache', None)
    if cache is None:
        cache = user._has_role_cache = {}
    if role_names not in cache:
        roles = role_names.split(',')
        cache[role_names] = UserCabinetRole.objects.filter(user=user, role__in=roles).exists()
    return cache[role_names]
