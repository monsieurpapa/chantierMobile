from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from accounts.models import Cabinet
from chantiermobile.constants import SiteStatus, ProjectConfig

class Site(BaseModel):
    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='sites')
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=SiteStatus.choices, default=SiteStatus.PLANNING)
    start_date = models.DateField(null=True, blank=True)
    expected_end_date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.status})"

    def delete(self, using=None, keep_parents=False):
        """Soft-delete this site and cascade to all owned child records."""
        from django.utils import timezone
        now = timezone.now()
        # Cascade soft-delete to expenses
        self.expenses.filter(is_deleted=False).update(is_deleted=True, deleted_at=now)
        # Cascade soft-delete to material requests
        self.material_requests.filter(is_deleted=False).update(is_deleted=True, deleted_at=now)
        # Cascade soft-delete to phases (and their progress reports)
        for phase in self.phases.filter(is_deleted=False):
            phase.progress_reports.filter(is_deleted=False).update(is_deleted=True, deleted_at=now)
        self.phases.filter(is_deleted=False).update(is_deleted=True, deleted_at=now)
        # Cascade soft-delete to personnel assignments
        self.assignments.filter(is_deleted=False).update(is_deleted=True, deleted_at=now)
        # Cascade soft-delete to budget
        if hasattr(self, 'budget'):
            self.budget.is_deleted = True
            self.budget.deleted_at = now
            self.budget.save(update_fields=['is_deleted', 'deleted_at'])
        # Cascade soft-delete to contract and its invoices/payments
        if hasattr(self, 'contract'):
            contract = self.contract
            for invoice in contract.invoices.filter(is_deleted=False):
                invoice.payments.filter(is_deleted=False).update(is_deleted=True, deleted_at=now)
            contract.invoices.filter(is_deleted=False).update(is_deleted=True, deleted_at=now)
            contract.is_deleted = True
            contract.deleted_at = now
            contract.save(update_fields=['is_deleted', 'deleted_at'])
        super().delete(using=using, keep_parents=keep_parents)

    def clean(self):
        """Validate site status transitions."""
        from django.core.exceptions import ValidationError
        
        if self.pk:  # Only validate transitions for existing sites
            original = Site.objects.get(pk=self.pk)
            
            # Define valid transitions
            valid_transitions = {
                SiteStatus.PLANNING: [SiteStatus.ACTIVE, SiteStatus.CANCELLED],
                SiteStatus.ACTIVE: [SiteStatus.PAUSED, SiteStatus.COMPLETED, SiteStatus.CANCELLED],
                SiteStatus.PAUSED: [SiteStatus.ACTIVE, SiteStatus.COMPLETED, SiteStatus.CANCELLED],
                SiteStatus.COMPLETED: [],  # Final state
                SiteStatus.CANCELLED: [],  # Final state
            }
            
            if original.status in valid_transitions:
                if self.status not in valid_transitions[original.status]:
                    raise ValidationError({
                        'status': f'Cannot transition site from {original.status} to {self.status}.'
                    })

    @property
    def active_assignments(self):
        from django.utils import timezone
        today = timezone.now().date()
        return self.assignments.filter(
            start_date__lte=today
        ).filter(
            models.Q(end_date__gte=today) | models.Q(end_date__isnull=True)
        )

    @property
    def total_daily_personnel_cost(self):
        return self.active_assignments.aggregate(
            total=models.Sum('daily_rate')
        )['total'] or 0

    @property
    def total_spent(self):
        return self.expenses.filter(status__in=['APPROVED', 'PAID']).aggregate(
            total=models.Sum('amount')
        )['total'] or 0

    @property
    def budget_usage_percentage(self):
        if hasattr(self, 'budget') and self.budget.total_amount > 0:
            return min(int((self.total_spent / self.budget.total_amount) * 100), 100)
        return 0

    @property
    def total_revenue(self):
        # Site -> Contract (OneToOne) -> Invoices
        if hasattr(self, 'contract'):
            return self.contract.invoices.filter(status='PAID').aggregate(
                total=models.Sum('amount')
            )['total'] or 0
        return 0

    @property
    def net_profit(self):
        return self.total_revenue - self.total_spent

class ProjectPhase(BaseModel):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='phases')
    name = models.CharField(max_length=255)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.site.name} - {self.name}"

class SiteProgress(BaseModel):
    phase = models.ForeignKey(ProjectPhase, on_delete=models.CASCADE, related_name='progress_reports')
    report_date = models.DateField()
    percentage_complete = models.PositiveIntegerField(help_text=_("0-100"))
    description = models.TextField()
    
    def clean(self):
        if self.percentage_complete < ProjectConfig.MIN_PROGRESS or self.percentage_complete > ProjectConfig.MAX_PROGRESS:
            from django.core.exceptions import ValidationError
            raise ValidationError(f'Progress must be between {ProjectConfig.MIN_PROGRESS} and {ProjectConfig.MAX_PROGRESS}.')
    
    def __str__(self):
        return f"{self.phase.name} - {self.percentage_complete}% on {self.report_date}"
