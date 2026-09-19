from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from .models import Personnel, Skill, SiteAssignment
from .forms import PersonnelForm, SiteAssignmentForm, SkillForm
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet
from chantiermobile.constants import UserRoles
from projects.models import Site

class PersonnelListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Personnel
    template_name = 'personnel/personnel_list.html'
    context_object_name = 'personnel_list'
    ordering = ['last_name', 'first_name']
    header_title = _("Ressources humaines")
    header_subtitle = _("Gérez le personnel et les affectations sur les chantiers")

    def get_queryset(self):
        qs = super().get_queryset().select_related('cabinet')
        personnel_type = self.request.GET.get('type')
        if personnel_type:
            qs = qs.filter(personnel_type=personnel_type)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_type_filter'] = self.request.GET.get('type', '')
        return context

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user,
            role__in=[UserRoles.DIRECTOR, UserRoles.CHIEF_ENGINEER]
        ).exists():
            return [{
                'label': _("Enregistrer un personnel"),
                'url': str(reverse_lazy('personnel:personnel_create')),
                'icon': 'user-plus',
                'class': 'btn-falcon-primary'
            }]
        return []

class PersonnelCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = Personnel
    form_class = PersonnelForm
    template_name = 'personnel/personnel_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    success_url = reverse_lazy('personnel:personnel_list')
    header_title = _("Enregistrer un nouveau personnel")
    header_subtitle = _("Ajoutez un nouveau membre du personnel au système")
    back_url = reverse_lazy('personnel:personnel_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Ressources humaines"), 'url': str(reverse_lazy('personnel:personnel_list'))},
            {'title': _("Nouvel enregistrement"), 'url': None},
        ]

    def form_valid(self, form):
        cabinet = self.get_user_cabinet()
        if not cabinet:
             messages.error(self.request, _("Identification du cabinet échouée."))
             return self.form_invalid(form)

        form.instance.cabinet = cabinet
        messages.success(self.request, _("Personnel enregistré avec succès."))
        return super().form_valid(form)

class PersonnelDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = Personnel
    template_name = 'personnel/personnel_detail.html'
    context_object_name = 'personnel'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'

    def get_header_title(self):
        return self.object.get_full_name()

    def get_header_subtitle(self):
        return _("Membre du personnel")

    def get_back_url(self):
        return str(reverse_lazy('personnel:personnel_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Ressources humaines"), 'url': str(reverse_lazy('personnel:personnel_list'))},
            {'title': self.object.get_full_name(), 'url': None},
        ]

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        user = self.request.user
        actions = []

        is_admin = user.is_superuser or UserCabinetRole.objects.filter(
            user=user, role__in=[UserRoles.DIRECTOR, UserRoles.CHIEF_ENGINEER]
        ).exists()

        is_director = user.is_superuser or UserCabinetRole.objects.filter(
            user=user, role='DIRECTOR'
        ).exists()

        if is_admin:
            actions.append({
                'label': _("Modifier le profil"),
                'url': str(reverse_lazy('personnel:personnel_update', kwargs={'unique_id': self.object.unique_id})),
                'icon': 'user-edit',
                'class': 'btn-falcon-default'
            })
        
        return actions

class PersonnelUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    model = Personnel
    form_class = PersonnelForm
    template_name = 'personnel/personnel_form.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    
    def get_header_title(self):
        return _("Modifier le profil : %(name)s") % {'name': self.object.get_full_name()}

    def get_back_url(self):
        return str(reverse_lazy('personnel:personnel_detail', kwargs={'unique_id': self.object.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Ressources humaines"), 'url': str(reverse_lazy('personnel:personnel_list'))},
            {'title': self.object.get_full_name(), 'url': str(reverse_lazy('personnel:personnel_detail', kwargs={'unique_id': self.object.unique_id}))},
            {'title': _("Modifier"), 'url': None},
        ]

    def get_success_url(self):
        messages.success(self.request, _("Profil mis à jour avec succès."))
        return reverse_lazy('personnel:personnel_detail', kwargs={'unique_id': self.object.unique_id})

class PersonnelDeleteView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DeleteView):
    model = Personnel
    template_name = 'projects/confirm_delete.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    success_url = reverse_lazy('personnel:personnel_list')
    allowed_roles = ['DIRECTOR']

    def get_header_title(self):
        return _("Supprimer le personnel : %(name)s") % {'name': self.object.get_full_name()}

    def get_header_subtitle(self):
        return _("Cette action est irréversible.")

    def get_back_url(self):
        return str(reverse_lazy('personnel:personnel_detail', kwargs={'unique_id': self.object.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Personnel"), 'url': str(reverse_lazy('personnel:personnel_list'))},
            {'title': self.object.get_full_name(), 'url': str(reverse_lazy('personnel:personnel_detail', kwargs={'unique_id': self.object.unique_id}))},
            {'title': _("Supprimer"), 'url': None},
        ]

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        personnel_name = self.object.get_full_name()
        messages.success(request, _("Personnel '%(name)s' supprimé avec succès.") % {'name': personnel_name})
        return super().delete(request, *args, **kwargs)

class SkillListView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    model = Skill
    template_name = 'personnel/skill_list.html'
    context_object_name = 'skill_list'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    header_title = _("Catalogue des compétences")
    header_subtitle = _("Gérez les compétences et aptitudes des travailleurs")
    back_url = reverse_lazy('personnel:personnel_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Personnel"), 'url': str(reverse_lazy('personnel:personnel_list'))},
            {'title': _("Compétences"), 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = SkillForm()
        return context

    def post(self, request, *args, **kwargs):
        form = SkillForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Compétence ajoutée avec succès."))
            return redirect('personnel:skill_list')

        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form=form))


class SiteAssignmentCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = SiteAssignment
    form_class = SiteAssignmentForm
    template_name = 'personnel/assignment_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    cabinet_lookup_field = 'site__cabinet'
    header_title = _("Affecter un personnel à un chantier")
    header_subtitle = _("Associez un travailleur à un chantier de construction")
    back_url = reverse_lazy('personnel:personnel_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Personnel"), 'url': str(reverse_lazy('personnel:personnel_list'))},
            {'title': _("Nouvelle affectation"), 'url': None},
        ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user = self.request.user
        if user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                form.fields['site'].queryset = Site.objects.filter(cabinet=active_cabinet)
                form.fields['personnel'].queryset = Personnel.objects.filter(cabinet=active_cabinet)
        elif hasattr(user, 'cabinet_roles'):
            cabinets = user.cabinet_roles.values_list('cabinet', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__in=cabinets)
            form.fields['personnel'].queryset = Personnel.objects.filter(cabinet__in=cabinets)
        else:
            form.fields['site'].queryset = Site.objects.none()
            form.fields['personnel'].queryset = Personnel.objects.none()
        return form

    def get_initial(self):
        initial = super().get_initial()
        personnel_id = self.request.GET.get('personnel')
        if personnel_id:
            person = get_object_or_404(Personnel, unique_id=personnel_id)
            initial['personnel'] = person
            initial['daily_rate'] = person.default_daily_rate
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['no_cabinet_selected'] = (
            self.request.user.is_superuser and not get_session_cabinet(self.request)
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, _("Affectation au chantier effectuée avec succès."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('personnel:personnel_detail', kwargs={'unique_id': self.object.personnel.unique_id})
