from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import Personnel, Skill, SiteAssignment
from .forms import PersonnelForm, SiteAssignmentForm, SkillForm
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin

class PersonnelListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Personnel
    template_name = 'personnel/personnel_list.html'
    context_object_name = 'personnel_list'
    ordering = ['last_name', 'first_name']
    header_title = "Human Resources"
    header_subtitle = "Manage all personnel and staff assignments"
    
    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, 
            role__in=['DIRECTOR', 'CHIEF_ENGINEER']
        ).exists():
            return [{
                'label': 'Register Personnel',
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
    header_title = "Register New Personnel"
    header_subtitle = "Add a new staff member to the system"
    back_url = reverse_lazy('personnel:personnel_list')

    def get_breadcrumb_items(self):
        return [
            {'title': 'Human Resources', 'url': str(reverse_lazy('personnel:personnel_list'))},
            {'title': 'New Registration', 'url': None},
        ]

    def form_valid(self, form):
        cabinet = self.get_user_cabinet()
        if not cabinet:
             messages.error(self.request, "Cabinet identification failed.")
             return self.form_invalid(form)
             
        form.instance.cabinet = cabinet
        messages.success(self.request, "Personnel registered successfully.")
        return super().form_valid(form)

class PersonnelDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = Personnel
    template_name = 'personnel/personnel_detail.html'
    context_object_name = 'personnel'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'

    def get_header_title(self):
        return self.object.get_full_name() or self.object.username

    def get_header_subtitle(self):
        return self.object.job_title or "Staff Member"

    def get_back_url(self):
        return str(reverse_lazy('personnel:personnel_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Human Resources', 'url': str(reverse_lazy('personnel:personnel_list'))},
            {'title': self.object.last_name or self.object.username, 'url': None},
        ]

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        user = self.request.user
        actions = []
        
        is_admin = user.is_superuser or UserCabinetRole.objects.filter(
            user=user, role__in=['DIRECTOR', 'CHIEF_ENGINEER']
        ).exists()
        
        is_director = user.is_superuser or UserCabinetRole.objects.filter(
            user=user, role='DIRECTOR'
        ).exists()

        if is_admin:
            actions.append({
                'label': 'Edit Profile',
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
        return f"Edit Profile: {self.object.username}"

    def get_back_url(self):
        return str(reverse_lazy('personnel:personnel_detail', kwargs={'unique_id': self.object.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Human Resources', 'url': str(reverse_lazy('personnel:personnel_list'))},
            {'title': self.object.username, 'url': str(reverse_lazy('personnel:personnel_detail', kwargs={'unique_id': self.object.unique_id}))},
            {'title': 'Edit', 'url': None},
        ]
    
    def get_success_url(self):
        messages.success(self.request, "Profile updated.")
        return reverse_lazy('personnel:personnel_detail', kwargs={'unique_id': self.object.unique_id})

class PersonnelDeleteView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, DeleteView):
    model = Personnel
    template_name = 'projects/confirm_delete.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    success_url = reverse_lazy('personnel:personnel_list')
    allowed_roles = ['DIRECTOR']

class SkillListView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, ListView):
    model = Skill
    template_name = 'personnel/skill_list.html'
    context_object_name = 'skill_list'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = SkillForm()
        return context

    def post(self, request, *args, **kwargs):
        form = SkillForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Skill added successfully.")
            return redirect('personnel:skill_list')
        
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form=form))


class SiteAssignmentCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model = SiteAssignment
    form_class = SiteAssignmentForm
    template_name = 'personnel/assignment_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']

    def get_initial(self):
        initial = super().get_initial()
        personnel_id = self.request.GET.get('personnel')
        if personnel_id:
            person = get_object_or_404(Personnel, unique_id=personnel_id)
            initial['personnel'] = person
            initial['daily_rate'] = person.default_daily_rate
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Site assignment completed.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('personnel:personnel_detail', kwargs={'unique_id': self.object.personnel.unique_id})
