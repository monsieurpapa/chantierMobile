"""
The `tasks` app owns `Task` — a single, deliberately simple model for
granular, assignable work items on a Site, complementing the coarser
%-complete tracking in projects.SiteProgress. See docs/modules/tasks.md
for the full walkthrough.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from projects.models import Site, ProjectPhase
from personnel.models import Personnel
from chantiermobile.constants import TaskStatus, TaskPriority


class Task(BaseModel):
    """A discrete, assignable, trackable unit of work on a Site — the
    granular counterpart to ProjectPhase/SiteProgress's coarse % complete
    reporting. Assignable to any Personnel record, including Tâcherons
    (day laborers) and Prestataires (subcontractors)."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='tasks')
    phase = models.ForeignKey(
        ProjectPhase, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tasks',
        help_text=_('Phase du chantier concernée (facultatif)'),
    )
    title = models.CharField(max_length=255, verbose_name=_('Titre'))
    description = models.TextField(blank=True, verbose_name=_('Description'))
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.A_FAIRE)
    priority = models.CharField(max_length=20, choices=TaskPriority.choices, default=TaskPriority.NORMALE)
    due_date = models.DateField(null=True, blank=True, verbose_name=_("Date d'échéance"))
    assigned_to = models.ForeignKey(
        Personnel, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tasks', verbose_name=_('Assigné à'),
        help_text=_('Employé, tâcheron ou prestataire responsable de cette tâche'),
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Tâche')
        verbose_name_plural = _('Tâches')
        ordering = ['status', 'due_date', 'id']

    def __str__(self):
        return self.title

    def clean(self):
        """Three guards: the assignee must belong to the same cabinet as
        the site (no cross-tenant assignment), a selected phase must
        belong to the same site, and status changes must follow the
        state machine below (BLOQUEE/TERMINEE/A_FAIRE/EN_COURS) —
        enforced here so no write path, not just the one view that
        exposes a transition today, can produce an invalid status jump."""
        from django.core.exceptions import ValidationError

        if self.assigned_to_id and self.site_id and self.assigned_to.cabinet_id != self.site.cabinet_id:
            raise ValidationError({
                'assigned_to': _("Le personnel assigné doit appartenir au même cabinet que le chantier.")
            })

        if self.phase_id and self.site_id and self.phase.site_id != self.site_id:
            raise ValidationError({
                'phase': _("La phase sélectionnée doit appartenir au même chantier.")
            })

        if self.pk:
            original = Task.objects.get(pk=self.pk)

            valid_transitions = {
                TaskStatus.A_FAIRE: [TaskStatus.EN_COURS, TaskStatus.BLOQUEE],
                TaskStatus.EN_COURS: [TaskStatus.TERMINEE, TaskStatus.BLOQUEE, TaskStatus.A_FAIRE],
                TaskStatus.BLOQUEE: [TaskStatus.A_FAIRE, TaskStatus.EN_COURS],
                TaskStatus.TERMINEE: [TaskStatus.A_FAIRE, TaskStatus.EN_COURS],
            }

            if original.status != self.status and original.status in valid_transitions:
                if self.status not in valid_transitions[original.status]:
                    raise ValidationError({
                        'status': _('Impossible de passer la tâche de %(old)s à %(new)s.') % {
                            'old': original.get_status_display(),
                            'new': self.get_status_display(),
                        }
                    })

    @property
    def is_overdue(self):
        """False for a completed task or one with no due_date — only a
        still-open task past its due date counts."""
        from django.utils import timezone
        if self.status == TaskStatus.TERMINEE or not self.due_date:
            return False
        return self.due_date < timezone.localdate()

    def _transition(self, new_status, changed_by=None, note=''):
        """Shared path for every status change below: stamps/clears
        `completed_at` as the task enters/leaves TERMINEE, runs
        full_clean() (so clean()'s transition-table check actually
        fires), and records a StatusChangeLog entry."""
        from core.models import StatusChangeLog
        from django.utils import timezone

        old_status = self.status
        self.status = new_status
        if new_status == TaskStatus.TERMINEE:
            self.completed_at = timezone.now()
        elif old_status == TaskStatus.TERMINEE:
            self.completed_at = None
        self.full_clean()
        self.save()
        StatusChangeLog.log(self, changed_by=changed_by, old_status=old_status, new_status=new_status, note=note)

    def start(self, changed_by=None):
        """A_FAIRE/BLOQUEE -> EN_COURS."""
        self._transition(TaskStatus.EN_COURS, changed_by=changed_by, note=_('Tâche démarrée.'))

    def complete(self, changed_by=None):
        """EN_COURS -> TERMINEE; stamps `completed_at`."""
        self._transition(TaskStatus.TERMINEE, changed_by=changed_by, note=_('Tâche terminée.'))

    def block(self, changed_by=None, reason=''):
        """A_FAIRE/EN_COURS -> BLOQUEE, with an optional free-text
        reason folded into the StatusChangeLog note."""
        note = _('Tâche bloquée : %(reason)s') % {'reason': reason} if reason else _('Tâche bloquée.')
        self._transition(TaskStatus.BLOQUEE, changed_by=changed_by, note=note)

    def reopen(self, changed_by=None):
        """BLOQUEE/TERMINEE -> A_FAIRE; clears `completed_at` if it was
        set."""
        self._transition(TaskStatus.A_FAIRE, changed_by=changed_by, note=_('Tâche réouverte.'))
