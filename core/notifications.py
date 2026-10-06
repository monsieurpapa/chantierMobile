"""
Helpers for creating in-app Notification rows (item 13 of the Directors/
Engineers audit). Two shapes cover every workflow in the app:

- notify_role_holders(cabinet, roles, message, url, exclude_user=None):
  "something needs your decision" — fanned out to everyone in that
  cabinet holding one of `roles`, mirroring the same role lists used for
  the pending-approvals inbox (core/approvals.py) and each view's own
  allowed_roles / can_act_for_cabinet check.
- notify_user(user, message, url): "your request was decided" — sent
  back to whoever submitted it.

Both are silent no-ops on bad input (no cabinet, no matching users, a
None user) rather than raising, since a notification is a side effect
that should never block the request that triggered it.
"""


def notify_role_holders(cabinet, roles, message, url, exclude_user=None):
    """Fan out one Notification to every user holding one of `roles` in
    `cabinet` — the "something needs your decision" direction. Pass
    exclude_user to skip the actor who just triggered this (e.g. a
    director approving their own prior comment), so they don't get
    notified about their own action."""
    if cabinet is None:
        return
    from accounts.models import UserCabinetRole
    from core.models import Notification

    user_ids = set(
        UserCabinetRole.objects.filter(cabinet=cabinet, role__in=roles).values_list('user_id', flat=True)
    )
    if exclude_user is not None:
        user_ids.discard(exclude_user.pk)
    if not user_ids:
        return
    Notification.objects.bulk_create([
        Notification(recipient_id=user_id, message=message, url=url) for user_id in user_ids
    ])


def notify_user(user, message, url):
    """Sends one Notification to a single user — the "your request was
    decided" direction, back to whoever originally submitted it."""
    if user is None:
        return
    from core.models import Notification
    Notification.objects.create(recipient=user, message=message, url=url)
