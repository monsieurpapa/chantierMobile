from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from core.models import BaseModel
from projects.models import Site
from chantiermobile.constants import ExpenseStatus, FileUploadConfig

class Budget(BaseModel):
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name='budget')
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    
    def __str__(self):
        return f"Budget for {self.site.name}: {self.total_amount}"

class ExpenseCategory(BaseModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    class Meta:
        verbose_name_plural = "Expense Categories"

    def __str__(self):
        return self.name

class Expense(BaseModel):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='expenses')
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='requested_expenses')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='expenses')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=ExpenseStatus.choices, default=ExpenseStatus.PENDING)
    receipt_image = models.ImageField(upload_to=FileUploadConfig.EXPENSE_RECEIPT_PATH, blank=True, null=True)
    
    def approve(self, user, comments=""):
        self.status = ExpenseStatus.APPROVED
        self.save()
        ExpenseApproval.objects.create(
            expense=self,
            approver=user,
            status=ExpenseApproval.Status.APPROVED,
            comments=comments
        )

    def reject(self, user, comments=""):
        self.status = ExpenseStatus.REJECTED
        self.save()
        ExpenseApproval.objects.create(
            expense=self,
            approver=user,
            status=ExpenseApproval.Status.REJECTED,
            comments=comments
        )

    def __str__(self):
        return f"{self.amount} - {self.category} ({self.status})"

class ExpenseApproval(BaseModel):
    class Status(models.TextChoices):
        APPROVED = 'APPROVED', _('Approved')
        REJECTED = 'REJECTED', _('Rejected')

    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='approvals')
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    approval_date = models.DateTimeField(auto_now_add=True)
    comments = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.status} by {self.approver} on {self.approval_date}"
