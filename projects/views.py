"""
Views for the `projects` app: Site CRUD, its phase structure, the
engineer-facing planning-review workflow, and the progress-reporting
loop (reports, photos, comments). Every state-changing view here must
go through RoleRequiredMixin/get_role_cabinet() or can_act_for_cabinet()
(see core/mixins.py and docs/security.md) — @login_required alone never
proves the actor holds the right role in the right Cabinet.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils.translation import gettext_lazy as _
from .models import Site, ProjectPhase, SiteProgress, ProgressPhoto, ProgressComment, PlanningSubmission, SiteLevel
from .forms import SiteForm, ProjectPhaseForm, SiteProgressForm, PlanningSubmissionForm, SiteLevelFormSet
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet, can_act_for_cabinet, can_view_cabinet
from chantiermobile.constants import UserRoles, ApprovalStatus

# Same director-tier/CHIEF_ENGINEER gate as SiteUpdateView — editing the
# structure (floors, concrete/maçonnerie detail) is a technical/design
# decision at the same level as editing the site itself.
SITE_STRUCTURE_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']


def _site_structure_can_act(request, site):
    """A director-tier/CHIEF_ENGINEER holder can edit any of their
    cabinet's sites' structure; a plain ENGINEER may still edit their
    *own* led site — same ownership rule as personnel.views's
    _attendance_can_act, since the site's own engineer is usually the one
    actually taking the on-site measurements."""
    if can_act_for_cabinet(request, site.cabinet, SITE_STRUCTURE_ROLES):
        return True
    return site.lead_engineer_id == request.user.pk

LEAD_ENGINEER_ROLES = ['ENGINEER', 'CHIEF_ENGINEER']
PHASE_CLOSE_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER', 'ENGINEER']
PLANNING_REVIEW_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER', 'ENGINEER']
# ENGINEER used to be missing here — only Director/Chief could submit a
# planning at all. That matched the original one-directional design (a
# plan authored centrally and pushed down "à examiner par l'ingénieur
# principal du chantier"), but it meant the site's own engineer, who
# usually knows the real sequencing best, had no way to draft and submit
# their own schedule for a chief/director to approve. Adding ENGINEER
# here is purely additive — the top-down flow still works — and pairs
# with the self-review guard in PlanningSubmission._decide() so an
# engineer can't submit a plan and then approve their own submission.
PLANNING_SUBMIT_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER', 'ENGINEER']
# Who can file a progress report or add photos to one afterward — the
# field/engineering side. Commenting is deliberately looser (see
# progress_comment_add): anyone with cabinet access, not just these roles.
PROGRESS_PHOTO_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER', 'ENGINEER']


def _scope_lead_engineer_queryset(form, cabinet):
    """Restricts the Site form's `lead_engineer` choices to users who
    actually hold an ENGINEER/CHIEF_ENGINEER role in this site's cabinet
    — otherwise the select would list every user in the system."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    if cabinet:
        user_ids = cabinet.user_roles.filter(role__in=LEAD_ENGINEER_ROLES).values_list('user_id', flat=True)
        form.fields['lead_engineer'].queryset = User.objects.filter(id__in=user_ids)
    else:
        form.fields['lead_engineer'].queryset = User.objects.none()
    return form

class SiteListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    """Lists the current user's Cabinet-scoped sites. Open to any
    authenticated member of a cabinet; only the "Créer un chantier"
    header action is role-gated (director-tier or CHIEF_ENGINEER)."""
    model = Site
    template_name = 'projects/site_list.html'
    context_object_name = 'sites'
    ordering = ['-created_at']
    header_title = _("Projets & Chantiers")
    header_subtitle = _("Gérez et suivez tous les chantiers actifs")

    def get_header_actions(self):
        # We can't easily use rbac_tags here, so we use UserCabinetRole logic
        # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now —
        # see core/mixins.py and docs/security.md.
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user,
            role__in=[UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.CHIEF_ENGINEER],
            status=ApprovalStatus.APPROVED,
        ).exists():
            return [{
                'label': _("Créer un chantier"),
                'url': str(reverse_lazy('projects:site_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary'
            }]
        return []

class SiteCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    """Creates a new Site. Director-tier or CHIEF_ENGINEER only
    (allowed_roles), tagged to the creator's own cabinet."""
    model = Site
    form_class = SiteForm
    template_name = 'projects/site_form.html'
    success_url = reverse_lazy('projects:site_list')
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']
    header_title = _("Nouveau chantier")
    header_subtitle = _("Saisissez les informations du chantier pour commencer le suivi")
    back_url = reverse_lazy('projects:site_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Projets & Chantiers"), 'url': str(reverse_lazy('projects:site_list'))},
            {'title': _("Nouveau chantier"), 'url': None},
        ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return _scope_lead_engineer_queryset(form, self.get_user_cabinet())

    def form_valid(self, form):
        cabinet = self.get_user_cabinet()
        if not cabinet:
            messages.error(self.request, _("Vous devez appartenir à un cabinet pour créer un chantier."))
            return self.form_invalid(form)

        form.instance.cabinet = cabinet
        messages.success(self.request, _("Chantier créé avec succès !"))
        response = super().form_valid(form)
        self.object.sync_levels()
        return response

class SiteUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    """Edits a Site, including status transitions (validated by
    Site.clean()). Director-tier or CHIEF_ENGINEER only (allowed_roles),
    scoped to the object's own cabinet via CabinetAccessMixin."""
    model = Site
    form_class = SiteForm
    template_name = 'projects/site_form.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']

    def get_header_title(self):
        return _("Modifier : %(name)s") % {'name': self.object.name}

    def get_header_subtitle(self):
        return self.object.location

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Projets & Chantiers"), 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.object.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.unique_id}))},
            {'title': _("Modifier"), 'url': None},
        ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return _scope_lead_engineer_queryset(form, self.object.cabinet)

    def form_valid(self, form):
        from django.core.exceptions import ValidationError
        from django.db import transaction
        from core.models import StatusChangeLog
        old_status = self.object.status
        try:
            form.instance.full_clean()
            with transaction.atomic():
                form.save()
                self.object = form.instance
                self.object.sync_levels()
                if old_status != self.object.status:
                    StatusChangeLog.log(
                        self.object,
                        changed_by=self.request.user,
                        old_status=old_status,
                        new_status=self.object.status,
                    )
            messages.success(self.request, _("Chantier mis à jour avec succès !"))
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(self.get_success_url())
        except ValidationError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.unique_id})

class SiteDeleteView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DeleteView):
    """Soft-deletes a Site (see Site.delete()'s cascade). Director-tier
    only (allowed_roles) — notably narrower than SiteCreateView/
    SiteUpdateView, which also allow CHIEF_ENGINEER."""
    model = Site
    template_name = 'projects/confirm_delete.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    success_url = reverse_lazy('projects:site_list')
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL']

    def get_header_title(self):
        return _("Supprimer : %(name)s") % {'name': self.object.name}

    def get_header_subtitle(self):
        return _("Cette action est irréversible.")

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Projets & Chantiers"), 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.object.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.unique_id}))},
            {'title': _("Supprimer"), 'url': None},
        ]

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, _("Chantier supprimé avec succès !"))
        return super().delete(request, *args, **kwargs)

class SiteDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    """A Site's full picture: financials, phases, and a merged activity
    timeline (progress reports, expenses, material requests). Open to
    any authenticated member of the site's cabinet (CabinetAccessMixin);
    not role-gated beyond that."""
    model = Site
    template_name = 'projects/site_detail.html'
    context_object_name = 'site'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'

    # header_title/header_subtitle/header_actions are intentionally left at
    # their PageHeaderMixin defaults (blank / empty list): this page renders
    # its own rich hero card just below the page_header include — name,
    # location, status, and the same role-gated Modifier/Supprimer buttons —
    # so repeating any of that here would just duplicate it. Only the
    # breadcrumb + back link are wanted from page_header.html on this page.

    def get_back_url(self):
        return str(reverse_lazy('projects:site_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Projets & Chantiers"), 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.object.name, 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Use self.object (already fetched by DetailView.get) — avoids a duplicate DB query
        site = self.object
        context['enabled_modules'] = site.get_enabled_modules()

        # Financial context
        expenses_qs = site.expenses.select_related('category', 'requester').order_by('-created_at')
        context['expenses'] = expenses_qs
        context['contract'] = getattr(site, 'contract', None)
        if context['contract']:
            context['invoices'] = context['contract'].invoices.all().order_by('-issued_date')

        # Unified Timeline / History
        # We collect different types of events and tag them for the template
        timeline = []

        # 1. Progress Reports
        for progress in SiteProgress.objects.filter(phase__site=site).select_related('phase').annotate(
            photo_count=Count('photos', distinct=True), comment_count=Count('comments', distinct=True)
        ):
            content = _("Complété : %(pct)s%% — %(desc)s") % {'pct': progress.percentage_complete, 'desc': progress.description}
            if progress.photo_count or progress.comment_count:
                content += " " + _("(%(photos)s photo(s), %(comments)s commentaire(s))") % {
                    'photos': progress.photo_count, 'comments': progress.comment_count,
                }
            timeline.append({
                'type': 'PROGRESS',
                'date': progress.report_date,
                'timestamp': progress.created_at,
                'title': _("Avancement : %(phase)s") % {'phase': progress.phase.name},
                'content': content,
                'icon': 'fas fa-chart-line',
                'color': 'primary',
                'url': str(reverse_lazy('projects:progress_detail', kwargs={'unique_id': progress.unique_id})),
            })

        # 2. Expenses — reuse the already-evaluated queryset, no second DB round-trip
        for expense in expenses_qs:
            timeline.append({
                'type': 'EXPENSE',
                'date': expense.created_at.date(),
                'timestamp': expense.created_at,
                'title': _("Dépense : %(cat)s") % {'cat': expense.category.name},
                'content': _("Montant : %(amount)s$ — Statut : %(status)s") % {'amount': expense.amount, 'status': expense.get_status_display()},
                'icon': 'fas fa-money-bill-wave',
                'color': 'warning'
            })

        # Matériaux tab: each request's own line items (fixes a pre-existing
        # template bug — MaterialRequest has no `material`/`quantity` field
        # of its own, only via its `items` — see site_detail.html) plus the
        # "Achat matériaux" caisse purchase lines recorded against this site
        # (added 2026-10-06; financial record only, see
        # finance.CaisseTransactionMaterialLine's docstring — this does not
        # reflect/replace actual stock-on-hand, which stays tracked by the
        # magasinier through the procurement app).
        context['material_requests'] = site.material_requests.all().select_related('requested_by').prefetch_related('items__material').order_by('-created_at')
        from finance.models import CaisseTransactionMaterialLine
        context['material_purchase_lines'] = CaisseTransactionMaterialLine.objects.filter(
            transaction__site=site,
        ).select_related('transaction', 'material').order_by('-transaction__date', '-created_at')

        # 3. Material Requests
        for req in site.material_requests.all().select_related('requested_by').prefetch_related('items__material'):
            timeline.append({
                'type': 'MATERIAL',
                'date': req.created_at.date(),
                'timestamp': req.created_at,
                'title': _("Demande de matériaux n°%(id)s") % {'id': req.id},
                'content': _("%(count)s article(s) — Statut : %(status)s") % {'count': req.total_items, 'status': req.get_status_display()},
                'icon': 'fas fa-boxes',
                'color': 'info'
            })

        # Sort combined timeline by timestamp descending
        context['timeline'] = sorted(timeline, key=lambda x: x['timestamp'], reverse=True)

        return context


class SiteStructureUpdateView(LoginRequiredMixin, PageHeaderMixin, DetailView):
    """Fills in each of a Site's SiteLevel rows (height, murs, poutres,
    colonnes, dalle) — the rows themselves are never created or deleted
    here (see Site.sync_levels(), called whenever floor_count/
    basement_count change on the Site form); this page only edits their
    detail, one fieldset per existing level, in one formset POST.

    Deliberately not a RoleRequiredMixin view — see
    _site_structure_can_act — since the site's own lead_engineer (who did
    the actual on-site measuring) should be able to fill this in even
    without a director-tier/CHIEF_ENGINEER role."""
    model = Site
    template_name = 'projects/site_structure_form.html'
    context_object_name = 'site'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not _site_structure_can_act(request, self.object):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('projects:site_detail', unique_id=self.object.unique_id)
        # Sites that predate SiteLevel (or were created outside the Site
        # form, e.g. seed commands/admin) have no level rows yet, which left
        # this page with nothing to edit. sync_levels() is idempotent.
        self.object.sync_levels()
        return super().dispatch(request, *args, **kwargs)

    def get_header_title(self):
        return _("Structure du chantier : %(name)s") % {'name': self.object.name}

    def get_header_subtitle(self):
        return _("Un niveau par étage (R+%(n)s) — modifiez « Nombre d'étages (R+N) » et « Nombre de sous-sols » depuis la fiche du chantier pour en ajouter ou en retirer.") % {'n': self.object.floor_count}

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Projets & Chantiers"), 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.object.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.unique_id}))},
            {'title': _("Structure"), 'url': None},
        ]

    def _formset(self, data=None):
        return SiteLevelFormSet(data, queryset=self.object.levels.all(), prefix='levels')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('levels_formset', self._formset(self.request.POST if self.request.method == 'POST' else None))
        return context

    def post(self, request, *args, **kwargs):
        formset = self._formset(request.POST)
        if formset.is_valid():
            formset.save()
            messages.success(request, _("Structure du chantier mise à jour."))
            return redirect('projects:site_detail', unique_id=self.object.unique_id)
        messages.error(request, _("Veuillez corriger les erreurs ci-dessous."))
        return self.render_to_response(self.get_context_data(levels_formset=formset))


# --- PHASES ---

class ProjectPhaseCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    """Adds a phase to a site. Director-tier or CHIEF_ENGINEER only
    (allowed_roles), scoped to the site's own cabinet via
    get_role_cabinet() below."""
    model = ProjectPhase
    form_class = ProjectPhaseForm
    template_name = 'projects/phase_form.html'
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']

    @staticmethod
    def _site_queryset(request):
        """Cabinet-scoped Site lookup so a phase can't be created under a
        site the requester has no access to (site_id is a raw URL kwarg,
        not a form field Django can validate against a scoped queryset).
        Mirrors the superuser/regular-user branching used everywhere else
        (e.g. SiteAssignmentCreateView.get_form). Unauthenticated requests
        fall through unscoped so LoginRequiredMixin's redirect (triggered
        by super().dispatch() right after) still fires instead of a 404.
        """
        # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now —
        # see core/mixins.py and docs/security.md.
        user = request.user
        if not user.is_authenticated:
            return Site.objects.all()
        if user.is_superuser:
            active_cabinet = get_session_cabinet(request)
            return Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
        cabinets = user.approved_cabinet_roles.values_list('cabinet', flat=True)
        return Site.objects.filter(cabinet__in=cabinets)

    def dispatch(self, request, *args, **kwargs):
        self.site = get_object_or_404(self._site_queryset(request), unique_id=self.kwargs.get('site_id'))
        return super().dispatch(request, *args, **kwargs)

    def get_role_cabinet(self):
        # Scopes the DIRECTOR/CHIEF_ENGINEER check to the site's own
        # cabinet, not just "has this role somewhere" — a Director in
        # Cabinet A has no authority to add phases to Cabinet B's sites.
        return self.site.cabinet

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['site'] = self.site
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site'] = self.site
        # Top-level phases this new phase could become a sous-étape of —
        # same scoping ProjectPhaseForm applies, kept here too since
        # phase_form.html renders fields by hand rather than via the form.
        context['top_level_phases'] = self.site.phases.filter(parent_phase__isnull=True).order_by('name')
        return context

    def get_header_title(self):
        return _("Ajouter une phase : %(name)s") % {'name': self.site.name}

    def get_header_subtitle(self):
        return _("Définissez une nouvelle phase de construction pour ce projet")

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.site.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Projets & Chantiers"), 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.site.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.site.unique_id}))},
            {'title': _("Ajouter une phase"), 'url': None},
        ]

    def form_valid(self, form):
        form.instance.site = self.site
        messages.success(self.request, _("Phase '%(name)s' ajoutée au projet.") % {'name': form.instance.name})
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.site.unique_id})

class ProjectPhaseUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    """Edits a phase's name/dates. Director-tier or CHIEF_ENGINEER only
    (allowed_roles) — closing a phase is a separate action, see
    `phase_close` below, which also allows ENGINEER."""
    model = ProjectPhase
    form_class = ProjectPhaseForm
    template_name = 'projects/phase_form.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']
    cabinet_lookup_field = 'site__cabinet'

    def get_header_title(self):
        return _("Modifier la phase : %(name)s") % {'name': self.object.name}

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Projets & Chantiers"), 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.object.site.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id}))},
            {'title': _("Modifier la phase"), 'url': None},
        ]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['site'] = self.object.site
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site'] = self.object.site
        # Same top-level-phases scoping as ProjectPhaseCreateView, minus
        # this phase itself (a phase can't be its own parent) and minus
        # everything if this phase already has its own sous-étapes (see
        # ProjectPhaseForm.__init__ / ProjectPhase.clean()).
        qs = self.object.site.phases.filter(parent_phase__isnull=True).exclude(pk=self.object.pk)
        if self.object.sub_phases.exists():
            qs = qs.none()
        context['top_level_phases'] = qs.order_by('name')
        return context

    def get_success_url(self):
        messages.success(self.request, _("Phase mise à jour avec succès !"))
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id})

