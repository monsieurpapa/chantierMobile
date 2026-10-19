"""Tests for the 2026-10-19 "Types de convention" feature (meeting-note
backlog): a SiteAssignment-based convention can now say explicitly
whether it covers a single étape (PAR_ETAPE, the pre-existing implicit
default — a convention with a `phase` set) or the whole chantier
(CHANTIER_ENTIER — a convention that intentionally carries no `phase`).

Covers:
- The ConventionScope enum's choices.
- SiteAssignment.clean()'s remaining model-level check: a
  CHANTIER_ENTIER convention must not carry a `phase`. (The reverse —
  PAR_ETAPE requiring a phase or new_phase_name — is deliberately NOT
  enforced at the model level; see SiteAssignment.clean()'s docstring.
  It's enforced by ConventionForm.clean() instead, already covered by
  tests/test_personnel_convention_feature.py's new-étape test cases.)
- ConventionForm.clean()'s scope-based behavior: CHANTIER_ENTIER clears
  any phase/new_phase_name the user had picked.
- The 0015 backfill migration's inference rule, re-invoked directly
  (per this codebase's --nomigrations/--reuse-db convention — see
  tests/test_stock_and_material_workflow.py's
  TestValidatedStatusMigratedForward for the established pattern).
- An HTTP-level round trip creating a CHANTIER_ENTIER convention through
  personnel:personnel_create.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from chantiermobile.constants import ConventionScope
from personnel.forms import ConventionForm
from personnel.models import SiteAssignment


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


class TestConventionScopeChoices:
    def test_scope_has_par_etape_and_chantier_entier(self):
        values = dict(ConventionScope.choices)
        assert set(values) == {'PAR_ETAPE', 'CHANTIER_ENTIER'}
        assert values['PAR_ETAPE'] == 'Par étape'
        assert values['CHANTIER_ENTIER'] == 'Chantier entier'


@pytest.mark.django_db
class TestSiteAssignmentCleanScopeCheck:
    def test_chantier_entier_with_phase_is_rejected(self, personnel, site, phase_factory):
        phase = phase_factory(site)
        assignment = SiteAssignment(
            personnel=personnel, site=site, name='Gardiennage',
            scope=ConventionScope.CHANTIER_ENTIER, phase=phase,
        )
        with pytest.raises(ValidationError) as excinfo:
            assignment.clean()
        assert 'scope' in excinfo.value.error_dict

    def test_chantier_entier_without_phase_is_valid(self, personnel, site):
        assignment = SiteAssignment(
            personnel=personnel, site=site, name='Gardiennage',
            scope=ConventionScope.CHANTIER_ENTIER,
        )
        assignment.clean()  # must not raise

    def test_par_etape_without_phase_does_not_raise_at_model_level(self, personnel, site):
        """The model itself has no way to know a view is about to resolve
        a `new_phase_name` into a real phase, so it must not block this
        — that's ConventionForm.clean()'s job (form-level, with correct
        timing relative to the view's get-or-create)."""
        assignment = SiteAssignment(
            personnel=personnel, site=site, name='Coffrage',
            scope=ConventionScope.PAR_ETAPE,
        )
        assignment.clean()  # must not raise

    def test_par_etape_with_phase_is_valid(self, personnel, site, phase_factory):
        phase = phase_factory(site)
        assignment = SiteAssignment(
            personnel=personnel, site=site, name='Coffrage',
            scope=ConventionScope.PAR_ETAPE, phase=phase,
        )
        assignment.clean()  # must not raise


@pytest.mark.django_db
class TestConventionFormScopeClean:
    def test_chantier_entier_clears_phase_and_new_phase_name(self, cabinet, site, phase_factory):
        phase = phase_factory(site)
        form = ConventionForm(cabinet=cabinet, data={
            'site': site.pk, 'name': 'Gardiennage',
            'scope': ConventionScope.CHANTIER_ENTIER,
            'phase': str(phase.pk), 'new_phase_name': 'Peu importe',
        })
        assert form.is_valid(), form.errors
        assert form.cleaned_data['phase'] is None
        assert form.cleaned_data['new_phase_name'] == ''
        assert form.cleaned_data['scope'] == ConventionScope.CHANTIER_ENTIER

    def test_par_etape_still_requires_phase_or_new_phase_name(self, cabinet, site):
        form = ConventionForm(cabinet=cabinet, data={
            'site': site.pk, 'name': 'Coffrage',
            'scope': ConventionScope.PAR_ETAPE,
        })
        assert not form.is_valid()

    def test_blank_scope_defaults_to_par_etape_and_still_requires_phase(self, cabinet, site):
        form = ConventionForm(cabinet=cabinet, data={
            'site': site.pk, 'name': 'Coffrage',
        })
        assert not form.is_valid()


@pytest.mark.django_db
class TestBackfillConventionScopeMigration:
    """Re-invokes personnel/migrations/0015_backfill_convention_scope's
    function directly, mirroring
    tests/test_stock_and_material_workflow.py's established pattern —
    RunPython seed/backfill functions never execute against the real
    pytest database (pytest.ini sets --nomigrations)."""

    def test_backfill_infers_scope_from_phase_presence(self, personnel, site, phase_factory):
        import importlib
        migration_module = importlib.import_module(
            'personnel.migrations.0015_backfill_convention_scope'
        )

        phase = phase_factory(site)
        with_phase = SiteAssignment.objects.create(
            personnel=personnel, site=site, name='Coffrage', phase=phase,
        )
        without_phase = SiteAssignment.objects.create(
            personnel=personnel, site=site, name='Gardiennage',
        )
        # A plain affectation (no convention name) must be left untouched.
        plain_affectation = SiteAssignment.objects.create(
            personnel=personnel, site=site, role='Chef de chantier',
        )

        class _FakeApps:
            @staticmethod
            def get_model(app_label, model_name):
                return SiteAssignment

        migration_module.backfill_scope(_FakeApps(), None)

        with_phase.refresh_from_db()
        without_phase.refresh_from_db()
        plain_affectation.refresh_from_db()
        assert with_phase.scope == ConventionScope.PAR_ETAPE
        assert without_phase.scope == ConventionScope.CHANTIER_ENTIER
        assert plain_affectation.scope == ''


@pytest.mark.django_db
class TestConventionScopeHttpRoundTrip:
    def test_create_personnel_with_chantier_entier_convention(self, director_client, site):
        payload = _personnel_payload(first_name='Fatou', last_name='Camara')
        payload.update(_convention_management_data(total=1))
        payload.update({
            'convention-0-site': str(site.pk),
            'convention-0-name': 'Gardiennage',
            'convention-0-scope': ConventionScope.CHANTIER_ENTIER,
            'convention-0-convention_amount': '300.00',
        })
        response = director_client.post(reverse('personnel:personnel_create'), payload)
        assert response.status_code == 302, getattr(response, 'context', None) and response.context['form'].errors

        from personnel.models import Personnel
        new_personnel = Personnel.objects.get(first_name='Fatou', last_name='Camara')
        assignment = new_personnel.assignments.get()
        assert assignment.scope == ConventionScope.CHANTIER_ENTIER
        assert assignment.phase is None
        assert assignment.convention_amount == Decimal('300.00')
