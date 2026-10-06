"""Tests for the 2026-10-06 Personnel/"Chantiers & conventions" feature:

- Personnel assignable to one or more Chantiers (Site) straight from the
  Personnel form, via a dynamic inline formset of lightweight
  SiteAssignment rows ("conventions").
- `default_daily_rate` optional (covered more directly in
  test_cashier_magasinier_features.py's cashier personnel tests, which
  already omit it).
- `monthly_salary` relabeled "Convention" in the template (cosmetic).
- A convention row names a ProjectPhase (étape) inline — reusing an
  existing one (case-insensitive, scoped to the site) rather than
  creating a duplicate when the name matches.
- The payroll ("liste de paie") disbursement screen surfaces the
  convention's name/étape/amount next to each item, so the cashier knows
  what a payment is tied to.

See AskUserQuestion answers recorded in the task history: a convention
row captures only name + étape + montant (no daily rate), and a
duplicate étape name on the same site reuses the existing étape rather
than creating a second one.
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from personnel.models import SiteAssignment
from personnel.forms import SiteAssignmentForm
from projects.models import ProjectPhase
from chantiermobile.constants import PersonnelPayrollType


def _convention_management_data(prefix='convention', total=1, initial=0):
    return {
        f'{prefix}-TOTAL_FORMS': str(total),
        f'{prefix}-INITIAL_FORMS': str(initial),
        f'{prefix}-MIN_NUM_FORMS': '0',
        f'{prefix}-MAX_NUM_FORMS': '1000',
    }


def _personnel_payload(**overrides):
    payload = {
        'first_name': 'Nouveau', 'last_name': 'Agent', 'personnel_type': 'EMPLOYE',
        'category': 'TERRAIN', 'status': 'ACTIF', 'payroll_type': 'OUVRIER',
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestSiteAssignmentOptionalFields:
    """SiteAssignment widened 2026-10-06 so a convention row (site + name
    + phase + convention_amount only) can be saved without the fields a
    full affectation (role/start_date/daily_rate) used to require."""

    def test_can_create_without_role_dates_or_daily_rate(self, personnel, site):
        assignment = SiteAssignment.objects.create(
            personnel=personnel, site=site, name='Finition dalle bloc B',
            convention_amount=Decimal('500.00'),
        )
        assert assignment.role == ''
        assert assignment.start_date is None
        assert assignment.daily_rate is None

    def test_full_assignment_form_still_requires_role_dates_and_rate(self, personnel, site):
        """SiteAssignmentForm (the separate, standalone affectation flow)
        should keep its old requiredness even though the model fields
        themselves are now optional — only the new lightweight
        ConventionForm should skip them."""
        form = SiteAssignmentForm(data={
            'personnel': personnel.pk, 'site': site.pk,
        })
        assert not form.is_valid()
        assert 'role' in form.errors
        assert 'start_date' in form.errors
        assert 'daily_rate' in form.errors


@pytest.mark.django_db
class TestPersonnelFormConventionSection:
    """The Personnel create/edit form's dynamic "Chantiers & conventions"
    section (requirements: assign to one-or-more chantiers; dynamic
    étape creation auto-linked to the convention)."""

    def test_get_or_create_convention_management_fields_present(self, director_client):
        response = director_client.get(reverse('personnel:personnel_create'))
        assert response.status_code == 200
        assert b'convention-TOTAL_FORMS' in response.content
        assert 'Chantiers & conventions'.encode() in response.content
        # Cosmetic rename: "Salaire mensuel" -> "Convention" on the label.
        assert 'Convention ($)'.encode() in response.content

    def test_create_personnel_with_new_site_and_new_phase(self, director_client, site, cabinet):
        payload = _personnel_payload(first_name='Awa', last_name='Diallo')
        payload.update(_convention_management_data(total=1))
        payload.update({
            'convention-0-site': str(site.pk),
            'convention-0-name': 'Finition dalle bloc B',
            'convention-0-new_phase_name': 'Fondations',
            'convention-0-convention_amount': '500.00',
        })
        response = director_client.post(reverse('personnel:personnel_create'), payload)
        assert response.status_code == 302, getattr(response, 'context', None) and response.context['form'].errors

        from personnel.models import Personnel
        new_personnel = Personnel.objects.get(first_name='Awa', last_name='Diallo')
        assignment = new_personnel.assignments.get()
        assert assignment.site_id == site.pk
        assert assignment.name == 'Finition dalle bloc B'
        assert assignment.convention_amount == Decimal('500.00')
        assert assignment.phase is not None
        assert assignment.phase.name == 'Fondations'
        assert assignment.phase.site_id == site.pk

    def test_duplicate_phase_name_is_reused_not_duplicated(self, director_client, site, phase_factory):
        existing_phase = phase_factory(site, name='Gros œuvre')
        payload = _personnel_payload(first_name='Moussa', last_name='Keita')
        payload.update(_convention_management_data(total=1))
        payload.update({
            'convention-0-site': str(site.pk),
            'convention-0-name': 'Coffrage',
            # Same name, different case — must reuse, not duplicate.
            'convention-0-new_phase_name': 'gros œuvre',
            'convention-0-convention_amount': '',
        })
        response = director_client.post(reverse('personnel:personnel_create'), payload)
        assert response.status_code == 302

        from personnel.models import Personnel
        new_personnel = Personnel.objects.get(first_name='Moussa', last_name='Keita')
        assignment = new_personnel.assignments.get()
        assert assignment.phase_id == existing_phase.pk
        assert ProjectPhase.objects.filter(site=site, name__iexact='gros œuvre').count() == 1

    def test_update_personnel_adds_second_convention(self, director_client, personnel, site, site_factory, phase_factory):
        other_site = site_factory(name='Autre Chantier')
        phase_a = phase_factory(site, name='Terrassement')
        existing = SiteAssignment.objects.create(
            personnel=personnel, site=site, name='Terrassement lot 1', phase=phase_a,
            convention_amount=Decimal('200.00'),
        )
        payload = _personnel_payload(first_name=personnel.first_name, last_name=personnel.last_name)
        payload.update(_convention_management_data(total=2, initial=1))
        payload.update({
            'convention-0-id': str(existing.pk),
            'convention-0-site': str(site.pk),
            'convention-0-name': existing.name,
            'convention-0-phase': str(phase_a.pk),
            'convention-0-convention_amount': '200.00',
            'convention-1-site': str(other_site.pk),
            'convention-1-name': 'Peinture',
            'convention-1-new_phase_name': 'Finitions',
            'convention-1-convention_amount': '150.00',
        })
        response = director_client.post(
            reverse('personnel:personnel_update', kwargs={'unique_id': personnel.unique_id}), payload,
        )
        assert response.status_code == 302, getattr(response, 'context', None) and response.context['form'].errors

        personnel.refresh_from_db()
        assert personnel.assignments.count() == 2
        new_row = personnel.assignments.get(site=other_site)
        assert new_row.name == 'Peinture'
        assert new_row.phase.name == 'Finitions'

    def test_legacy_post_without_convention_fields_still_saves_personnel(self, director_client):
        """A POST that doesn't include the formset's management fields at
        all (an older client, or any caller unaware of this section)
        must not 500 — it's treated as "no conventions submitted"."""
        payload = _personnel_payload(first_name='Legacy', last_name='Client')
        response = director_client.post(reverse('personnel:personnel_create'), payload)
        assert response.status_code == 302

        from personnel.models import Personnel
        new_personnel = Personnel.objects.get(first_name='Legacy', last_name='Client')
        assert new_personnel.assignments.count() == 0

    def test_row_with_site_but_no_name_or_phase_is_rejected(self, director_client, site):
        payload = _personnel_payload(first_name='Invalide', last_name='Row')
        payload.update(_convention_management_data(total=1))
        payload.update({'convention-0-site': str(site.pk)})
        response = director_client.post(reverse('personnel:personnel_create'), payload)
        assert response.status_code == 200
        from personnel.models import Personnel
        assert not Personnel.objects.filter(first_name='Invalide', last_name='Row').exists()


@pytest.mark.django_db
class TestPayrollDisbursementShowsConventionDetails:
    """Requirement: at décaissement, the cashier should know which
    convention (and its details) a payment is tied to."""

    def test_convention_name_phase_and_cap_are_shown_on_payroll_detail(
        self, director_client, site, personnel_factory, phase_factory,
    ):
        from finance.models import PayrollList, PayrollListItem

        phase = phase_factory(site, name='Second œuvre')
        worker = personnel_factory(payroll_type=PersonnelPayrollType.OUVRIER)
        assignment = SiteAssignment.objects.create(
            personnel=worker, site=site, name='Finition dalle bloc B', phase=phase,
            convention_amount=Decimal('500.00'),
        )
        payroll_list = PayrollList.objects.create(site=site)
        PayrollListItem.objects.create(
            payroll_list=payroll_list, personnel=worker, assignment=assignment, amount=Decimal('200.00'),
        )

        response = director_client.get(reverse('finance:payroll_detail', kwargs={'pk': payroll_list.pk}))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Finition dalle bloc B' in content
        assert 'Second œuvre' in content
        # Cap (500) and remaining (500 - 200 = 300) should both surface.
        assert '500' in content
        assert '300' in content
