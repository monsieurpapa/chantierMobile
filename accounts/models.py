from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel

class User(AbstractUser):
    # Extension of standard user
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    
    def __str__(self):
        return self.username

class Cabinet(BaseModel):
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    tax_id = models.CharField(max_length=50, blank=True, help_text="NIF/TIN")
    logo = models.ImageField(upload_to='cabinets/logos/', blank=True, null=True)
    
    def __str__(self):
        return self.name

class UserCabinetRole(BaseModel):
    class Role(models.TextChoices):
        DIRECTOR = 'DIRECTOR', _('Cabinet Director')
        CHIEF_ENGINEER = 'CHIEF_ENGINEER', _('Chief of Engineers')
        ENGINEER = 'ENGINEER', _('Engineer')
        ACCOUNTANT = 'ACCOUNTANT', _('Accountant')
        CASHIER = 'CASHIER', _('Cashier')
        WORKER = 'WORKER', _('Worker')

    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending Approval')
        APPROVED = 'APPROVED', _('Approved')
        REJECTED = 'REJECTED', _('Rejected')

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cabinet_roles')
    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='user_roles')
    role = models.CharField(max_length=50, choices=Role.choices)
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.PENDING
    )
    
    class Meta:
        unique_together = ('user', 'cabinet')

    def __str__(self):
        return f"{self.user.username} - {self.role} @ {self.cabinet.name}"
