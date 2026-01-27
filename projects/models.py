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
    percentage_complete = models.PositiveIntegerField(help_text="0-100")
    description = models.TextField()
    
    def clean(self):
        if self.percentage_complete < ProjectConfig.MIN_PROGRESS or self.percentage_complete > ProjectConfig.MAX_PROGRESS:
            from django.core.exceptions import ValidationError
            raise ValidationError(f'Progress must be between {ProjectConfig.MIN_PROGRESS} and {ProjectConfig.MAX_PROGRESS}.')
    
    def __str__(self):
        return f"{self.phase.name} - {self.percentage_complete}% on {self.report_date}"
