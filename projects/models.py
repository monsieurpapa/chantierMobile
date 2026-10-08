"""
The `projects` app owns the construction site itself — `Site`, the single
object every other app (finance, personnel, materials, revenue, tasks)
hangs its records off, plus the site's own internal structure
(`ProjectPhase`) and the engineer-facing reporting loop around it
(`PlanningSubmission` for schedule review, `SiteProgress`/`ProgressPhoto`/
`ProgressComment` for day-to-day advancement reporting). See
docs/modules/projects.md for the full walkthrough and
docs/architecture/overview.md for how Site fits into the wider Cabinet
multi-tenancy model.
"""
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from accounts.models import Cabinet
from chantiermobile.constants import (
    SiteStatus, ProjectConfig, ExpenseStatus, PlanningStatus, PhaseStatus, ContractMode, CONTRACT_MODE_MODULES,
    StructureType,
)

class Site(BaseModel):
    """A chantier (construction site) — the tenancy anchor for almost
    every other business record (expenses, personnel assignments, tasks,
    contracts, budgets all hang off a Site, directly or indirectly).
    Belongs to exactly one Cabinet and optionally has a `lead_engineer`,
    who gets the extra authority to close phases and review this site's
    planning submissions (see ProjectPhase.close / PlanningSubmission)."""
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
    contract_mode = models.CharField(
        max_length=30, choices=ContractMode.choices, default=ContractMode.CLE_EN_MAIN,
        verbose_name=_('Type de contrat'),
        help_text=_(
            "Type de contrat signé avec le client — pré-établi dès la création du chantier, "
            "modifiable plus tard par un directeur si l'accord avec le client change. Détermine "
            "quelles fonctionnalités (feuilles) sont pertinentes pour ce chantier : voir "
            "get_enabled_modules()."
        ),
    )
    floor_count = models.PositiveSmallIntegerField(
        default=0, verbose_name=_("Nombre d'étages (R+N)"),
        help_text=_(
            "0 = rez-de-chaussée seul ; 1 = R+1 ; 2 = R+2, etc. Détermine combien de niveaux "
            "apparaissent dans l'onglet Structure (voir sync_levels()) — un niveau par étage, en "
            "plus du RDC et des sous-sols éventuels."
        ),
    )
    basement_count = models.PositiveSmallIntegerField(
        default=0, verbose_name=_('Nombre de sous-sols'),
        help_text=_("Niveaux en sous-sol (parking, cave...) — 0 si aucun."),
    )
    footprint_area_m2 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        verbose_name=_('Emprise au sol (m²)'),
        help_text=_(
            "Surface au sol occupée par le bâtiment. Sert de valeur par défaut pour la surface "
            "plancher (floor_area_m2) de chaque niveau dont ce champ est laissé vide — un étage "
            "dont l'emprise diffère réellement (retrait, porte-à-faux, extension) peut la "
            "renseigner lui-même pour remplacer ce défaut."
        ),
    )
    structure_type = models.CharField(
        max_length=20, choices=StructureType.choices, default=StructureType.POTEAUX_POUTRES,
        verbose_name=_('Type de structure'),
        help_text=_(
            "Indicatif pour la saisie des niveaux — ne bloque aucun champ. Poteaux-poutres : "
            "chaque niveau a sa propre trame de poutres/colonnes. Maçonnerie portante : les murs "
            "porteurs reprennent les charges, les champs poutres/colonnes restent disponibles "
            "mais sont généralement laissés à 0."
        ),
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
        # Cascade soft-delete to structure levels
        self.levels.filter(is_deleted=False).update(is_deleted=True, deleted_at=now)
        # Cascade soft-delete to phases (and their progress reports, photos, comments)
        for phase in self.phases.filter(is_deleted=False):
            for progress in phase.progress_reports.filter(is_deleted=False):
                progress.photos.filter(is_deleted=False).update(is_deleted=True, deleted_at=now)
                progress.comments.filter(is_deleted=False).update(is_deleted=True, deleted_at=now)
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
        """SiteAssignments covering today's date — open-ended (`end_date`
        null) or not yet expired."""
        from django.utils import timezone
        today = timezone.localdate()
        return self.assignments.filter(
            start_date__lte=today
        ).filter(
            models.Q(end_date__gte=today) | models.Q(end_date__isnull=True)
        )

    @property
    def total_daily_personnel_cost(self):
        """Sum of `daily_rate` across today's active assignments — the
        site's current day-labor burn rate, not a cumulative total."""
        return self.active_assignments.aggregate(
            total=models.Sum('daily_rate')
        )['total'] or 0

    @property
    def total_spent(self):
        """Cumulative APPROVED+PAID expenses only — PENDING/REJECTED
        expenses never count toward spend, so this can't be inflated by
        a request that hasn't actually been authorized."""
        return self.expenses.filter(status__in=[ExpenseStatus.APPROVED, ExpenseStatus.PAID]).aggregate(
            total=models.Sum('amount')
        )['total'] or 0

    @property
    def budget_usage_percentage(self):
        """0 when there's no Budget row yet (not an error — a site can
        exist before its budget is set). Capped at 100 even if actual
        spend exceeds the budget, since this drives a progress-bar style
        display; use total_spent vs. budget.total_amount directly if the
        overrun amount itself is needed."""
        if hasattr(self, 'budget') and self.budget.total_amount > 0:
            return min(int((self.total_spent / self.budget.total_amount) * 100), 100)
        return 0

    @property
    def total_revenue(self):
        """Cumulative amount of this site's PAID invoices, via its
        (optional, OneToOne) Contract. 0 when the site has no contract
        yet, not an error."""
        # Site -> Contract (OneToOne) -> Invoices
        if hasattr(self, 'contract'):
            return self.contract.invoices.filter(status='PAID').aggregate(
                total=models.Sum('amount')
            )['total'] or 0
        return 0

    @property
    def net_profit(self):
        """Revenue collected minus spend approved so far — a running
        figure, not a final project margin (both sides only reflect
        money that has actually moved, not pending invoices/expenses)."""
        return self.total_revenue - self.total_spent

    def get_enabled_modules(self):
        """Which of this site's optional tabs/modules make sense given its
        `contract_mode` — see CONTRACT_MODE_MODULES's docstring for what
        each module key covers and why a supervision-only or labor-only
        contract doesn't need all of them shown. Falls back to the fullest
        set for an unrecognized/legacy value rather than hiding everything,
        since failing open is safer than silently hiding a tab a site
        actually needs."""
        return CONTRACT_MODE_MODULES.get(self.contract_mode, {'personnel', 'materials', 'finance'})

    def has_module(self, module):
        """Convenience check for a single module key (see
        get_enabled_modules()) — used where a view needs a plain
        True/False rather than the whole set."""
        return module in self.get_enabled_modules()

    def sync_levels(self):
        """Creates/restores/removes SiteLevel rows so they exactly match
        `floor_count`/`basement_count` — called from SiteCreateView/
        SiteUpdateView.form_valid() after every save, so the "Structure du
        chantier" page always shows exactly the right number of level
        fieldsets without anyone having to manage them by hand.

        Indexing: 0 = RDC, 1..floor_count = R+1..R+N, -1..-basement_count =
        Sous-sol 1..N (see SiteLevel.label). A level whose index falls
        outside the new range is soft-deleted (its data isn't lost — see
        `restore` below — but it stops counting toward the site's
        structural totals); raising the count back later restores the
        same row (with whatever it had last) rather than creating a fresh
        blank one, since a dormant row for that exact index is reused via
        SiteLevel.all_objects instead of SiteLevel.objects.create()."""
        wanted = set(range(-self.basement_count, self.floor_count + 1))
        active = {lvl.level_index: lvl for lvl in self.levels.all()}
        for idx in wanted - active.keys():
            dormant = SiteLevel.all_objects.filter(site=self, level_index=idx, is_deleted=True).first()
            if dormant is not None:
                dormant.restore()
            else:
                SiteLevel.objects.create(site=self, level_index=idx)
        for idx, level in active.items():
            if idx not in wanted:
                level.delete()

    @property
    def total_concrete_volume_m3(self):
        """Sum of every (non-deleted) level's `concrete_volume_m3` —
        poutres + colonnes + dalles across the whole chantier, the
        starting point for a BETON-category DQE line quantity (see
        pricing.services.structural_quantity_estimate)."""
        return sum((level.concrete_volume_m3 for level in self.levels.all()), Decimal('0'))

    @property
    def total_wall_area_m2(self):
        """Sum of every level's net `wall_area_m2` (wall length × height,
        minus openings) — the starting point for a MACONNERIE-category
        DQE line quantity."""
        return sum((level.wall_area_m2 or Decimal('0') for level in self.levels.all()), Decimal('0'))

    @property
    def estimated_rebar_kg(self):
        """Steel (acier/armatures) estimated from `total_concrete_volume_m3`
        via the cabinet's configurable `rebar_density_kg_per_m3` — a
        deliberately rough order-of-magnitude figure (reinforcement isn't
        actually proportional to gross concrete volume in reality — a
        slab and a column reinforce very differently — but a single
        density factor is the standard quick avant-métré shortcut, and a
        quantity surveyor is expected to refine it per DQE line as
        needed, not take it as final)."""
        density = (self.cabinet.rebar_density_kg_per_m3 if self.cabinet_id else None) or Decimal('100')
        return self.total_concrete_volume_m3 * density

class ProjectPhase(BaseModel):
    """A named stage of work within a Site (e.g. "Fondations",
    "Gros œuvre") — the unit SiteProgress reports and PlanningSubmissions
    are filed against, and the unit a lead engineer formally closes with
    `close()` once its work is done.

    `parent_phase` (added 2026-10-07, Devis/État de besoin comparison
    feature) lets one top-level étape carry one or more sous-étapes (e.g.
    "Gros Œuvre" > "Semelles filantes bloc A") — deliberately **one level
    deep only** (see `clean()`), matching the client's literal ask rather
    than a generic arbitrary-depth tree. A phase with no parent is a
    top-level étape; a phase with a parent is a sous-étape of it."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='phases')
    parent_phase = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sub_phases', verbose_name=_('Étape parente'),
        help_text=_(
            "Laisser vide pour une étape principale. Sélectionner une étape "
            "existante en fait une sous-étape de celle-ci (un seul niveau de "
            "profondeur — une sous-étape ne peut pas elle-même avoir de "
            "sous-étapes)."
        ),
    )
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
        if self.parent_phase_id:
            return f"{self.site.name} - {self.parent_phase.name} > {self.name}"
        return f"{self.site.name} - {self.name}"

    def clean(self):
        """Keeps the hierarchy exactly one level deep and sane:
        - a phase can't be its own parent;
        - a parent must belong to the same site;
        - a parent can't itself already be a sous-étape (no 2nd level);
        - a phase that already has its own sous-étapes can't itself become
          a sous-étape of another phase (that would create a 2nd level from
          the other direction — caught here, not above, since the check
          above only looks at the *parent's* parent, not at this phase's
          own children)."""
        from django.core.exceptions import ValidationError
        if self.parent_phase_id:
            if self.pk and self.parent_phase_id == self.pk:
                raise ValidationError({'parent_phase': _("Une étape ne peut pas être sa propre étape parente.")})
            if self.site_id and self.parent_phase.site_id != self.site_id:
                raise ValidationError({'parent_phase': _("L'étape parente doit appartenir au même chantier.")})
            if self.parent_phase.parent_phase_id:
                raise ValidationError({'parent_phase': _(
                    "Une sous-étape ne peut pas elle-même avoir de sous-étape (un seul niveau de profondeur)."
                )})
            if self.pk and self.sub_phases.exists():
                raise ValidationError({'parent_phase': _(
                    "Cette étape a déjà ses propres sous-étapes ; elle ne peut pas devenir "
                    "elle-même une sous-étape (un seul niveau de profondeur)."
                )})

    @property
    def is_sub_phase(self):
        """True when this phase is a sous-étape of another."""
        return self.parent_phase_id is not None

    @property
    def top_level_phase(self):
        """This phase itself if it's already top-level, else its parent —
        the étape to roll sous-étape figures up into for a site-wide
        devis/consommation comparison."""
        return self.parent_phase if self.parent_phase_id else self

    @property
    def is_closed(self):
        """True once the phase has been formally closed via close()."""
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


class SiteLevel(BaseModel):
    """One physical floor/level of a Site's building — RDC, R+1, R+2...,
    or a sous-sol (negative index) — carrying the structural detail an
    avant-métré needs to estimate concrete/steel/maçonnerie quantities
    for that level specifically (added 2026-10-08, floors/structure
    feature). Rows are managed entirely through `Site.sync_levels()`
    (called after every Site save): there is no "add a level" form —
    changing `Site.floor_count`/`basement_count` and saving is the only
    way to create or remove one, so the set of levels always matches
    what the site's own R+N says, no more and no fewer.

    All structural fields are optional (an engineer fills them in as
    survey/design data becomes available) and deliberately *aggregated*
    per level rather than member-by-member (one total beam length and a
    typical section, not each beam individually) — precise enough for an
    early avant-métré, far faster to fill than a full structural member
    schedule, which belongs in dedicated structural-design software, not
    here."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='levels')
    level_index = models.SmallIntegerField(
        verbose_name=_('Indice de niveau'),
        help_text=_("0 = RDC, 1..N = R+1..R+N, négatif = sous-sol. Géré par Site.sync_levels()."),
    )
    height_m = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name=_('Hauteur sous plafond (m)'),
    )
    floor_area_m2 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        verbose_name=_('Surface plancher (m²)'),
        help_text=_("Laisser vide pour reprendre l'emprise au sol du chantier (voir Site.footprint_area_m2)."),
    )
    wall_length_m = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        verbose_name=_('Longueur cumulée des murs (m)'),
        help_text=_("Périmètre extérieur + refends (murs de séparation intérieurs) de ce niveau."),
    )
    opening_area_m2 = models.DecimalField(
        max_digits=6, decimal_places=2, default=0, null=True, blank=True,
        verbose_name=_('Surface des ouvertures (m²)'),
        help_text=_(
            "Portes et fenêtres de ce niveau — déduite de la surface des murs pour une "
            "estimation plus juste des parpaings/enduit (voir wall_area_m2)."
        ),
    )
    beam_count = models.PositiveIntegerField(default=0, verbose_name=_('Nombre de poutres'))
    beam_section_width_m = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True, default=Decimal('0.20'),
        verbose_name=_('Section des poutres — largeur (m)'),
    )
    beam_section_height_m = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True, default=Decimal('0.40'),
        verbose_name=_('Section des poutres — hauteur (m)'),
    )
    beam_total_length_m = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        verbose_name=_('Longueur totale des poutres (m)'),
        help_text=_("Somme des portées de toutes les poutres de ce niveau (pas la longueur d'une seule)."),
    )
    column_count = models.PositiveIntegerField(default=0, verbose_name=_('Nombre de colonnes'))
    column_section_width_m = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True, default=Decimal('0.20'),
        verbose_name=_('Section des colonnes — largeur (m)'),
    )
    column_section_depth_m = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True, default=Decimal('0.20'),
        verbose_name=_('Section des colonnes — profondeur (m)'),
    )
    slab_thickness_m = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True, default=Decimal('0.15'),
        verbose_name=_('Épaisseur de la dalle (m)'),
        help_text=_("Dalle haute de ce niveau (plancher de l'étage suivant, ou toiture-terrasse pour le dernier niveau)."),
    )
    notes = models.TextField(blank=True, verbose_name=_('Notes'))

    class Meta:
        verbose_name = _('Niveau de chantier')
        verbose_name_plural = _('Niveaux de chantier')
        unique_together = ('site', 'level_index')
        ordering = ['level_index']

    def __str__(self):
        return f"{self.site.name} — {self.label}"

    @property
    def label(self):
        """Human-readable French level name: "RDC", "R+2", "Sous-sol 1"."""
        if self.level_index == 0:
            return _('Rez-de-chaussée (RDC)')
        if self.level_index > 0:
            return f'R+{self.level_index}'
        return _('Sous-sol %(n)s') % {'n': abs(self.level_index)}

    @property
    def effective_floor_area_m2(self):
        """This level's own `floor_area_m2`, falling back to the site's
        `footprint_area_m2` when left blank (most levels share the
        building's footprint; only a level with a real retrait/porte-à-
        faux/extension needs its own value)."""
        if self.floor_area_m2 is not None:
            return self.floor_area_m2
        return self.site.footprint_area_m2

    @property
    def wall_area_m2(self):
        """Net wall surface (for a MACONNERIE ratio, priced per m²):
        wall_length × height, minus openings. None (not 0) when the
        inputs needed to compute it aren't filled in yet, since "not
        entered" and "zero wall" are different facts worth distinguishing
        in a summary display."""
        if self.wall_length_m is None or self.height_m is None:
            return None
        gross = self.wall_length_m * self.height_m
        net = gross - (self.opening_area_m2 or Decimal('0'))
        return net if net > 0 else Decimal('0')

    @property
    def beam_volume_m3(self):
        """Concrete volume of this level's beams: total span length ×
        section (width × height). 0 (not None) when any input is missing
        — makes concrete_volume_m3 a safe, always-summable total."""
        if not self.beam_total_length_m or not self.beam_section_width_m or not self.beam_section_height_m:
            return Decimal('0')
        return self.beam_total_length_m * self.beam_section_width_m * self.beam_section_height_m

    @property
    def column_volume_m3(self):
        """Concrete volume of this level's columns: count × height ×
        section (width × depth) — a column is assumed to run the level's
        full height sous plafond."""
        if not self.column_count or not self.column_section_width_m or not self.column_section_depth_m or not self.height_m:
            return Decimal('0')
        return Decimal(self.column_count) * self.height_m * self.column_section_width_m * self.column_section_depth_m

    @property
    def slab_volume_m3(self):
        """Concrete volume of this level's dalle haute: floor area ×
        thickness."""
        area = self.effective_floor_area_m2
        if not area or not self.slab_thickness_m:
            return Decimal('0')
        return area * self.slab_thickness_m

    @property
    def concrete_volume_m3(self):
        """Total structural concrete for this level (poutres + colonnes +
        dalle) — the quantity a BETON-category DQE line for this level
        would carry."""
        return self.beam_volume_m3 + self.column_volume_m3 + self.slab_volume_m3


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
        """Moves a BROUILLON submission to SOUMISE, ready for review.
        Only a draft can be submitted — a submission already under
        review or decided cannot be resubmitted through this method."""
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        if self.status != PlanningStatus.BROUILLON:
            raise ValidationError(_('Seule une planification en brouillon peut être soumise.'))
        self.status = PlanningStatus.SOUMISE
        self.submitted_by = user
        self.submitted_at = timezone.now()
        self.save(update_fields=['status', 'submitted_by', 'submitted_at', 'updated_at'])

    def _decide(self, user, new_status, notes=''):
        """Shared approve/reject path: only a SOUMISE submission can be
        decided, and the self-review guard below blocks the submitter
        from deciding their own submission. Note this only checks
        "not the submitter" — it does not check that `user` is the
        site's lead_engineer or otherwise specifically responsible for
        this site, so any reviewer-role holder the call site authorizes
        can decide any other engineer's submission (see
        projects/views.py's PLANNING_REVIEW_ROLES / can_act_for_cabinet
        for where that authorization actually happens)."""
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        if self.status != PlanningStatus.SOUMISE:
            raise ValidationError(_('Seule une planification soumise peut être examinée.'))
        # ENGINEER is in both PLANNING_SUBMIT_ROLES and PLANNING_REVIEW_ROLES
        # (see projects/views.py) so a site engineer can draft their own
        # planning — but not rubber-stamp it themselves. Mirrors
        # Expense.approve()'s self-approval guard.
        if not user.is_superuser and self.submitted_by_id == user.pk:
            raise ValidationError(_("Vous ne pouvez pas examiner votre propre soumission."))
        self.status = new_status
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_notes', 'updated_at'])

    def approve(self, user, notes=''):
        """Marks this submission APPROUVEE. See `_decide` for the
        self-review guard this relies on."""
        self._decide(user, PlanningStatus.APPROUVEE, notes)

    def reject(self, user, notes=''):
        """Marks this submission REJETEE. See `_decide` for the
        self-review guard this relies on."""
        self._decide(user, PlanningStatus.REJETEE, notes)


