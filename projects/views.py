from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import Site, ProjectPhase, SiteProgress, PlanningSubmission
from .forms import SiteForm, ProjectPhaseForm, SiteProgressForm, PlanningSubmissionForm
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet, can_act_for_cabinet
from chantiermobile.constants import UserRoles

LEAD_ENGINEER_ROLES = ['ENGINEER', 'CHIEF_ENGINEER']
PHASE_CLOSE_ROLES = ['DIRECTOR', 'CHIEF_ENGINEER', 'ENGINEER']
PLANNING_REVIEW_ROLES = ['DIRECTOR', 'CHIEF_ENGINEER', 'ENGINEER']
PLANNING_SUBMIT_ROLES = ['DIRECTOR', 'CHIEF_ENGINEER']


def _scope_lead_engineer_queryset(form, cabinet):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    if cabinet:
        user_ids = cabinet.user_roles.filter(role__in=LEAD_ENGINEER_ROLES).values_list('user_id', flat=True)
        form.fields['lead_engineer'].queryset = User.objects.filter(id__in=user_ids)
    else:
        form.fields['lead_engineer'].queryset = User.objects.none()
    return form

class SiteListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Site
    template_name = 'projects/site_list.html'
    context_object_name = 'sites'
    ordering = ['-created_at']
    header_title = _("Projets & Chantiers")
    header_subtitle = _("Gérez et suivez tous les chantiers actifs")

    def get_header_actions(self):
        # We can't easily use rbac_tags here, so we use UserCabinetRole logic
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user,
            role__in=[UserRoles.DIRECTOR, UserRoles.CHIEF_ENGINEER]
        ).exists():
            return [{
                'label': _("Créer un chantier"),
                'url': str(reverse_lazy('projects:site_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary'
            }]
        return []

class SiteCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = Site
    form_class = SiteForm
    template_name = 'projects/site_form.html'
    success_url = reverse_lazy('projects:site_list')
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
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
        return super().form_valid(form)

class SiteUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    model = Site
    form_class = SiteForm
    template_name = 'projects/site_form.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']

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
    model = Site
    template_name = 'projects/confirm_delete.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    success_url = reverse_lazy('projects:site_list')
    allowed_roles = ['DIRECTOR']

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
        for progress in SiteProgress.objects.filter(phase__site=site).select_related('phase'):
            timeline.append({
                'type': 'PROGRESS',
                'date': progress.report_date,
                'timestamp': progress.created_at,
                'title': _("Avancement : %(phase)s") % {'phase': progress.phase.name},
                'content': _("Complété : %(pct)s%% — %(desc)s") % {'pct': progress.percentage_complete, 'desc': progress.description},
                'icon': 'fas fa-chart-line',
                'color': 'primary'
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


# --- PHASES ---

class ProjectPhaseCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    model = ProjectPhase
    form_class = ProjectPhaseForm
    template_name = 'projects/phase_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']

    def dispatch(self, request, *args, **kwargs):
        self.site = get_object_or_404(Site, unique_id=self.kwargs.get('site_id'))
        return super().dispatch(request, *args, **kwargs)

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site'] = self.site
        return context

    def get_success_url(self):
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.site.unique_id})

class ProjectPhaseUpdateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, UpdateView):
    model = ProjectPhase
    form_class = ProjectPhaseForm
    template_name = 'projects/phase_form.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site'] = self.object.site
        return context

    def get_success_url(self):
        messages.success(self.request, _("Phase mise à jour avec succès !"))
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id})

class ProjectPhaseDeleteView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, DeleteView):
    model = ProjectPhase
    template_name = 'projects/confirm_delete.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']

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
    model = SiteProgress
    form_class = SiteProgressForm
    template_name = 'projects/progress_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER', 'ENGINEER']

    def dispatch(self, request, *args, **kwargs):
        self.phase = get_object_or_404(ProjectPhase, unique_id=self.kwargs.get('phase_id'))
        return super().dispatch(request, *args, **kwargs)

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
        messages.success(self.request, _("Rapport d'avancement enregistré avec succès !"))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['phase'] = self.phase
        return context

    def get_success_url(self):
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.phase.site.unique_id})


@login_required
def phase_close(request, unique_id):
    """L'ingénieur principal du chantier (ou un directeur/chef des
    ingénieurs) clôture une étape du projet une fois ses travaux
    terminés."""
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
        messages.success(self.request, _("Planification soumise pour examen."))
        return response

    def get_success_url(self):
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.site.unique_id})


@login_required
def planning_submission_approve(request, pk):
    submission = get_object_or_404(PlanningSubmission, pk=pk)
    if request.method != 'POST':
        return redirect('projects:site_detail', unique_id=submission.site.unique_id)
    if not can_act_for_cabinet(request, submission.site.cabinet, PLANNING_REVIEW_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('projects:site_detail', unique_id=submission.site.unique_id)
    notes = request.POST.get('notes', '')
    try:
        submission.approve(request.user, notes=notes)
        messages.success(request, _("Planification approuvée."))
    except ValidationError as e:
        messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('projects:site_detail', unique_id=submission.site.unique_id)


@login_required
def planning_submission_reject(request, pk):
    submission = get_object_or_404(PlanningSubmission, pk=pk)
    if request.method != 'POST':
        return redirect('projects:site_detail', unique_id=submission.site.unique_id)
    if not can_act_for_cabinet(request, submission.site.cabinet, PLANNING_REVIEW_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('projects:site_detail', unique_id=submission.site.unique_id)
    notes = request.POST.get('notes', '')
    try:
        submission.reject(request.user, notes=notes)
        messages.success(request, _("Planification rejetée."))
    except ValidationError as e:
        messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('projects:site_detail', unique_id=submission.site.unique_id)