class ProjectPhaseDeleteView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DeleteView):
    """Soft-deletes a phase. Director-tier or CHIEF_ENGINEER only
    (allowed_roles)."""
    model = ProjectPhase
    template_name = 'projects/confirm_delete.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']
    cabinet_lookup_field = 'site__cabinet'

    def get_header_title(self):
        return _("Supprimer la phase : %(name)s") % {'name': self.object.name}

    def get_header_subtitle(self):
        return _("Cette action est irréversible.")

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Projets & Chantiers"), 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.object.site.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id}))},
            {'title': _("Supprimer la phase"), 'url': None},
        ]

    def get_success_url(self):
        messages.success(self.request, _("Phase supprimée avec succès !"))
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id})


# --- PROGRESS ---

class SiteProgressCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    """Files a progress report (%, description, optional photos) against
    a phase. Director-tier, CHIEF_ENGINEER or ENGINEER (allowed_roles),
    scoped to the phase's own cabinet via get_role_cabinet() and the
    cabinet-filtered `self.phase` lookup below.

    FIXED 2026-10-06: previously `self.phase` was looked up with a bare
    get_object_or_404(ProjectPhase, ...) (no cabinet filter) and
    get_role_cabinet() was not overridden, so RoleRequiredMixin's check
    was "does this user hold one of allowed_roles in *any* cabinet" —
    letting a user who holds e.g. ENGINEER in their own Cabinet A file a
    progress report, with attached photos, against a phase belonging to
    an unrelated Cabinet B, provided they knew/guessed that phase's
    unique_id (a UUID in the URL). Now mirrors the already-scoped
    ProjectPhaseCreateView/PlanningSubmissionCreateView siblings above:
    the phase lookup is cabinet-scoped (superuser sees their session-
    active cabinet or all; a regular user sees only their own
    cabinet(s)) and get_role_cabinet() ties the role check to that same
    phase's cabinet. See docs/security.md."""
    model = SiteProgress
    form_class = SiteProgressForm
    template_name = 'projects/progress_form.html'
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER', 'ENGINEER']

    @staticmethod
    def _phase_queryset(request):
        """Cabinet-scoped ProjectPhase lookup, mirroring
        ProjectPhaseCreateView._site_queryset above — phase_id is a raw
        URL kwarg, not a form field Django can validate against a
        scoped queryset. Unauthenticated requests fall through unscoped
        so LoginRequiredMixin's redirect (triggered by super().dispatch()
        right after) still fires instead of a 404."""
        # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now —
        # see core/mixins.py and docs/security.md.
        user = request.user
        if not user.is_authenticated:
            return ProjectPhase.objects.all()
        if user.is_superuser:
            active_cabinet = get_session_cabinet(request)
            return ProjectPhase.objects.filter(site__cabinet=active_cabinet) if active_cabinet else ProjectPhase.objects.all()
        cabinets = user.approved_cabinet_roles.values_list('cabinet', flat=True)
        return ProjectPhase.objects.filter(site__cabinet__in=cabinets)

    def dispatch(self, request, *args, **kwargs):
        self.phase = get_object_or_404(self._phase_queryset(request), unique_id=self.kwargs.get('phase_id'))
        return super().dispatch(request, *args, **kwargs)

    def get_role_cabinet(self):
        # Scopes the DIRECTOR/CHIEF_ENGINEER/ENGINEER check to the
        # phase's own cabinet, not just "has this role somewhere" — an
        # Engineer in Cabinet A has no authority to report progress on
        # Cabinet B's phases.
        return self.phase.site.cabinet

    def get_header_title(self):
        return _("Rapport d'avancement : %(name)s") % {'name': self.phase.name}

    def get_header_subtitle(self):
        return _("Projet : %(name)s") % {'name': self.phase.site.name}

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.phase.site.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Projets & Chantiers"), 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.phase.site.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.phase.site.unique_id}))},
            {'title': _("Rapport d'avancement"), 'url': None},
        ]

    def form_valid(self, form):
        form.instance.phase = self.phase
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        # Photos are a plain multi-file input (name="photos"), not part of
        # the ModelForm — Django has no built-in multi-file model field, so
        # each upload becomes its own ProgressPhoto row here rather than
        # forcing a formset for what's really a single "attach these" action.
        for f in self.request.FILES.getlist('photos'):
            ProgressPhoto.objects.create(progress=self.object, image=f, uploaded_by=self.request.user)
        messages.success(self.request, _("Rapport d'avancement enregistré avec succès !"))
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['phase'] = self.phase
        return context

    def get_success_url(self):
        return reverse_lazy('projects:progress_detail', kwargs={'unique_id': self.object.unique_id})


class ProgressDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    """A single progress report: its photos (gallery) and its comment
    thread — the "historique en détail" a report only got as a one-line
    timeline entry before. Reachable from the site's Activity Timeline."""
    model = SiteProgress
    template_name = 'projects/progress_detail.html'
    context_object_name = 'progress'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    cabinet_lookup_field = 'phase__site__cabinet'

    def get_header_title(self):
        return _("Rapport d'avancement : %(name)s") % {'name': self.object.phase.name}

    def get_header_subtitle(self):
        return _("Projet : %(name)s") % {'name': self.object.phase.site.name}

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.phase.site.unique_id}))

    def get_breadcrumb_items(self):
        site = self.object.phase.site
        return [
            {'title': _("Projets & Chantiers"), 'url': str(reverse_lazy('projects:site_list'))},
            {'title': site.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': site.unique_id}))},
            {'title': _("Rapport d'avancement"), 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        progress = self.object
        context['photos'] = progress.photos.select_related('uploaded_by')
        context['comments'] = progress.comments.select_related('author', 'photo')
        context['can_add_photo'] = can_act_for_cabinet(self.request, progress.phase.site.cabinet, PROGRESS_PHOTO_ROLES)
        context['can_comment'] = can_view_cabinet(self.request, progress.phase.site.cabinet)
        return context


@login_required
def progress_photo_add(request, unique_id):
    """Attach one or more follow-up photos to an existing progress report
    — kept as a small standalone action rather than folded into an "edit
    report" view, since the report's own fields (date/%/description) don't
    change, only its evidence grows over time."""
    progress = get_object_or_404(SiteProgress, unique_id=unique_id)
    if request.method != 'POST':
        return redirect('projects:progress_detail', unique_id=progress.unique_id)
    if not can_act_for_cabinet(request, progress.phase.site.cabinet, PROGRESS_PHOTO_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('projects:progress_detail', unique_id=progress.unique_id)
    files = request.FILES.getlist('photos')
    if not files:
        messages.error(request, _("Sélectionnez au moins une photo à ajouter."))
    else:
        for f in files:
            ProgressPhoto.objects.create(progress=progress, image=f, uploaded_by=request.user)
        messages.success(request, _("%(count)s photo(s) ajoutée(s).") % {'count': len(files)})
    return redirect('projects:progress_detail', unique_id=progress.unique_id)


@login_required
def progress_comment_add(request, unique_id):
    """Comment on a progress report, or — if a photo id is posted — on one
    specific photo within it. Open to anyone with access to the site
    (see core.mixins.can_view_cabinet), not just the roles that can file
    the report: this is meant as a shared discussion thread (e.g. the
    Director asking about something visible in a photo), not another
    engineer-only channel."""
    progress = get_object_or_404(SiteProgress, unique_id=unique_id)
    if request.method != 'POST':
        return redirect('projects:progress_detail', unique_id=progress.unique_id)
    if not can_view_cabinet(request, progress.phase.site.cabinet):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('projects:progress_detail', unique_id=progress.unique_id)
    body = request.POST.get('body', '').strip()
    if not body:
        messages.error(request, _("Le commentaire ne peut pas être vide."))
        return redirect('projects:progress_detail', unique_id=progress.unique_id)
    photo = None
    photo_id = request.POST.get('photo')
    if photo_id:
        photo = get_object_or_404(ProgressPhoto, unique_id=photo_id, progress=progress)
    ProgressComment.objects.create(progress=progress, photo=photo, author=request.user, body=body)
    messages.success(request, _("Commentaire ajouté."))
    return redirect('projects:progress_detail', unique_id=progress.unique_id)


@login_required
def phase_close(request, unique_id):
    """L'ingénieur principal du chantier (ou un directeur/chef des
    ingénieurs) clôture une étape du projet une fois ses travaux
    terminés.

    GOTCHA: PHASE_CLOSE_ROLES is only checked via can_act_for_cabinet
    against `phase.site.cabinet` — any ENGINEER holding that role
    anywhere in the same cabinet can close this phase, not only the
    site's own `lead_engineer`. There is no additional check here (or in
    ProjectPhase.close()) that the acting user actually leads *this*
    site. Contrast with personnel/views.py's _attendance_can_act and
    SiteAssignmentCreateView, which explicitly check
    `site.lead_engineer_id == user.pk` for the equivalent "own site
    only" restriction."""
    phase = get_object_or_404(ProjectPhase, unique_id=unique_id)
    if request.method != 'POST':
        return redirect('projects:site_detail', unique_id=phase.site.unique_id)
    if not can_act_for_cabinet(request, phase.site.cabinet, PHASE_CLOSE_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('projects:site_detail', unique_id=phase.site.unique_id)
    notes = request.POST.get('notes', '')
    try:
        phase.close(request.user, notes=notes)
        messages.success(request, _("Étape '%(name)s' clôturée.") % {'name': phase.name})
    except ValidationError as e:
        messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('projects:site_detail', unique_id=phase.site.unique_id)


# --- PLANNING SUBMISSIONS ---

class PlanningSubmissionCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    """Drafts and immediately submits (BROUILLON -> SOUMISE, see
    form_valid) a planning submission for a site. Director-tier,
    CHIEF_ENGINEER or ENGINEER (PLANNING_SUBMIT_ROLES), scoped to the
    site's own cabinet via get_role_cabinet() below — but any ENGINEER
    in that cabinet may submit for any of its sites, not only one they
    lead (see the GOTCHA note on `planning_submission_approve` below for
    why that symmetry matters)."""
    model = PlanningSubmission
    form_class = PlanningSubmissionForm
    template_name = 'projects/planning_submission_form.html'
    allowed_roles = PLANNING_SUBMIT_ROLES

    def dispatch(self, request, *args, **kwargs):
        self.site = get_object_or_404(Site, unique_id=self.kwargs.get('site_id'))
        return super().dispatch(request, *args, **kwargs)

    def get_role_cabinet(self):
        return self.site.cabinet

    def get_header_title(self):
        return _("Soumettre une planification : %(name)s") % {'name': self.site.name}

    def get_header_subtitle(self):
        return _("À examiner par l'ingénieur principal du chantier")

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.site.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Projets & Chantiers"), 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.site.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.site.unique_id}))},
            {'title': _("Nouvelle planification"), 'url': None},
        ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['phase'].queryset = self.site.phases.all()
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site'] = self.site
        return context

    def form_valid(self, form):
        form.instance.site = self.site
        response = super().form_valid(form)
        self.object.submit(self.request.user)
        from core.notifications import notify_role_holders
        notify_role_holders(
            self.site.cabinet, PLANNING_REVIEW_ROLES,
            _("Nouvelle planification à examiner : %(site)s") % {'site': self.site.name},
            str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.site.unique_id})),
            exclude_user=self.request.user,
        )
        messages.success(self.request, _("Planification soumise pour examen."))
        return response

    def get_success_url(self):
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.site.unique_id})


