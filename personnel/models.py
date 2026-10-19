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
from django.db import models, transaction
from django.core.validators import MaxValueValidator
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from accounts.models import Cabinet, User
from projects.models import Site, ProjectPhase
from chantiermobile.constants import (
    PersonnelType, AgentCategory, PersonnelStatus, PersonnelPayrollType, Trade, LeaveType, ApprovalStatus,
    AttendanceStatus, ConventionScope, EvaluationMention,
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
    default_daily_rate = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_(
            "Tarif journalier par défaut — optionnel depuis 2026-10-06 : laisser vide pour un "
            "personnel payé uniquement par convention (par étape de chantier) plutôt qu'au "
            "journalier."
        ),
        verbose_name=_('Tarif journalier'),
    )
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
    experience_notes = models.TextField(
        blank=True, verbose_name=_('Compétences et expérience'),
        help_text=_(
            "Texte libre — added 2026-10-19 (meeting-note backlog, section Ingénieurs: "
            "\"le DG doit pouvoir voir le profil complet de chaque ingénieur : compétences et "
            "expérience\"). The client's own notes left open whether this should be structured "
            "fields or free text already captured elsewhere (CV import, ...) — a single free-form "
            "field is the reasonable default until that's confirmed; `skills` (the existing "
            "many-to-many tag list) covers the structured side of \"compétences\" already."
        ),
    )
    is_chef_de_corps = models.BooleanField(
        default=False, verbose_name=_('Chef de corps'),
        help_text=_(
            "Sous-traitant qui contracte avec le Cabinet pour tout un corps de métier "
            "(plomberie, maçonnerie, électricité, carrelage, ferraillage, charpente, soudure, ...) "
            "à une étape donnée, selon une convention négociée avec lui — il rémunère ensuite "
            "lui-même ses propres ouvriers, sans l'intervention du Cabinet, sauf en cas de "
            "dispute avec eux. Apparaît dans la section « Chefs de corps », distincte de la "
            "liste Personnel classique, mais partage le même enregistrement et les mêmes "
            "conventions par chantier (SiteAssignment)."
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
    concurrent assignments to the same site, one per convention.

    `name` and `phase` were added 2026-10-06 for the Personnel form's
    dynamic "Chantiers & conventions" section: there, a convention is
    named by the user and tied to a chantier `étape` (ProjectPhase) rather
    than filled in as a full standalone affectation, so `role`/`start_date`/
    `daily_rate` are no longer required at the model level — a convention
    created that way only ever sets `site`, `name`, `phase`, and
    `convention_amount`. The full assignment form (SiteAssignmentForm,
    used from the site's own crew-management flow) still collects
    role/dates/daily_rate as before; this is a widening of the model to
    support a second, lighter-weight creation path, not a behavior change
    for the existing one."""
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='assignments')
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='assignments')
    name = models.CharField(
        max_length=150, blank=True, verbose_name=_('Nom de la convention'),
        help_text=_(
            "Nom donné à cette convention par celui qui l'enregistre (ex : « Finition dalle "
            "bloc B »). Optionnel pour une affectation classique (role/dates/tarif journalier) ; "
            "utilisé par la section « Chantiers & conventions » du formulaire Personnel."
        ),
    )
    phase = models.ForeignKey(
        'projects.ProjectPhase', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='conventions', verbose_name=_('Étape du chantier'),
        help_text=_("L'étape (ProjectPhase) du chantier à laquelle cette convention se rapporte."),
    )
    scope = models.CharField(
        max_length=20, choices=ConventionScope.choices, blank=True,
        verbose_name=_('Portée de la convention'),
        help_text=_(
            "Par étape (cette convention porte sur une étape précise — voir `phase`) ou pour le "
            "chantier entier. Laisser vide pour une affectation classique (sans nom de "
            "convention) — ce champ ne s'applique qu'aux conventions."
        ),
    )
    role = models.CharField(
        max_length=100, blank=True,
        help_text=_("Specific role on this site, e.g. Chef d'équipe"), verbose_name=_('Role'),
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    daily_rate = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_("Agreed rate for this specific assignment"), verbose_name=_('Daily Rate'),
    )
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
            "conventions actives sur un même chantier — une par tâche. C'est aussi le plafond "
            "*actuel* d'une convention de Chef de corps : ConventionAvenant.record() le met à "
            "jour à chaque renégociation (voir initial_convention_amount pour le tout premier "
            "montant convenu)."
        ),
    )
    initial_convention_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name=_('Convention initiale'),
        help_text=_(
            "Montant de la toute première convention, avant le premier avenant — rempli "
            "automatiquement par ConventionAvenant.record() la première fois qu'un avenant est "
            "enregistré sur cette convention. Reste vide tant qu'aucun avenant n'a eu lieu : "
            "utiliser effective_initial_amount pour lire « la convention initiale, qu'il y ait "
            "eu un avenant ou non »."
        ),
    )

    def clean(self):
        """Blocks assigning a non-ACTIF (e.g. suspended/terminated)
        personnel record to a site. Note: this only checks eligibility
        at save time — it does not check for overlapping date ranges
        against the same personnel's other assignments, so double-
        booking the same person to two sites on the same dates is
        currently possible.

        Also blocks a CHANTIER_ENTIER convention from carrying a phase
        (added 2026-10-19) — it covers the whole site, not one étape, so
        the two are never both meaningful at once. The reverse (PAR_ETAPE
        requiring a phase) is deliberately NOT checked here: it's
        ConventionForm.clean()'s job instead, because
        ConventionFormSetMixin.form_valid() resolves a brand-new
        `new_phase_name` into a real ProjectPhase (get-or-create) only
        *after* the formset already validated — at that validation point
        a PAR_ETAPE row naming a new étape legitimately has no `phase`
        yet, so enforcing the requirement here would reject it before
        the view ever gets a chance to fill it in."""
        from django.core.exceptions import ValidationError
        # Validation logic for overlapping assignments could go here
        # For MVP, we'll enforce it in the form/view or simple clean method
        if self.personnel_id and not self.personnel.is_eligible:
            raise ValidationError({
                'personnel': _(
                    "%(name)s n'est pas éligible (statut : %(status)s) et ne peut pas être affecté(e) à un chantier."
                ) % {'name': self.personnel, 'status': self.personnel.get_status_display()},
            })
        if self.scope == ConventionScope.CHANTIER_ENTIER and self.phase_id:
            raise ValidationError({
                'scope': _("Une convention « chantier entier » ne doit pas être rattachée à une étape précise."),
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

    @property
    def effective_initial_amount(self):
        """The convention's original amount regardless of whether an
        avenant has since changed it: `initial_convention_amount` once
        an avenant has been recorded, otherwise simply today's
        `convention_amount` (no renegotiation has happened yet, so the
        current amount *is* the initial one)."""
        return self.initial_convention_amount if self.initial_convention_amount is not None else self.convention_amount


class ConventionAvenant(BaseModel):
    """A dated change to a SiteAssignment's `convention_amount` after the
    original convention was agreed — "le chef technique annonce avenant
    sur convention à la caissière, elle ajoute ces détails sur la rubrique
    de changement de conventions avec les dates et détails spécifiés"
    (client spec, 2026-10-07). Typically used for a Chef de Corps whose
    scope grew (surplus de travail), but not restricted to one — any
    SiteAssignment with a tracked convention_amount can have avenants.

    `ConventionAvenant.record()` is the only supported way to create one:
    besides writing the history row, it also updates the assignment's
    live `convention_amount` (the cap PayrollListItem.clean() and the
    payroll disbursement screen check against) and backfills
    `initial_convention_amount` the first time an assignment is
    renegotiated, so "what was the very first amount" is never lost once
    it starts changing."""
    assignment = models.ForeignKey(
        SiteAssignment, on_delete=models.CASCADE, related_name='avenants',
        verbose_name=_('Convention'),
    )
    date = models.DateField(verbose_name=_("Date de l'avenant"))
    previous_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('Ancien montant'))
    new_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('Nouveau montant'))
    reason = models.TextField(
        verbose_name=_('Motif'),
        help_text=_(
            "Ex : surplus de travail annoncé par le chef technique, révision de prix des "
            "matériaux, retard du chantier..."
        ),
    )
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='convention_avenants_recorded', verbose_name=_('Enregistré par'),
        help_text=_("La caissière (ou le caissier) qui a saisi cet avenant dans le système."),
    )

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = _('Avenant de convention')
        verbose_name_plural = _('Avenants de convention')

    def __str__(self):
        return f"{self.assignment} : {self.previous_amount} → {self.new_amount} ({self.date})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.new_amount is not None and self.new_amount < 0:
            raise ValidationError({'new_amount': _('Le montant ne peut pas être négatif.')})

    @classmethod
    @transaction.atomic
    def record(cls, assignment, new_amount, reason, user, date=None):
        """Create the avenant row and apply `new_amount` to
        `assignment.convention_amount` in one step. Snapshots the
        assignment's current `convention_amount` into both this row's
        `previous_amount` and — the first time this runs for a given
        assignment — `assignment.initial_convention_amount`, so the
        original figure survives any number of later avenants."""
        from django.utils import timezone as _tz
        previous = assignment.convention_amount or 0
        if assignment.initial_convention_amount is None:
            assignment.initial_convention_amount = previous
        avenant = cls.objects.create(
            assignment=assignment, date=date or _tz.localdate(),
            previous_amount=previous, new_amount=new_amount,
            reason=reason, recorded_by=user,
        )
        assignment.convention_amount = new_amount
        assignment.save(update_fields=['convention_amount', 'initial_convention_amount', 'updated_at'])
        return avenant


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


class PersonnelEvaluation(BaseModel):
    """One cotation/observation of a worker's performance on a given
    étape (gros œuvre) — added 2026-10-19 (meeting-note backlog,
    "Évaluation du personnel par étape"). Deliberately **append-only**
    from the UI (no update/delete view): the client's explicit ask was
    an "historique des observations... pas un score unique écrasé à
    chaque mise à jour" — every cotation made is its own row, kept
    forever, rather than one mutable rating per (personnel, phase) pair.
    `phase` is whichever étape or sous-étape ProjectPhase the observation
    concerns (reusing the structure already in place, same as
    SiteAssignment/DQELine) — not necessarily the worker's *current*
    assignment, since an évaluation can reasonably be entered for an
    étape the worker has since moved on from.

    Scale (open question in the client's own notes — "note chiffrée,
    mention qualitative, les deux ?"): both are supported, each
    optional, so the evaluator can fill whichever fits; `clean()` only
    requires that at least one rating dimension be given alongside the
    observation text. Revisit once the client settles on one.

    Who may cote (open question — "qui d'autre que l'Ingénieur en Chef
    peut coter ?"): gated to HR_ADMIN_ROLES in the view (director-tier +
    CHIEF_ENGINEER), the same tier already trusted to edit a Personnel
    profile — not CHIEF_ENGINEER-only, pending client confirmation."""
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='evaluations')
    phase = models.ForeignKey(
        ProjectPhase, on_delete=models.CASCADE, related_name='personnel_evaluations',
        verbose_name=_('Étape'),
        help_text=_("L'étape (ou sous-étape) de chantier concernée par cette cotation."),
    )
    note_chiffree = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_('Note (/20)'),
        validators=[MaxValueValidator(20)],
        help_text=_("Note chiffrée sur 20, facultative — laisser vide si seule la mention qualitative est utilisée."),
    )
    mention_qualitative = models.CharField(
        max_length=20, choices=EvaluationMention.choices, blank=True,
        verbose_name=_('Mention qualitative'),
    )
    observation = models.TextField(
        verbose_name=_('Observation'),
        help_text=_("Le commentaire de l'Ingénieur en Chef (ou autre évaluateur habilité) sur la prestation du travailleur à cette étape."),
    )
    evaluated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='personnel_evaluations_made',
        verbose_name=_('Évalué par'),
    )

    class Meta:
        verbose_name = _('Cotation du personnel')
        verbose_name_plural = _('Cotations du personnel')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.personnel} — {self.phase.name} ({self.created_at:%Y-%m-%d})"

    def clean(self):
        """At least one rating dimension (numeric or qualitative) must
        be given — an observation with neither isn't a cotation, just a
        free-form note (which belongs elsewhere, e.g. a progress
        comment). `note_chiffree`'s 0-20 range is already enforced by
        its PositiveSmallIntegerField + MaxValueValidator below."""
        from django.core.exceptions import ValidationError
        if self.note_chiffree is None and not self.mention_qualitative:
            raise ValidationError(_(
                "Donnez au moins une note chiffrée ou une mention qualitative."
            ))
        if self.phase_id and self.personnel_id and self.phase.site_id:
            # Not a hard requirement that the worker is (still) assigned
            # to this site — an évaluation can outlive the assignment —
            # but a phase from a site the worker has never set foot on
            # at all is almost certainly a form mistake.
            has_history = self.personnel.assignments.filter(site_id=self.phase.site_id).exists()
            if not has_history:
                raise ValidationError({
                    'phase': _("Cette personne n'a aucune affectation connue sur le chantier de cette étape."),
                })
