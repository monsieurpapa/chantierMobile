from django import template
from accounts.models import UserCabinetRole

register = template.Library()

@register.filter(name='has_role')
def has_role(user, role_names):
    """
    Usage: {% if request.user|has_role:'DIRECTOR,CHIEF_ENGINEER' %}
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
        
    roles = role_names.split(',')
    return UserCabinetRole.objects.filter(user=user, role__in=roles).exists()
