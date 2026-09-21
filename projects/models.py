from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from accounts.models import Cabinet
from chantiermobile.constants import SiteStatus, ProjectConfig, ExpenseStatus, PlanningStatus, PhaseStatus

class Site(BaseModel):
    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='sites')
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=SiteStatus.choices, default=SiteStatus.PLANNING)
    start_date = models.DateField(null=True, blank=True)
    expected_end_date = models.DateField(null=True, blank=True)
    lead_engineer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sites_led', verbose_name=_('Ingénieur principal'),
        help_text=_("Ingénieur responsable de ce chantier — clôture les étapes et examine la planification."),
    )

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
        # Cascade soft-delete to planning submissions
        self.planning_submissions.filter(is_deleted=False).update(is_deleted=True, deleted_at=now)
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

            # Editing a site without changing its status (the common case —
            # e.g. just assigning a lead engineer) is not a transition and
            # must not be blocked by this check.
            if original.status != self.status and original.status in valid_transitions:
                if self.status not in valid_transitions[original.status]:
                    raise ValidationError({
                        'status': f'Cannot transition site from {original.status} to {self.status}.'
                    })

    @property
    def active_assignments(self):
        from django.utils import timezone
        today = timezone.localdate()
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
        return self.expenses.filter(status__in=[ExpenseStatus.APPROVED, ExpenseStatus.PAID]).aggregate(
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
    status = models.CharField(max_length=20, choices=PhaseStatus.choices, default=PhaseStatus.EN_COURS)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='phases_closed', verbose_name=_('Clôturée par'),
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closure_notes = models.TextField(blank=True, verbose_name=_('Notes de clôture'))

    def __str__(self):
        return f"{self.site.name} - {self.name}"

    @property
    def is_closed(self):
        return self.status == PhaseStatus.CLOTUREE

    def close(self, user, notes=''):
        """L'ingénieur principal (ou un directeur) clôture cette étape du
        projet — geste final une fois les travaux de la phase terminés."""
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        from core.models import StatusChangeLog

        if self.is_closed:
            raise ValidationError(_('Cette étape est déjà clôturée.'))

        old_status = self.status
        self.status = PhaseStatus.CLOTUREE
        self.closed_by = user
        self.closed_at = timezone.now()
        self.closure_notes = notes
        self.save(update_fields=['status', 'closed_by', 'closed_at', 'closure_notes', 'updated_at'])
        StatusChangeLog.log(
            self, changed_by=user, old_status=old_status, new_status=self.status,
            note=notes or _('Étape clôturée.'),
        )


class PlanningSubmission(BaseModel):
    """A planning/schedule submitted for review by the site's concerned
    engineer(s) — "Soumettre la planification aux ingénieurs concernés"."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='planning_submissions')
    phase = models.ForeignKey(
        ProjectPhase, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='planning_submissions',
        help_text=_('Étape concernée (facultatif)'),
    )
    description = models.TextField(verbose_name=_('Description de la planification'))
    status = models.CharField(max_length=20, choices=PlanningStatus.choices, default=PlanningStatus.BROUILLON)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='planning_submissions_made',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='planning_submissions_reviewed',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, verbose_name=_('Notes de revue'))

    class Meta:
        verbose_name = _('Planification soumise')
        verbose_name_plural = _('Planifications soumises')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.site.name}: {self.get_status_display()}"

    def submit(self, user):
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        if self.status != PlanningStatus.BROUILLON:
            raise ValidationError(_('Seule une planification en brouillon peut être soumise.'))
        self.status = PlanningStatus.SOUMISE
        self.submitted_by = user
        self.submitted_at = timezone.now()
        self.save(update_fields=['status', 'submitted_by', 'submitted_at', 'updated_at'])

    def _decide(self, user, new_status, notes=''):
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        if self.status != PlanningStatus.SOUMISE:
            raise ValidationError(_('Seule une planification soumise peut être examinée.'))
        self.status = new_status
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_notes', 'updated_at'])

    def approve(self, user, notes=''):
        self._decide(user, PlanningStatus.APPROUVEE, notes)

    def reject(self, user, notes=''):
        self._decide(user, PlanningStatus.REJETEE, notes)


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
