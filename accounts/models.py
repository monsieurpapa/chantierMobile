"""
Identity and multi-tenancy models: the custom User, the Cabinet tenant
boundary, the UserCabinetRole grant that is the system's entire
authorization model, and the CabinetContextLog audit trail for the
superuser cabinet-switcher. See docs/modules/accounts.md and
docs/architecture/overview.md#multi-tenancy-cabinet for the full picture —
nothing in this app is keyed off Django's built-in permission/group
system; every access decision elsewhere in the codebase goes through
UserCabinetRole instead.
"""
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from chantiermobile.constants import UserRoles, ApprovalStatus

class User(AbstractUser):
    """Extension of Django's AbstractUser. Carries no role or Cabinet
    information itself — that lives entirely in UserCabinetRole, so a
    single user can hold different roles in different Cabinets (or none)
    without this model changing shape."""
    # Extension of standard user
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    must_change_password = models.BooleanField(
        default=False,
        help_text='If true, the user is forced to change their password before using the rest of the app.',
    )

    def __str__(self):
        return self.username

    @property
    def approved_cabinet_roles(self):
        """FIXED 2026-10-06: `self.cabinet_roles` (the plain reverse FK
        manager) returns every UserCabinetRole row regardless of
        `status`, including a PENDING one a superadmin hasn't approved
        yet — and every RBAC helper that queried it directly (or ran
        its own equivalent `UserCabinetRole.objects.filter(...)`)
        treated a PENDING grant as fully active, contrary to the
        model's own docstring ("only APPROVED is meant to grant access
        in practice"). Every access-control check should go through
        this property (or filter on status=ApprovalStatus.APPROVED
        directly) instead of the bare `cabinet_roles` manager — see
        docs/security.md. An *informational* listing that intentionally
        shows a user their own pending assignments (e.g. a profile
        page) should keep using `cabinet_roles` directly; this property
        is only for "does this grant actually authorize anything"."""
        return self.cabinet_roles.filter(status=ApprovalStatus.APPROVED)

class Cabinet(BaseModel):
    """A tenant: one construction firm, or one branch of one. This is the
    isolation boundary for every business model in the system (sites,
    personnel, finance, materials, revenue, ...) — see ADR 0001. A Cabinet
    itself carries no owner/admin reference; who can act on it is entirely
    determined by UserCabinetRole rows pointing at it."""
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    tax_id = models.CharField(max_length=50, blank=True, help_text=_("NIF/TIN"))
    logo = models.ImageField(upload_to='cabinets/logos/', blank=True, null=True)

    def __str__(self):
        return self.name

class UserCabinetRole(BaseModel):
    """The authorization grant: (user, cabinet, role). This single table
    is what every RBAC check in the codebase queries — CabinetAccessMixin,
    RoleRequiredMixin, can_act_for_cabinet, can_view_cabinet, has_role —
    there is no other permission store. `unique_together` caps a user at
    one role per Cabinet (to hold a second role there, the existing row
    must be changed, not duplicated). `status` (ApprovalStatus) lets a
    superadmin stage an assignment as PENDING before it takes effect;
    only APPROVED is meant to grant access in practice, though the RBAC
    helpers themselves don't filter on status — enforcing that is on
    whatever creates/approves the row (see accounts/views.py's admin
    assignment views)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cabinet_roles')
    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='user_roles')
    role = models.CharField(max_length=50, choices=UserRoles.choices)
    status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )

    class Meta:
        unique_together = ('user', 'cabinet')

    def __str__(self):
        return f"{self.user.username} - {self.role} @ {self.cabinet.name}"


class CabinetContextLog(models.Model):
    """Audit log for superadmin cabinet context switches."""
    SWITCH = 'SWITCH'
    CLEAR = 'CLEAR'
    ACTION_CHOICES = [
        (SWITCH, 'Switch to Cabinet'),
        (CLEAR, 'Clear to All Cabinets'),
    ]

    cabinet = models.ForeignKey(
        Cabinet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='context_logs',
    )
    switched_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='cabinet_context_logs',
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        if self.action == self.SWITCH:
            return f"{self.switched_by} → {self.cabinet}"
        return f"{self.switched_by} → All Cabinets"
