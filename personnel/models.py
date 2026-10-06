"""
The `personnel` app owns the HR side of a Cabinet: the people
(`Personnel`), their skills, where they're working (`SiteAssignment`),
their paperwork (`PersonnelDocument`), and their time (`Leave`,
`Holiday`, `Attendance`). `Personnel.payroll_type` is the fork point
with `finance`'s two parallel payroll tracks — see ADR 0005
(docs/architecture/decisions/0005-separate-payroll-tracks.md) for why
ouvriers and ingénieurs/staff are paid through entirely separate models
rather than one generic payroll entity. See docs/modules/personnel.md
for the full walkthrough.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from accounts.models import Cabinet, User
from projects.models import Site
from chantiermobile.constants import (
    PersonnelType, AgentCategory, PersonnelStatus, PersonnelPayrollType, Trade, LeaveType, ApprovalStatus,
    AttendanceStatus,
)

class Skill(BaseModel):
    """A tag naming an aptitude or trade (e.g. Maçon, Ferrailleur), shared
    across the whole system rather than scoped to one cabinet — see
    personnel/views.py's SkillQuickCreateView (`cabinet_scoped = False`)."""
    name = models.CharField(max_length=100, verbose_name=_('Skill Name')) # e.g. Maçon, Ferrailleur
    description = models.TextField(blank=True, verbose_name=_('Description'))

    def __str__(self):
        return self.name

class Personnel(BaseModel):
    """A person the Cabinet employs or engages — permanent employee,
    tâcheron (day laborer) or prestataire (subcontractor), see
    `personnel_type`. `payroll_type` (OUVRIER/INGENIEUR) decides which of
    finance's two payroll tracks their pay flows through (ADR 0005), and
    is independent of `personnel_type`/`category` — it must be set
    explicitly, there is no inference between the three. `user` is an
    optional link to a system login, used for self-service (e.g. a
    tâcheron viewing their own assigned Tasks, see tasks/views.py)."""
    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='personnel')
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='personnel_profile', help_text=_("Link to system user if they have login access"))
    first_name = models.CharField(max_length=100, verbose_name=_('First Name'))
    last_name = models.CharField(max_length=100, verbose_name=_('Last Name'))
    personnel_type = models.CharField(
        max_length=20, choices=PersonnelType.choices, default=PersonnelType.EMPLOYE,
        verbose_name=_('Type'),
        help_text=_("Employé permanent, tâcheron (journalier) ou prestataire (sous-traitant)"),
    )
    skills = models.ManyToManyField(Skill, blank=True)
    default_daily_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text=_("Default daily cost"), verbose_name=_('Default Daily Rate'))
    monthly_salary = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_("Salaire mensuel fixe (agents administratifs / ingénieurs). Laisser vide pour un ouvrier payé au journalier."),
        verbose_name=_('Salaire mensuel'),
    )
    category = models.CharField(
        max_length=20, choices=AgentCategory.choices, default=AgentCategory.TERRAIN,
        verbose_name=_('Catégorie'),
        help_text=_("Agent de terrain ou d'administration"),
    )
    trade = models.CharField(
        max_length=20, choices=Trade.choices, blank=True,
        verbose_name=_('Fonction / Métier'),
        help_text=_("Fonction de l'ouvrier (Maçon, Menuisier, Plombier, ...)"),
    )
    status = models.CharField(
        max_length=20, choices=PersonnelStatus.choices, default=PersonnelStatus.ACTIF,
        verbose_name=_('Statut'),
    )
    payroll_type = models.CharField(
        max_length=20, choices=PersonnelPayrollType.choices, default=PersonnelPayrollType.OUVRIER,
        verbose_name=_('Catégorie de paie'),
        help_text=_(
            "Ouvrier (main d'œuvre, payé selon convention par chantier) ou Ingénieur (salarié) — "
            "détermine la catégorie de décaissement sur la liste de paie."
        ),
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_subcontractor(self):
        """True for Tâcherons and Prestataires — non-payroll workers."""
        return self.personnel_type in (PersonnelType.TACHERON, PersonnelType.PRESTATAIRE)

    @property
    def is_eligible(self):
        """Only an ACTIF personnel record may be newly assigned to a site
        — see SiteAssignment.clean()."""
        return self.status == PersonnelStatus.ACTIF

class SiteAssignment(BaseModel):
    """Links a Personnel to a Site for a date range, at an agreed
    `daily_rate` — the record that drives `Site.total_daily_personnel_cost`
    and the attendance/pointage crew list (see Attendance,
    AttendanceDailyView.get_rows). `convention_amount` optionally caps
    total pay for one specific task/convention; a worker can hold several
    concurrent assignments to the same site, one per convention."""
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='assignments')
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='assignments')
    role = models.CharField(max_length=100, help_text=_("Specific role on this site, e.g. Chef d'équipe"), verbose_name=_('Role'))
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    daily_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text=_("Agreed rate for this specific assignment"), verbose_name=_('Daily Rate'))
    agreement_document = models.FileField(
        upload_to='personnel/agreements/', null=True, blank=True,
        verbose_name=_("Convention (document)"),
        help_text=_("Convention de main-d'œuvre signée pour cette affectation."),
    )
    agreement_notes = models.TextField(
        blank=True, verbose_name=_('Termes de la convention'),
        help_text=_("Conditions particulières de la convention de main-d'œuvre."),
    )
    convention_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name=_('Montant de la convention'),
        help_text=_(
            "Montant total convenu pour cette tâche (ex : communiqué par l'Archi à la caisse). "
            "Laisser vide si aucun plafond n'est suivi. Un même personnel peut avoir plusieurs "
            "conventions actives sur un même chantier — une par tâche."
        ),
    )

    def clean(self):
        """Blocks assigning a non-ACTIF (e.g. suspended/terminated)
        personnel record to a site. Note: this only checks eligibility
        at save time — it does not check for overlapping date ranges
        against the same personnel's other assignments, so double-
        booking the same person to two sites on the same dates is
        currently possible."""
        from django.core.exceptions import ValidationError
        # Validation logic for overlapping assignments could go here
        # For MVP, we'll enforce it in the form/view or simple clean method
        if self.personnel_id and not self.personnel.is_eligible:
            raise ValidationError({
                'personnel': _(
                    "%(name)s n'est pas éligible (statut : %(status)s) et ne peut pas être affecté(e) à un chantier."
                ) % {'name': self.personnel, 'status': self.personnel.get_status_display()},
            })

    def __str__(self):
        return f"{self.personnel} -> {self.site} ({self.role})"

    @property
    def paid_amount(self):
        """Sum of all liste-de-paie payments made against this specific
        assignment/convention so far."""
        agg = self.payroll_items.aggregate(t=models.Sum('amount'))
        return agg['t'] or 0

    @property
    def remaining_convention(self):
        """None means no cap is tracked for this assignment. Can go
        negative if items were entered before a cap was added — treated
        the same as any exceeded cap by callers."""
        if self.convention_amount is None:
            return None
        return self.convention_amount - self.paid_amount


