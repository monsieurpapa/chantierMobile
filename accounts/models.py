from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from chantiermobile.constants import UserRoles, ApprovalStatus

class User(AbstractUser):
    # Extension of standard user
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    must_change_password = models.BooleanField(
        default=False,
        help_text='If true, the user is forced to change their password before using the rest of the app.',
    )
    
    def __str__(self):
        return self.username

class Cabinet(BaseModel):
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    tax_id = models.CharField(max_length=50, blank=True, help_text=_("NIF/TIN"))
    logo = models.ImageField(upload_to='cabinets/logos/', blank=True, null=True)
    
    def __str__(self):
        return self.name

class UserCabinetRole(BaseModel):
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
