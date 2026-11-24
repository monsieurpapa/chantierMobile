"""Display helpers for the superadmin audit journal templates."""
from django import template

register = template.Library()

_BADGES = {
    'CREATE': ('success', 'plus'),
    'UPDATE': ('info', 'pen'),
    'DELETE': ('warning', 'trash-alt'),
    'RESTORE': ('primary', 'undo'),
    'HARD_DELETE': ('danger', 'times-circle'),
    'LOGIN': ('secondary', 'sign-in-alt'),
    'LOGOUT': ('secondary', 'sign-out-alt'),
    'LOGIN_FAILED': ('danger', 'user-lock'),
    'CABINET_SWITCH': ('dark', 'exchange-alt'),
}


@register.filter
def audit_badge(action):
    """Bootstrap colour suffix for an action badge (badge-soft-<colour>)."""
    return _BADGES.get(action, ('secondary', 'circle'))[0]


@register.filter
def audit_icon(action):
    """Font Awesome icon name for an action."""
    return _BADGES.get(action, ('secondary', 'circle'))[1]


@register.simple_tag(takes_context=True)
def audit_history_url(context, obj):
    """Link to the journal filtered to one record's history, for a
    superadmin; '' for anyone else (so `{% if url %}` hides the button).
    Usage: {% audit_history_url site as history_url %}"""
    from core.audit import history_url_for
    return history_url_for(getattr(context.get('request'), 'user', None), obj)


@register.filter
def audit_change_rows(changes):
    """The entry's changes as a list of {label, old, new} dicts."""
    return list(changes.values()) if isinstance(changes, dict) else []
