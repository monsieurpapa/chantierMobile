from django.db import models, transaction
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
    
    def is_budget_period_active(self, check_date=None):
        """Check if the budget period is active on given date."""
        from django.utils import timezone
        if check_date is None:
            check_date = timezone.localdate()
        return self.start_date <= check_date <= self.end_date
    
    def get_spent_amount(self):
        """Get total spent amount within budget period (approved/paid expenses).

        Filters by expense_date (date the expense was incurred), not created_at,
        so that expenses submitted in one period but incurred in another are
        correctly attributed.
        """
        return self.site.expenses.filter(
            status__in=[ExpenseStatus.APPROVED, ExpenseStatus.PAID],
            expense_date__gte=self.start_date,
            expense_date__lte=self.end_date,
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or 0
    
    def get_remaining_amount(self):
        """Get remaining budget amount."""
        from decimal import Decimal
        spent = self.get_spent_amount()
        return self.total_amount - Decimal(spent)

    def is_budget_exceeded(self, amount=0):
        """Check if budget would be exceeded with additional amount."""
        from decimal import Decimal
        remaining = self.get_remaining_amount()
        return Decimal(amount) > remaining

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
    expense_date = models.DateField(help_text=_("Date the expense was incurred (used for budget period matching)"))
    description = models.TextField()
    status = models.CharField(max_length=20, choices=ExpenseStatus.choices, default=ExpenseStatus.PENDING)
    receipt_image = models.ImageField(upload_to=FileUploadConfig.EXPENSE_RECEIPT_PATH, blank=True, null=True)
    
    def clean(self):
        """Validate expense data."""
        from django.core.exceptions import ValidationError
        from decimal import Decimal
        
        # Validate positive amount (None means the amount field itself already
        # failed form-level validation and is excluded from clean_fields())
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Amount must be a positive number.'})
        
        # Validate status transition
        original = None
        if self.pk:  # Only if updating existing expense
            original = Expense.objects.get(pk=self.pk)
            # PENDING → APPROVED | REJECTED
            # APPROVED → PAID | REJECTED
            # REJECTED and PAID are terminal states
            valid_transitions = {
                ExpenseStatus.PENDING: [ExpenseStatus.APPROVED, ExpenseStatus.REJECTED],
                ExpenseStatus.APPROVED: [ExpenseStatus.PAID, ExpenseStatus.REJECTED],
                ExpenseStatus.REJECTED: [],
                ExpenseStatus.PAID: [],
            }

            if original.status != self.status:  # Only check on actual transition
                allowed = valid_transitions.get(original.status, [])
                if self.status not in allowed:
                    raise ValidationError({
                        'status': f'Cannot transition from {original.status} to {self.status}.'
                    })

        # Validate against budget if expense is being approved
        if self.status == ExpenseStatus.APPROVED and hasattr(self.site, 'budget'):
            budget = self.site.budget
            if not budget.is_budget_period_active():
                raise ValidationError({
                    'status': 'Budget period is not active for this expense.'
                })

            # Check if this expense would exceed budget.
            # Only subtract original.amount when it was already APPROVED (i.e. already
            # counted in get_spent_amount()). PENDING expenses are not counted, so we
            # check the full self.amount when transitioning PENDING → APPROVED.
            amount_to_check = self.amount
            if original and original.status == ExpenseStatus.APPROVED:
                # Delta only: original.amount is already in get_spent_amount()
                amount_to_check = self.amount - original.amount
            
            if budget.is_budget_exceeded(amount_to_check):
                remaining = budget.get_remaining_amount()
                raise ValidationError({
                    'amount': f'Budget exceeded. Remaining budget: {remaining}. This expense is {self.amount}.'
                })
    
    def approve(self, user, comments=""):
        from django.core.exceptions import ValidationError
        if not user.is_superuser and self.requester_id == user.pk:
            raise ValidationError(_("You cannot approve your own expense request."))
        with transaction.atomic():
            # Lock the budget row to serialize concurrent approvals and prevent budget overruns.
            if hasattr(self.site, 'budget'):
                Budget.objects.select_for_update().get(site=self.site)
            self.status = ExpenseStatus.APPROVED
            self.full_clean()
            self.save()
            ExpenseApproval.objects.create(
                expense=self,
                approver=user,
                status=ExpenseApproval.Status.APPROVED,
                comments=comments
            )

    def reject(self, user, comments=""):
        with transaction.atomic():
            self.status = ExpenseStatus.REJECTED
            self.full_clean()
            self.save()
            ExpenseApproval.objects.create(
                expense=self,
                approver=user,
                status=ExpenseApproval.Status.REJECTED,
                comments=comments
            )
    
    def can_be_paid(self):
        """Check if expense can be marked as paid."""
        return self.status == ExpenseStatus.APPROVED

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
