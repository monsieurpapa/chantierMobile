from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from accounts.models import Cabinet

class Site(BaseModel):
    class Status(models.TextChoices):
        PLANNING = 'PLANNING', _('Planning')
        ACTIVE = 'ACTIVE', _('Active')
        PAUSED = 'PAUSED', _('Paused')
        COMPLETED = 'COMPLETED', _('Completed')
        CANCELLED = 'CANCELLED', _('Cancelled')

    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='sites')
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNING)
    start_date = models.DateField(null=True, blank=True)
    expected_end_date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.status})"

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
    
    def __str__(self):
        return f"{self.phase.name} - {self.percentage_complete}% on {self.report_date}"
