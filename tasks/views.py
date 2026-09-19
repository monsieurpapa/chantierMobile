from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from .models import Task
from .forms import TaskForm
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet
from projects.models import Site, ProjectPhase
from personnel.models import Personnel
from chantiermobile.constants import UserRoles, TaskStatus

MANAGE_ROLES = ['DIRECTOR', 'CHIEF_ENGINEER', 'ENGINEER']


def _can_manage_task(user, task):
    """DIRECTOR/CHIEF_ENGINEER/ENGINEER on the task's cabinet, or the
    Personnel the task is assigned to (self-service for tâcherons/
    prestataires who have a linked login)."""
    if user.is_superuser:
        return True
    from accounts.models import UserCabinetRole
    if UserCabinetRole.objects.filter(
        user=user, cabinet=task.site.cabinet, role__in=MANAGE_ROLES
    ).exists():
        return True
    if task.assigned_to_id and getattr(task.assigned_to, 'user_id', None) == user.id:
        return True
    return False


class TaskListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Task
    template_name = 'tasks/task_list.html'
    context_object_name = 'tasks'
    cabinet_lookup_field = 'site__cabinet'
    header_title = _("Tâches")
    header_subtitle = _("Suivez l'avancement des tâches par chantier")

    def get_header_actions(self):
        return [{
            'label': _("Nouvelle tâche"),
            'url': str(reverse_lazy('tasks:task_create')),
            'icon': 'plus',
            'class': 'btn-falcon-primary'
        }]

    def get_queryset(self):
        if self.request.GET.get('mine'):
            # Self-service: a worker (tâcheron/prestataire) with a linked
            # login sees their own assigned tasks even without a
            # UserCabinetRole on any cabinet — CabinetAccessMixin's
            # cabinet-role filtering would otherwise exclude them entirely.
            qs = Task.objects.select_related('site', 'phase', 'assigned_to').filter(
                assigned_to__user=self.request.user
            )
        else:
            qs = super().get_queryset().select_related('site', 'phase', 'assigned_to')
            if self.request.user.is_superuser:
                active_cabinet = get_session_cabinet(self.request)
                if active_cabinet:
                    qs = qs.filter(site__cabinet=active_cabinet)
            else:
                user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
                qs = qs.filter(site__cabinet__id__in=user_cabinet_ids)

        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        site_id = self.request.GET.get('site')
        if site_id:
            qs = qs.filter(site_id=site_id)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_status_filter'] = self.request.GET.get('status', '')
        context['mine_filter'] = self.request.GET.get('mine', '')
        return context


class TaskCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    allowed_roles = MANAGE_ROLES
    header_title = _("Créer une tâche")
    header_subtitle = _("Définissez une nouvelle tâche pour un chantier")
    back_url = reverse_lazy('tasks:task_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Tâches"), 'url': str(reverse_lazy('tasks:task_list'))},
            {'title': _("Nouvelle tâche"), 'url': None},
        ]

    def get_initial(self):
        initial = super().get_initial()
        site_id = self.kwargs.get('site_id')
        if site_id:
            initial['site'] = get_object_or_404(Site, unique_id=site_id)
        return initial

    def _scope_form_querysets(self, form):
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            site_qs = Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
            personnel_qs = Personnel.objects.filter(cabinet=active_cabinet) if active_cabinet else Personnel.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            site_qs = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
            personnel_qs = Personnel.objects.filter(cabinet__id__in=user_cabinet_ids)
        form.fields['site'].queryset = site_qs
        form.fields['assigned_to'].queryset = personnel_qs
        form.fields['phase'].queryset = ProjectPhase.objects.filter(site__in=site_qs)
        return form

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return self._scope_form_querysets(form)

    def form_valid(self, form):
        messages.success(self.request, _("Tâche '%(title)s' créée avec succès.") % {'title': form.instance.title})
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('tasks:task_detail', kwargs={'pk': self.object.pk})


class TaskUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    allowed_roles = MANAGE_ROLES
    cabinet_lookup_field = 'site__cabinet'

    def get_header_title(self):
        return _("Modifier la tâche : %(title)s") % {'title': self.object.title}

    def get_back_url(self):
        return str(reverse_lazy('tasks:task_detail', kwargs={'pk': self.object.pk}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Tâches"), 'url': str(reverse_lazy('tasks:task_list'))},
            {'title': self.object.title, 'url': str(reverse_lazy('tasks:task_detail', kwargs={'pk': self.object.pk}))},
            {'title': _("Modifier"), 'url': None},
        ]

    def _scope_form_querysets(self, form):
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            site_qs = Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
            personnel_qs = Personnel.objects.filter(cabinet=active_cabinet) if active_cabinet else Personnel.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            site_qs = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
            personnel_qs = Personnel.objects.filter(cabinet__id__in=user_cabinet_ids)
        form.fields['site'].queryset = site_qs
        form.fields['assigned_to'].queryset = personnel_qs
        form.fields['phase'].queryset = ProjectPhase.objects.filter(site__in=site_qs)
        return form

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return self._scope_form_querysets(form)

    def form_valid(self, form):
        messages.success(self.request, _("Tâche mise à jour avec succès."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('tasks:task_detail', kwargs={'pk': self.object.pk})


class TaskDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = Task
    template_name = 'tasks/task_detail.html'
    context_object_name = 'task'
    cabinet_lookup_field = 'site__cabinet'

    def get_queryset(self):
        return super().get_queryset().select_related('site', 'phase', 'assigned_to')

    def get_header_title(self):
        return self.object.title

    def get_header_subtitle(self):
        return _("Chantier : %(site)s | Statut : %(status)s") % {
            'site': self.object.site.name,
            'status': self.object.get_status_display(),
        }

    def get_back_url(self):
        return str(reverse_lazy('tasks:task_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Tâches"), 'url': str(reverse_lazy('tasks:task_list'))},
            {'title': self.object.title, 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_manage'] = _can_manage_task(self.request.user, self.object)
        return context

    def get_header_actions(self):
        actions = []
        if _can_manage_task(self.request.user, self.object):
            actions.append({
                'label': _("Modifier"),
                'url': str(reverse_lazy('tasks:task_update', kwargs={'pk': self.object.pk})),
                'icon': 'edit',
                'class': 'btn-falcon-secondary'
            })
        return actions


@login_required
def task_start(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == 'POST':
        if not _can_manage_task(request.user, task):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('tasks:task_detail', pk=pk)
        try:
            task.start(changed_by=request.user)
            messages.success(request, _("Tâche démarrée."))
        except ValidationError as e:
            messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('tasks:task_detail', pk=pk)


@login_required
def task_complete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == 'POST':
        if not _can_manage_task(request.user, task):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('tasks:task_detail', pk=pk)
        try:
            task.complete(changed_by=request.user)
            messages.success(request, _("Tâche marquée comme terminée."))
        except ValidationError as e:
            messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('tasks:task_detail', pk=pk)


@login_required
def task_block(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == 'POST':
        if not _can_manage_task(request.user, task):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('tasks:task_detail', pk=pk)
        reason = request.POST.get('reason', '')
        try:
            task.block(changed_by=request.user, reason=reason)
            messages.success(request, _("Tâche marquée comme bloquée."))
        except ValidationError as e:
            messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('tasks:task_detail', pk=pk)


@login_required
def task_reopen(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == 'POST':
        if not _can_manage_task(request.user, task):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('tasks:task_detail', pk=pk)
        try:
            task.reopen(changed_by=request.user)
            messages.success(request, _("Tâche réouverte."))
        except ValidationError as e:
            messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('tasks:task_detail', pk=pk)
