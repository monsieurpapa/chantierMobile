"""
Template filter for role-gating what a template renders (e.g. hiding an
action button a user couldn't actually use) — a read-only convenience for
display only. It is NOT a substitute for the server-side check
(RoleRequiredMixin / can_act_for_cabinet) on the view or action itself;
see docs/security.md.
"""
from django import template
from accounts.models import UserCabinetRole
from chantiermobile.constants import ApprovalStatus

register = template.Library()

@register.filter(name='has_role')
def has_role(user, role_names):
    """
    Usage: {% if request.user|has_role:'DIRECTOR,CHIEF_ENGINEER' %}

    Cached per (user, role_names) on the user instance — templates commonly
    call this once per row in a list (e.g. per-site action buttons), and the
    result never changes within a single request, so re-querying each time
    is pure N+1.

    FIXED 2026-10-06: only counts an APPROVED UserCabinetRole — a
    PENDING grant no longer lights up an action button it shouldn't
    (the server-side check this is paired with is fixed the same way;
    see core/mixins.py and docs/security.md).
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
        cache[role_names] = UserCabinetRole.objects.filter(user=user, role__in=roles, status=ApprovalStatus.APPROVED).exists()
    return cache[role_names]