class SiteProgress(BaseModel):
    """A dated advancement report against one ProjectPhase — "we're at X%
    as of this date" plus free-text notes. The day-to-day counterpart to
    PlanningSubmission's one-off schedule review; photos and comments
    attach to this record (see ProgressPhoto, ProgressComment)."""
    phase = models.ForeignKey(ProjectPhase, on_delete=models.CASCADE, related_name='progress_reports')
    report_date = models.DateField()
    percentage_complete = models.PositiveIntegerField(help_text=_("0-100"))
    description = models.TextField()

    def clean(self):
        """Keeps percentage_complete within ProjectConfig's configured
        0-100 bounds."""
        if self.percentage_complete < ProjectConfig.MIN_PROGRESS or self.percentage_complete > ProjectConfig.MAX_PROGRESS:
            from django.core.exceptions import ValidationError
            raise ValidationError(f'Progress must be between {ProjectConfig.MIN_PROGRESS} and {ProjectConfig.MAX_PROGRESS}.')

    def __str__(self):
        return f"{self.phase.name} - {self.percentage_complete}% on {self.report_date}"


class ProgressPhoto(BaseModel):
    """A photo attached to a site progress report — the visual evidence
    behind the percentage/description an engineer files (rebar laid, a
    wall poured, a defect found). Multiple photos per report, addable at
    any time (not only when the report is first filed), since follow-up
    photos often come in over the following days."""
    progress = models.ForeignKey(SiteProgress, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='projects/progress_photos/', verbose_name=_('Photo'))
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='progress_photos_uploaded', verbose_name=_('Ajoutée par'),
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Photo — {self.progress}"


class ProgressComment(BaseModel):
    """A comment on a progress report, or — when `photo` is set — on one
    specific photo within it (e.g. the Director asking about a crack
    visible in photo 3). Open to anyone with access to the site, not just
    the roles that can file progress reports, so it works as a shared
    discussion thread rather than an engineer-only channel."""
    progress = models.ForeignKey(SiteProgress, on_delete=models.CASCADE, related_name='comments')
    photo = models.ForeignKey(
        ProgressPhoto, on_delete=models.CASCADE, related_name='comments',
        null=True, blank=True, verbose_name=_('Photo commentée'),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='progress_comments', verbose_name=_('Auteur'),
    )
    body = models.TextField(verbose_name=_('Commentaire'))

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.author} on {self.progress}"

    def clean(self):
        """A photo-scoped comment must reference a photo that actually
        belongs to this same progress report — prevents cross-linking a
        comment to an unrelated report's photo (e.g. via a tampered
        `photo` id in the POST body)."""
        if self.photo_id and self.progress_id and self.photo.progress_id != self.progress_id:
            from django.core.exceptions import ValidationError
            raise ValidationError(_("La photo commentée doit appartenir au même rapport d'avancement."))
