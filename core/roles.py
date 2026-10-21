"""
Role helpers for the Magasinier (store-keeper) role, added 2026-10-21.

A Magasinier belongs to one chantier (UserCabinetRole.site). There, and
only there, they record stock entries and exits (create, edit, delete);
everyone else sees those movements read-only. A Magasinier sees
quantities, never prices.
"""
from chantiermobile.constants import ApprovalStatus, UserRoles


def magasinier_site_ids(user):
    """Ids of the chantiers `user` is the (approved) Magasinier of."""
    if user is None or not user.is_authenticated:
        return set()
    cache = getattr(user, '_magasinier_site_ids', None)
    if cache is None:
        from accounts.models import UserCabinetRole
        cache = set(
            UserCabinetRole.objects.filter(
                user=user, role=UserRoles.MAGASINIER, status=ApprovalStatus.APPROVED, site__isnull=False,
            ).values_list('site_id', flat=True)
        )
        user._magasinier_site_ids = cache
    return cache


def is_site_magasinier(user, site):
    """True when `user` is the Magasinier of `site` — the one person who
    may record, edit or delete stock entries and exits there."""
    return site is not None and site.pk in magasinier_site_ids(user)


def is_magasinier_only(user):
    """True for a user whose only approved roles are Magasinier: they are
    scoped to their chantier(s) and shown quantities, never prices.
    Superusers and anyone holding another role somewhere are not."""
    if user is None or not user.is_authenticated or user.is_superuser:
        return False
    cache = getattr(user, '_is_magasinier_only', None)
    if cache is None:
        roles = set(user.approved_cabinet_roles.values_list('role', flat=True))
        cache = bool(roles) and roles == {UserRoles.MAGASINIER}
        user._is_magasinier_only = cache
    return cache


class MagasinierSiteScopeMixin:
    """For list/detail views of chantier data: a Magasinier only sees their
    own chantier(s). Place it before CabinetAccessMixin."""
    magasinier_site_field = 'site_id'

    def get_queryset(self):
        qs = super().get_queryset()
        if is_magasinier_only(self.request.user):
            qs = qs.filter(**{f'{self.magasinier_site_field}__in': magasinier_site_ids(self.request.user)})
        return qs


def can_record_stock(request, site):
    """May this request record, edit, delete or transfer entrées/sorties
    at `site`? The chantier's Magasinier — or a superadmin."""
    from core.mixins import can_act_for_cabinet
    if site is None:
        return False
    if request.user.is_superuser:
        return can_act_for_cabinet(request, site.cabinet, [])
    return is_site_magasinier(request.user, site)


def stock_editor_site_ids(request):
    """Chantiers where this request may record entrées/sorties: the
    Magasinier's own, or for a superadmin every chantier (of the cabinet
    their session is switched to, if any)."""
    user = request.user
    if user.is_authenticated and user.is_superuser:
        from core.mixins import get_session_cabinet
        from projects.models import Site
        cabinet = get_session_cabinet(request)
        qs = Site.objects.filter(cabinet=cabinet) if cabinet else Site.objects.all()
        return set(qs.values_list('pk', flat=True))
    return magasinier_site_ids(user)