@login_required
def planning_submission_approve(request, pk):
    """Approves a SOUMISE planning submission. Director-tier,
    CHIEF_ENGINEER or ENGINEER (PLANNING_REVIEW_ROLES) within the site's
    cabinet, plus PlanningSubmission._decide()'s self-review guard
    (can't approve your own submission).

    GOTCHA: that's the only "own site" guard — can_act_for_cabinet checks
    role + cabinet only, so any other ENGINEER in the same cabinet (not
    just the site's lead_engineer) can approve a colleague's submission
    for a site neither of them leads. docs/security.md currently
    describes this row as "ENGINEER (own site only)"; the code doesn't
    actually enforce the "own site" part beyond self-review."""
    submission = get_object_or_404(PlanningSubmission, pk=pk)
    if request.method != 'POST':
        return redirect('projects:site_detail', unique_id=submission.site.unique_id)
    if not can_act_for_cabinet(request, submission.site.cabinet, PLANNING_REVIEW_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('projects:site_detail', unique_id=submission.site.unique_id)
    notes = request.POST.get('notes', '')
    try:
        submission.approve(request.user, notes=notes)
        from core.notifications import notify_user
        notify_user(
            submission.submitted_by,
            _("Votre planification a été approuvée : %(site)s") % {'site': submission.site.name},
            str(reverse_lazy('projects:site_detail', kwargs={'unique_id': submission.site.unique_id})),
        )
        messages.success(request, _("Planification approuvée."))
    except ValidationError as e:
        messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('projects:site_detail', unique_id=submission.site.unique_id)


@login_required
def planning_submission_reject(request, pk):
    """Rejects a SOUMISE planning submission. Same role/cabinet/self-
    review gating as `planning_submission_approve` above (see its
    GOTCHA note)."""
    submission = get_object_or_404(PlanningSubmission, pk=pk)
    if request.method != 'POST':
        return redirect('projects:site_detail', unique_id=submission.site.unique_id)
    if not can_act_for_cabinet(request, submission.site.cabinet, PLANNING_REVIEW_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('projects:site_detail', unique_id=submission.site.unique_id)
    notes = request.POST.get('notes', '')
    try:
        submission.reject(request.user, notes=notes)
        from core.notifications import notify_user
        notify_user(
            submission.submitted_by,
            _("Votre planification a été rejetée : %(site)s") % {'site': submission.site.name},
            str(reverse_lazy('projects:site_detail', kwargs={'unique_id': submission.site.unique_id})),
        )
        messages.success(request, _("Planification rejetée."))
    except ValidationError as e:
        messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('projects:site_detail', unique_id=submission.site.unique_id)