class PersonnelDocument(BaseModel):
    """A file in an agent/worker's 'dossier' — ID copy, diploma, contract,
    medical certificate, etc."""
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='documents')
    label = models.CharField(max_length=150, verbose_name=_('Libellé'), help_text=_("Ex: Copie CNI, Diplôme, Contrat de travail"))
    file = models.FileField(upload_to='personnel/documents/', verbose_name=_('Fichier'))
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.label} — {self.personnel}"


class Holiday(BaseModel):
    """A company-wide public holiday (jour férié)."""
    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='holidays')
    name = models.CharField(max_length=150, verbose_name=_('Nom'))
    date = models.DateField(verbose_name=_('Date'))

    class Meta:
        ordering = ['date']
        unique_together = ('cabinet', 'date')

    def __str__(self):
        return f"{self.name} ({self.date})"


class Leave(BaseModel):
    """A personnel absence: congé (leave) or other declared time off.
    Public holidays that apply to everyone belong on the Holiday model
    instead; this is per-worker."""
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='leaves')
    leave_type = models.CharField(max_length=20, choices=LeaveType.choices, default=LeaveType.CONGE, verbose_name=_('Type'))
    start_date = models.DateField(verbose_name=_('Date de début'))
    end_date = models.DateField(verbose_name=_('Date de fin'))
    reason = models.TextField(blank=True, verbose_name=_('Motif'))
    status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING, verbose_name=_('Statut'))
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='leave_decisions')
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.personnel} — {self.get_leave_type_display()} ({self.start_date} → {self.end_date})"

    @property
    def duration_days(self):
        """Inclusive day count (start and end date both count), so a
        single-day leave reads as 1, not 0."""
        return (self.end_date - self.start_date).days + 1


class Attendance(BaseModel):
    """Daily pointage: one row per (personnel, site, date) recording
    whether that worker actually showed up (item 14 of the Directors/
    Engineers audit). Keyed on personnel+site+date rather than the
    SiteAssignment so a late/early assignment change on the same day
    doesn't orphan the day's record, and so the same personnel/site/date
    combination can never be recorded twice by accident."""
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='attendance_records')
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(verbose_name=_('Date'))
    status = models.CharField(
        max_length=20, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT,
        verbose_name=_('Statut'),
    )
    notes = models.CharField(max_length=255, blank=True, verbose_name=_('Notes'))
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='attendance_recorded',
    )

    class Meta:
        ordering = ['-date', 'personnel__last_name']
        unique_together = ('personnel', 'site', 'date')

    def __str__(self):
        return f"{self.personnel} — {self.site} — {self.date} ({self.get_status_display()})"
