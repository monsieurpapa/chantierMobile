"""
Views for the `personnel` app: Personnel/Skill/SiteAssignment CRUD, the
dossier (PersonnelDocument), congés/jours fériés (Leave/Holiday), and
daily pointage (Attendance). The recurring pattern across this module is
HR_ADMIN_ROLES (cabinet-wide HR authority) vs. a plain ENGINEER scoped to
"their own crew" — the site(s) where they're Site.lead_engineer — via
`_is_hr_admin()` and the explicit lead_engineer checks in
SiteAssignmentCreateView.get_form, LeaveCreateView.get_form and
`_attendance_can_act`.
"""
from decimal import Decimal
import datetime

from django.db import models
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView, TemplateView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .models import Personnel, Skill, SiteAssignment, PersonnelDocument, Leave, Holiday, Attendance
from .forms import PersonnelForm, SiteAssignmentForm, SkillForm, PersonnelDocumentForm, LeaveForm, HolidayForm
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet, can_act_for_cabinet
from core.quickcreate import QuickCreateView
from chantiermobile.constants import UserRoles, PersonnelPayrollType, DIRECTOR_ROLES, AttendanceStatus, ApprovalStatus
from projects.models import Site

HR_ADMIN_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']

# An ENGINEER should be able to assign personnel to, and record leave
# for, their OWN crew — the site(s) where they're Site.lead_engineer —
# without inheriting the rest of what HR_ADMIN_ROLES grants cabinet-wide
# (public holidays, any personnel's dossier documents, deciding someone
# else's leave request). So these two are deliberately their own
# constants rather than just adding ENGINEER to HR_ADMIN_ROLES, and the
# views below scope the actual querysets via _is_hr_admin() so a plain
# engineer only ever sees/touches their own site's crew.
SITE_ASSIGNMENT_ROLES = HR_ADMIN_ROLES + ['ENGINEER']
LEAVE_CREATE_ROLES = HR_ADMIN_ROLES + ['ENGINEER']
# Same shape as the two above: an ENGINEER can record pointage for their
# own crew (the site(s) they lead), an HR_ADMIN_ROLES holder for any site
# in the cabinet. Scoped explicitly in AttendanceDailyView.dispatch()
# rather than via a queryset, since this is a per-site URL, not a form.
ATTENDANCE_ROLES = HR_ADMIN_ROLES + ['ENGINEER']


def _is_hr_admin(user, cabinets=None):
    """True for a full HR_ADMIN_ROLES holder (cabinet-wide HR reach).
    False for a plain ENGINEER, who should be scoped to their own led
    site(s) instead of the whole cabinet's personnel.

    FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now — see
    core/mixins.py and docs/security.md."""
    if user.is_superuser:
        return True
    qs = user.approved_cabinet_roles.filter(role__in=HR_ADMIN_ROLES)
    if cabinets is not None:
        qs = qs.filter(cabinet__in=cabinets)
    return qs.exists()

class PersonnelListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    """Lists the current user's Cabinet-scoped personnel roster, filterable
    by type/status/category/trade. Open to any cabinet member; only the
    "Enregistrer un personnel" header action is role-gated (director-tier
    or CHIEF_ENGINEER)."""
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
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(category=category)
        trade = self.request.GET.get('trade')
        if trade:
            qs = qs.filter(trade=trade)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_type_filter'] = self.request.GET.get('type', '')
        context['current_status_filter'] = self.request.GET.get('status', '')
        context['current_category_filter'] = self.request.GET.get('category', '')
        context['current_trade_filter'] = self.request.GET.get('trade', '')
        return context

    def get_header_actions(self):
        # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now —
        # see core/mixins.py and docs/security.md.
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user,
            role__in=[UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.CHIEF_ENGINEER],
            status=ApprovalStatus.APPROVED,
        ).exists():
            return [{
                'label': _("Enregistrer un personnel"),
                'url': str(reverse_lazy('personnel:personnel_create')),
                'icon': 'user-plus',
                'class': 'btn-falcon-primary'
            }]
        return []

class PersonnelCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    """Registers a new Personnel record. Director-tier or CHIEF_ENGINEER
    only (allowed_roles) — a plain ENGINEER cannot create new personnel,
    only assign existing ones to their own site (SiteAssignmentCreateView)."""
    model = Personnel
    form_class = PersonnelForm
    template_name = 'personnel/personnel_form.html'
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']
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
    """A Personnel's full profile. Open to any cabinet member; the
    "Modifier le profil" action is shown only to director-tier/
    CHIEF_ENGINEER (see get_header_actions)."""
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
        # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now —
        # see core/mixins.py and docs/security.md.
        from accounts.models import UserCabinetRole
        user = self.request.user
        actions = []

        is_admin = user.is_superuser or UserCabinetRole.objects.filter(
            user=user, role__in=[UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.CHIEF_ENGINEER],
            status=ApprovalStatus.APPROVED,
        ).exists()

        is_director = user.is_superuser or UserCabinetRole.objects.filter(
            user=user, role__in=DIRECTOR_ROLES, status=ApprovalStatus.APPROVED,
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
    """Edits a Personnel profile. Director-tier or CHIEF_ENGINEER only
    (allowed_roles)."""
    model = Personnel
    form_class = PersonnelForm
    template_name = 'personnel/personnel_form.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']
    
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
    """Soft-deletes a Personnel record. Director-tier only
    (allowed_roles) — narrower than Create/Update, which also allow
    CHIEF_ENGINEER."""
    model = Personnel
    template_name = 'projects/confirm_delete.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    success_url = reverse_lazy('personnel:personnel_list')
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL']

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
    """Lists and (via its inline POST handler) creates Skills — the
    shared, non-cabinet-scoped tag catalog. Director-tier or
    CHIEF_ENGINEER only (allowed_roles); note allowed_roles isn't scoped
    to a specific cabinet here since Skill has no cabinet of its own."""
    model = Skill
    template_name = 'personnel/skill_list.html'
    context_object_name = 'skill_list'
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']
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
    """Assigns a Personnel to a Site. HR_ADMIN_ROLES (cabinet-wide) or
    ENGINEER (SITE_ASSIGNMENT_ROLES); get_form() further narrows a plain
    ENGINEER's `site` choices to only the site(s) they lead (see
    `_is_hr_admin`) — allowed_roles alone doesn't carry that
    restriction, it's enforced by scoping the form field's queryset."""
    model = SiteAssignment
    form_class = SiteAssignmentForm
    template_name = 'personnel/assignment_form.html'
    allowed_roles = SITE_ASSIGNMENT_ROLES
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
        # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now —
        # see core/mixins.py and docs/security.md.
        if user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                form.fields['site'].queryset = Site.objects.filter(cabinet=active_cabinet)
                form.fields['personnel'].queryset = Personnel.objects.filter(cabinet=active_cabinet)
        elif hasattr(user, 'approved_cabinet_roles'):
            cabinets = user.approved_cabinet_roles.values_list('cabinet', flat=True)
            site_qs = Site.objects.filter(cabinet__in=cabinets)
            if not _is_hr_admin(user, cabinets):
                # Plain ENGINEER: assigning personnel is a cabinet-wide HR
                # action for everyone else — restrict them to the site(s)
                # they actually lead.
                site_qs = site_qs.filter(lead_engineer=user)
            form.fields['site'].queryset = site_qs
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
        # "Assign Staff" on the site detail page links here with ?site=<pk>
        # — prefill it so the field isn't left for the user to reselect
        # from scratch (this was silently ignored before).
        site_id = self.request.GET.get('site')
        if site_id:
            initial['site'] = site_id
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


# ---------------------------------------------------------------------
# Dossier (documents), congés/jours fériés
# ---------------------------------------------------------------------

class PersonnelDocumentCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    """Upload a file into a Personnel's dossier. Scoped by cabinet via the
    parent Personnel (not CabinetAccessMixin, since PersonnelDocument has
    no direct cabinet FK)."""
    model = PersonnelDocument
    form_class = PersonnelDocumentForm
    template_name = 'personnel/document_form.html'
    allowed_roles = HR_ADMIN_ROLES
    header_title = _("Ajouter un document au dossier")

    def dispatch(self, request, *args, **kwargs):
        self.personnel = get_object_or_404(Personnel, unique_id=kwargs['unique_id'])
        return super().dispatch(request, *args, **kwargs)

    def get_role_cabinet(self):
        return self.personnel.cabinet

    def get_back_url(self):
        return str(reverse_lazy('personnel:personnel_detail', kwargs={'unique_id': self.personnel.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Ressources humaines"), 'url': str(reverse_lazy('personnel:personnel_list'))},
            {'title': self.personnel.get_full_name(), 'url': self.get_back_url()},
            {'title': _("Dossier"), 'url': None},
        ]

    def form_valid(self, form):
        form.instance.personnel = self.personnel
        messages.success(self.request, _("Document ajouté au dossier."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('personnel:personnel_detail', kwargs={'unique_id': self.personnel.unique_id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['personnel'] = self.personnel
        return context


class PersonnelDocumentDeleteView(LoginRequiredMixin, RoleRequiredMixin, DeleteView):
    """Removes a file from a Personnel's dossier. HR_ADMIN_ROLES only,
    scoped to the document's own personnel's cabinet via
    get_role_cabinet()."""
    model = PersonnelDocument
    allowed_roles = HR_ADMIN_ROLES

    def get_role_cabinet(self):
        return self.get_object().personnel.cabinet

    def get_success_url(self):
        messages.success(self.request, _("Document supprimé."))
        return reverse_lazy('personnel:personnel_detail', kwargs={'unique_id': self.object.personnel.unique_id})

    def post(self, request, *args, **kwargs):
        return self.delete(request, *args, **kwargs)


class LeaveListView(LoginRequiredMixin, PageHeaderMixin, ListView):
    """Congés — scoped to the current user's cabinet(s) via Personnel."""
    model = Leave
    template_name = 'personnel/leave_list.html'
    context_object_name = 'leave_list'
    header_title = _("Congés")
    header_subtitle = _("Gérez les congés du personnel")
    back_url = reverse_lazy('personnel:personnel_list')

    def get_queryset(self):
        qs = Leave.objects.select_related('personnel').order_by('-start_date')
        user = self.request.user
        # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now —
        # see core/mixins.py and docs/security.md.
        if not user.is_superuser:
            cabinets = user.approved_cabinet_roles.values_list('cabinet', flat=True) if hasattr(user, 'approved_cabinet_roles') else []
            qs = qs.filter(personnel__cabinet__in=cabinets)
        else:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                qs = qs.filter(personnel__cabinet=active_cabinet)
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_status_filter'] = self.request.GET.get('status', '')
        # Deciding (approve/reject) someone's leave stays an HR_ADMIN_ROLES
        # action; creating one is now open to an ENGINEER too (for their
        # own crew) — these are two different template checks so the
        # "Déclarer un congé" button doesn't imply approve/reject rights.
        user = self.request.user
        is_hr_admin = _is_hr_admin(user)
        context['can_decide_leave'] = is_hr_admin
        # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now —
        # see core/mixins.py and docs/security.md.
        context['can_create_leave'] = is_hr_admin or (
            user.is_authenticated and user.approved_cabinet_roles.filter(role__in=LEAVE_CREATE_ROLES).exists()
        )
        # Kept for any other template still relying on the old name.
        context['can_manage'] = context['can_decide_leave']
        return context


class LeaveCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    """Declares a leave for a Personnel. HR_ADMIN_ROLES or ENGINEER
    (LEAVE_CREATE_ROLES); get_form() narrows a plain ENGINEER's
    `personnel` choices to workers currently assigned to a site they
    lead. Deciding the leave (approve/reject) is a separate,
    HR_ADMIN_ROLES-only action — see `_decide_leave`."""
    model = Leave
    form_class = LeaveForm
    template_name = 'personnel/leave_form.html'
    allowed_roles = LEAVE_CREATE_ROLES
    success_url = reverse_lazy('personnel:leave_list')
    header_title = _("Déclarer un congé")
    header_subtitle = _("Enregistrez un congé pour un membre du personnel")
    back_url = reverse_lazy('personnel:leave_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user = self.request.user
        # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now —
        # see core/mixins.py and docs/security.md.
        if user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            form.fields['personnel'].queryset = (
                Personnel.objects.filter(cabinet=active_cabinet) if active_cabinet else Personnel.objects.all()
            )
        elif hasattr(user, 'approved_cabinet_roles'):
            cabinets = user.approved_cabinet_roles.values_list('cabinet', flat=True)
            personnel_qs = Personnel.objects.filter(cabinet__in=cabinets)
            if not _is_hr_admin(user, cabinets):
                # Plain ENGINEER: only personnel currently assigned to a
                # site they lead — their own crew, not the whole
                # cabinet's personnel roster.
                personnel_qs = personnel_qs.filter(assignments__site__lead_engineer=user).distinct()
            form.fields['personnel'].queryset = personnel_qs
        return form

    def form_valid(self, form):
        response = super().form_valid(form)
        from core.notifications import notify_role_holders
        notify_role_holders(
            self.object.personnel.cabinet, HR_ADMIN_ROLES,
            _("Nouveau congé à examiner : %(name)s") % {'name': self.object.personnel.get_full_name()},
            str(reverse_lazy('personnel:leave_list')),
            exclude_user=self.request.user,
        )
        messages.success(self.request, _("Congé enregistré avec succès."))
        return response


def _decide_leave(request, pk, approve):
    """Shared approve/reject path for a Leave. HR_ADMIN_ROLES only,
    scoped to the personnel's cabinet via can_act_for_cabinet — note
    this is cabinet-wide, not restricted to "the requester's own
    lead_engineer"; unlike planning/phase actions it also deliberately
    excludes ENGINEER from deciding (only from creating) a leave."""
    leave = get_object_or_404(Leave, pk=pk)
    if not can_act_for_cabinet(request, leave.personnel.cabinet, HR_ADMIN_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('personnel:leave_list')
    from chantiermobile.constants import ApprovalStatus
    leave.status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
    leave.decided_by = request.user
    leave.decided_at = timezone.now()
    leave.save(update_fields=['status', 'decided_by', 'decided_at', 'updated_at'])
    if leave.personnel.user_id:
        from core.notifications import notify_user
        notify_user(
            leave.personnel.user,
            _("Votre congé a été approuvé.") if approve else _("Votre congé a été rejeté."),
            str(reverse_lazy('personnel:leave_list')),
        )
    messages.success(
        request,
        _("Congé approuvé.") if approve else _("Congé rejeté."),
    )
    return redirect('personnel:leave_list')


def leave_approve(request, pk):
    """Approves a pending Leave — see `_decide_leave` for the actual
    permission check."""
    return _decide_leave(request, pk, approve=True)


def leave_reject(request, pk):
    """Rejects a pending Leave — see `_decide_leave` for the actual
    permission check."""
    return _decide_leave(request, pk, approve=False)


class HolidayListView(LoginRequiredMixin, PageHeaderMixin, ListView):
    """Lists the cabinet's public holidays (jours fériés). Open to any
    cabinet member; "can_manage" (create/delete) is HR_ADMIN_ROLES-only,
    checked separately in get_context_data."""
    model = Holiday
    template_name = 'personnel/holiday_list.html'
    context_object_name = 'holiday_list'
    header_title = _("Jours fériés")
    header_subtitle = _("Calendrier des jours fériés")
    back_url = reverse_lazy('personnel:personnel_list')

    def get_queryset(self):
        qs = Holiday.objects.order_by('date')
        user = self.request.user
        # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now —
        # see core/mixins.py and docs/security.md.
        if not user.is_superuser:
            cabinets = user.approved_cabinet_roles.values_list('cabinet', flat=True) if hasattr(user, 'approved_cabinet_roles') else []
            qs = qs.filter(cabinet__in=cabinets)
        else:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                qs = qs.filter(cabinet=active_cabinet)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now —
        # see core/mixins.py and docs/security.md.
        context['can_manage'] = (
            self.request.user.is_superuser or
            self.request.user.approved_cabinet_roles.filter(role__in=HR_ADMIN_ROLES).exists()
        )
        return context


class HolidayCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    """Adds a holiday. HR_ADMIN_ROLES only (allowed_roles), tagged to
    the creator's own cabinet."""
    model = Holiday
    form_class = HolidayForm
    template_name = 'personnel/holiday_form.html'
    allowed_roles = HR_ADMIN_ROLES
    success_url = reverse_lazy('personnel:holiday_list')
    header_title = _("Ajouter un jour férié")
    back_url = reverse_lazy('personnel:holiday_list')

    def form_valid(self, form):
        cabinet = self.get_user_cabinet()
        if not cabinet:
            messages.error(self.request, _("Identification du cabinet échouée."))
            return self.form_invalid(form)
        form.instance.cabinet = cabinet
        messages.success(self.request, _("Jour férié ajouté."))
        return super().form_valid(form)


class HolidayDeleteView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, DeleteView):
    """Removes a holiday. HR_ADMIN_ROLES only (allowed_roles)."""
    model = Holiday
    allowed_roles = HR_ADMIN_ROLES
    success_url = reverse_lazy('personnel:holiday_list')

    def post(self, request, *args, **kwargs):
        messages.success(request, _("Jour férié supprimé."))
        return self.delete(request, *args, **kwargs)


class PersonnelQuickCreateView(QuickCreateView):
    """Backs the "select or add a worker" pickers (Leave, SiteAssignment,
    Task assignment, Expense/Payroll main-d'œuvre, Paie du personnel
    Ingénieurs & Staff, ...). Only a name is typed at this point — the
    rest of the profile (type, rate, category, monthly salary, ...) gets
    filled in later from the worker's own edit screen."""
    model = Personnel

    def build_instance(self, name, request, cabinet, payload):
        parts = name.split(None, 1)
        first_name, last_name = parts[0], (parts[1] if len(parts) > 1 else '')
        # SalaryPaymentItemForm's picker (Ingénieurs & Staff tab) sends a
        # fixed 'payroll_type': 'INGENIEUR' extra param — without honoring
        # it here, a name typed there would quick-create as the default
        # Ouvrier and immediately fail SalaryPaymentItem.clean()'s
        # Ingénieur-only guard. Any other/missing value keeps the model's
        # own default (Ouvrier), unchanged for every other picker.
        kwargs = {}
        payroll_type = payload.get('payroll_type')
        if payroll_type in PersonnelPayrollType.values:
            kwargs['payroll_type'] = payroll_type
        return Personnel(
            cabinet=cabinet,
            first_name=first_name,
            last_name=last_name,
            default_daily_rate=Decimal('0.00'),
            **kwargs,
        )

    def display_text(self, instance):
        return instance.get_full_name()

    def after_create(self, instance, request, payload):
        # If this picker was scoped to a site (e.g. the expense form's
        # site-assigned personnel list), assign the new worker to that
        # site right away so they immediately show up wherever that
        # scoping is re-applied.
        site_id = payload.get('site')
        if not site_id:
            return
        site = Site.objects.filter(pk=site_id, cabinet=instance.cabinet).first()
        if site:
            SiteAssignment.objects.create(
                personnel=instance,
                site=site,
                role=_('Ouvrier'),
                start_date=datetime.date.today(),
                daily_rate=Decimal('0.00'),
            )


class SkillQuickCreateView(QuickCreateView):
    """Backs the worker "skills" tag picker. Skills aren't cabinet-scoped —
    they're a shared tag list across the whole system."""
    model = Skill
    cabinet_scoped = False

    def build_instance(self, name, request, cabinet, payload):
        return Skill(name=name)


def _attendance_can_act(request, site):
    """An HR_ADMIN_ROLES holder can record any site's pointage; a plain
    ENGINEER only their own led site — same ownership rule as item 6's
    site-assignment/leave scoping (SiteAssignmentCreateView, LeaveCreateView)."""
    if can_act_for_cabinet(request, site.cabinet, HR_ADMIN_ROLES):
        return True
    return site.lead_engineer_id == request.user.pk


class AttendanceDailyView(LoginRequiredMixin, PageHeaderMixin, TemplateView):
    """Item 14 of the Directors/Engineers audit: there was no attendance
    tracking at all. One row per personnel currently assigned to this
    site, with a status <select> for the selected date — mirrors
    PayrollListAllocateView's bulk-row pattern (finance/views.py) rather
    than a one-record-at-a-time CreateView, since pointage is filled in
    for the whole crew at once, every day."""
    template_name = 'personnel/attendance_daily.html'

    def dispatch(self, request, *args, **kwargs):
        self.site = get_object_or_404(Site, unique_id=kwargs['unique_id'])
        if not _attendance_can_act(request, self.site):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('projects:site_detail', unique_id=self.site.unique_id)
        raw_date = request.GET.get('date') or request.POST.get('date')
        try:
            self.date = datetime.date.fromisoformat(raw_date) if raw_date else timezone.localdate()
        except ValueError:
            self.date = timezone.localdate()
        return super().dispatch(request, *args, **kwargs)

    def get_header_title(self):
        return _("Pointage — %(site)s") % {'site': self.site.name}

    def get_header_subtitle(self):
        return str(self.date)

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.site.unique_id}))

    def get_rows(self):
        assignments = SiteAssignment.objects.filter(
            site=self.site, start_date__lte=self.date,
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=self.date)
        ).select_related('personnel').order_by('personnel__last_name', 'personnel__first_name')
        existing = {
            a.personnel_id: a for a in Attendance.objects.filter(site=self.site, date=self.date)
        }
        rows = []
        seen_personnel = set()
        for assignment in assignments:
            personnel = assignment.personnel
            if personnel.pk in seen_personnel:
                continue
            seen_personnel.add(personnel.pk)
            record = existing.get(personnel.pk)
            rows.append({
                'personnel': personnel,
                'status': record.status if record else AttendanceStatus.PRESENT,
                'notes': record.notes if record else '',
            })
        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site'] = self.site
        context['date'] = self.date
        context['rows'] = self.get_rows()
        context['status_choices'] = AttendanceStatus.choices
        context['history_url'] = reverse_lazy('personnel:attendance_history', kwargs={'unique_id': self.site.unique_id})
        return context

    def post(self, request, *args, **kwargs):
        for row in self.get_rows():
            personnel = row['personnel']
            status = request.POST.get(f'status_{personnel.pk}', AttendanceStatus.PRESENT)
            if status not in AttendanceStatus.values:
                status = AttendanceStatus.PRESENT
            notes = (request.POST.get(f'notes_{personnel.pk}') or '').strip()
            Attendance.objects.update_or_create(
                personnel=personnel, site=self.site, date=self.date,
                defaults={'status': status, 'notes': notes, 'recorded_by': request.user},
            )
        messages.success(request, _("Pointage enregistré pour le %(date)s.") % {'date': self.date})
        return redirect(f"{reverse_lazy('personnel:attendance_daily', kwargs={'unique_id': self.site.unique_id})}?date={self.date.isoformat()}")


class AttendanceHistoryView(LoginRequiredMixin, PageHeaderMixin, TemplateView):
    """Read-only history for a site's pointage — the last 30 days'
    records, newest first, one line per worker per day."""
    template_name = 'personnel/attendance_history.html'

    def dispatch(self, request, *args, **kwargs):
        self.site = get_object_or_404(Site, unique_id=kwargs['unique_id'])
        if not _attendance_can_act(request, self.site):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('projects:site_detail', unique_id=self.site.unique_id)
        return super().dispatch(request, *args, **kwargs)

    def get_header_title(self):
        return _("Historique de pointage — %(site)s") % {'site': self.site.name}

    def get_back_url(self):
        return str(reverse_lazy('personnel:attendance_daily', kwargs={'unique_id': self.site.unique_id}))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site'] = self.site
        context['records'] = Attendance.objects.filter(site=self.site).select_related('personnel', 'recorded_by')[:200]
        return context
