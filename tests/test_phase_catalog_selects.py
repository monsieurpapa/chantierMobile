"""Catalogue des étapes in every "Étape" select (added 2026-10-20).

Every étape select (the étape form itself and every form with a `phase`
field) now offers, after the chantier's own étapes, the catalog étapes and
sous-étapes that chantier doesn't have yet. Picking one creates the
ProjectPhase on the chantier when the form is saved — and only then: an
invalid submission creates nothing. See projects/phase_fields.py."""
from decimal import Decimal

import pytest
from django.urls import reverse

from accounts.models import Cabinet
from chantiermobile.constants import PhaseCategory, TaskPriority
from projects.models import PhaseTemplate, ProjectPhase, Site
from projects.phase_fields import (
    CatalogPhaseChoiceField, catalog_entries_for_site, catalog_value,
)

# Names unlikely to collide with the seeded global catalog.
MAIN = 'Zz Catalogue Fondations'
SUB = 'Zz Semelles filantes'
SUB2 = 'Zz Longrines'


@pytest.fixture
def main_tpl(db):
    return PhaseTemplate.objects.create(cabinet=None, name=MAIN, category=PhaseCategory.GROS_OEUVRE, order=0)


@pytest.fixture
def sub_tpl(db, main_tpl):
    return PhaseTemplate.objects.create(
        cabinet=None, parent_template=main_tpl, name=SUB, category=PhaseCategory.GROS_OEUVRE, order=0,
    )


@pytest.fixture
def sub_tpl2(db, main_tpl):
    return PhaseTemplate.objects.create(
        cabinet=None, parent_template=main_tpl, name=SUB2, category=PhaseCategory.GROS_OEUVRE, order=1,
    )


def _option_values(field):
    values = []
    for value, label in field.choices:
        if isinstance(label, (list, tuple)):
            values.extend(str(v) for v, _l in label)
        else:
            values.append(str(value))
    return values


@pytest.mark.django_db
class TestCatalogEntries:
    def test_lists_main_etape_then_its_sub_etapes(self, site, main_tpl, sub_tpl):
        entries = [(t.pk, label) for t, label in catalog_entries_for_site(site)]
        assert (main_tpl.pk, MAIN) in entries
        assert (sub_tpl.pk, f'{MAIN} › {SUB}') in entries
        assert entries.index((main_tpl.pk, MAIN)) < entries.index((sub_tpl.pk, f'{MAIN} › {SUB}'))

    def test_excludes_etapes_the_chantier_already_has(self, site, main_tpl, sub_tpl, phase_factory):
        parent = phase_factory(site, name=MAIN.upper())  # case-insensitive match
        phase_factory(site, name=SUB, parent_phase=parent)
        ids = [t.pk for t, _label in catalog_entries_for_site(site)]
        assert main_tpl.pk not in ids
        assert sub_tpl.pk not in ids

    def test_top_level_only(self, site, main_tpl, sub_tpl):
        ids = [t.pk for t, _label in catalog_entries_for_site(site, top_level_only=True)]
        assert main_tpl.pk in ids
        assert sub_tpl.pk not in ids

    def test_other_cabinets_own_templates_are_not_offered(self, site, db):
        other = Cabinet.objects.create(name='Autre cabinet', address='x', tax_id='OTHER1')
        foreign = PhaseTemplate.objects.create(cabinet=other, name='Zz Étape privée', category='')
        assert foreign.pk not in [t.pk for t, _label in catalog_entries_for_site(site)]


@pytest.mark.django_db
class TestEveryPhaseSelectOffersTheCatalog:
    """Each form's `phase` select lists the catalog for its chantier."""

    def test_expense_form(self, site, main_tpl):
        from finance.forms import ExpenseForm
        form = ExpenseForm(data={'site': site.pk})
        assert isinstance(form.fields['phase'], CatalogPhaseChoiceField)
        assert catalog_value(site.pk, main_tpl.pk) in _option_values(form.fields['phase'])

    def test_caisse_transaction_form(self, site, main_tpl):
        from finance.forms import CaisseTransactionForm
        form = CaisseTransactionForm(data={'site': site.pk})
        assert catalog_value(site.pk, main_tpl.pk) in _option_values(form.fields['phase'])

    def test_payroll_list_form(self, site, main_tpl):
        from finance.forms import PayrollListForm
        form = PayrollListForm(data={'site': site.pk})
        assert catalog_value(site.pk, main_tpl.pk) in _option_values(form.fields['phase'])

    def test_material_request_item_form(self, site, main_tpl):
        from materials.forms import MaterialRequestItemForm
        form = MaterialRequestItemForm(data={'site': site.pk})
        assert catalog_value(site.pk, main_tpl.pk) in _option_values(form.fields['phase'])

    def test_dqe_line_form(self, site, main_tpl):
        from pricing.forms import DQELineForm
        form = DQELineForm(data={'site': site.pk})
        assert catalog_value(site.pk, main_tpl.pk) in _option_values(form.fields['phase'])

    def test_devis_line_form(self, site, main_tpl):
        from revenue.forms import DevisLineForm
        form = DevisLineForm(data={'site': site.pk})
        assert catalog_value(site.pk, main_tpl.pk) in _option_values(form.fields['phase'])

    def test_stock_movement_form(self, site, main_tpl):
        from procurement.forms import StockMovementForm
        from procurement.models import StockItem
        item = StockItem.objects.create(site=site, name='Ciment 50kg', unit='sac', quantity_on_hand=Decimal('10'))
        form = StockMovementForm(stock_item=item)
        assert catalog_value(site.pk, main_tpl.pk) in _option_values(form.fields['phase'])

    def test_task_form(self, site, main_tpl):
        from tasks.forms import TaskForm
        form = TaskForm(initial={'site': site})
        form.offer_phase_catalog(Site.objects.filter(pk=site.pk))
        assert catalog_value(site.pk, main_tpl.pk) in _option_values(form.fields['phase'])

    def test_convention_form(self, site, cabinet, main_tpl):
        from personnel.forms import ConventionForm
        form = ConventionForm(data={'site': site.pk}, cabinet=cabinet)
        assert catalog_value(site.pk, main_tpl.pk) in _option_values(form.fields['phase'])

    def test_evaluation_form_only_for_the_persons_chantiers(self, site, site_factory, cabinet, personnel, main_tpl):
        from personnel.forms import PersonnelEvaluationForm
        from personnel.models import SiteAssignment
        other_site = site_factory(name='Chantier sans affectation')
        SiteAssignment.objects.create(personnel=personnel, site=site, role='Ouvrier', start_date='2026-01-01', daily_rate=Decimal('10'))
        values = _option_values(PersonnelEvaluationForm(cabinet=cabinet, personnel=personnel).fields['phase'])
        assert catalog_value(site.pk, main_tpl.pk) in values
        assert catalog_value(other_site.pk, main_tpl.pk) not in values

    def test_plain_select_unchanged_when_nothing_left_in_catalog(self, site, phase, monkeypatch):
        """With no catalog entries, the select renders as before (flat)."""
        from finance.forms import PayrollListForm
        monkeypatch.setattr('projects.phase_fields.catalog_entries_for_site', lambda *a, **k: [])
        form = PayrollListForm(data={'site': site.pk})
        assert not any(isinstance(label, (list, tuple)) for _v, label in form.fields['phase'].choices)
        assert str(phase.pk) in _option_values(form.fields['phase'])


@pytest.mark.django_db
class TestPickingACatalogEtape:
    def test_valid_form_creates_the_etape_and_links_it(self, site, main_tpl):
        from finance.forms import PayrollListForm
        form = PayrollListForm(data={'site': site.pk, 'phase': catalog_value(site.pk, main_tpl.pk), 'notes': ''})
        assert form.is_valid(), form.errors
        payroll = form.save()
        created = ProjectPhase.objects.get(site=site, name=MAIN)
        assert payroll.phase == created
        assert created.category == PhaseCategory.GROS_OEUVRE
        assert created.parent_phase is None

    def test_catalog_sub_etape_also_creates_its_parent(self, site, main_tpl, sub_tpl):
        from finance.forms import PayrollListForm
        form = PayrollListForm(data={'site': site.pk, 'phase': catalog_value(site.pk, sub_tpl.pk), 'notes': ''})
        assert form.is_valid(), form.errors
        payroll = form.save()
        assert payroll.phase.name == SUB
        assert payroll.phase.parent_phase.name == MAIN
        assert ProjectPhase.objects.filter(site=site, name=MAIN).count() == 1

    def test_catalog_sub_etape_reuses_an_existing_parent(self, site, main_tpl, sub_tpl, phase_factory):
        from finance.forms import PayrollListForm
        parent = phase_factory(site, name=MAIN)
        form = PayrollListForm(data={'site': site.pk, 'phase': catalog_value(site.pk, sub_tpl.pk), 'notes': ''})
        assert form.is_valid(), form.errors
        assert form.save().phase.parent_phase == parent
        assert ProjectPhase.objects.filter(site=site, name=MAIN).count() == 1

    def test_invalid_form_creates_nothing(self, site, main_tpl):
        from finance.forms import ExpenseForm
        form = ExpenseForm(data={'site': site.pk, 'phase': catalog_value(site.pk, main_tpl.pk), 'amount': 'pas un montant'})
        assert not form.is_valid()
        assert not ProjectPhase.objects.filter(site=site, name=MAIN).exists()

    def test_catalog_value_for_another_chantier_is_rejected(self, site, site_factory, main_tpl):
        from finance.forms import PayrollListForm
        other_site = site_factory(name='Autre chantier')
        form = PayrollListForm(data={'site': site.pk, 'phase': catalog_value(other_site.pk, main_tpl.pk), 'notes': ''})
        assert not form.is_valid()
        assert 'phase' in form.errors
        assert not ProjectPhase.objects.filter(name=MAIN).exists()

    def test_other_cabinets_template_is_rejected(self, site):
        from finance.forms import PayrollListForm
        other = Cabinet.objects.create(name='Autre cabinet', address='x', tax_id='OTHER2')
        foreign = PhaseTemplate.objects.create(cabinet=other, name='Zz Étape privée', category='')
        form = PayrollListForm(data={'site': site.pk, 'phase': catalog_value(site.pk, foreign.pk), 'notes': ''})
        assert not form.is_valid()
        assert 'phase' in form.errors

    def test_existing_etapes_still_work(self, site, phase, main_tpl):
        from finance.forms import PayrollListForm
        form = PayrollListForm(data={'site': site.pk, 'phase': phase.pk, 'notes': ''})
        assert form.is_valid(), form.errors
        assert form.save().phase == phase

    def test_task_create_view(self, director_client, site, main_tpl):
        from tasks.models import Task
        response = director_client.post(reverse('tasks:task_create'), {
            'site': site.pk, 'title': 'Coffrage', 'priority': TaskPriority.NORMALE,
            'description': '', 'due_date': '', 'assigned_to': '',
            'phase': catalog_value(site.pk, main_tpl.pk),
        })
        assert response.status_code == 302
        assert Task.objects.get(title='Coffrage').phase == ProjectPhase.objects.get(site=site, name=MAIN)

    def test_evaluation_view(self, client, cabinet, site, personnel, main_tpl):
        from accounts.models import UserCabinetRole
        from chantiermobile.constants import ApprovalStatus, UserRoles
        from django.contrib.auth import get_user_model
        from personnel.models import PersonnelEvaluation, SiteAssignment
        SiteAssignment.objects.create(personnel=personnel, site=site, role='Ouvrier', start_date='2026-01-01', daily_rate=Decimal('10'))
        chief = get_user_model().objects.create_user(username='chief_cat', password='x')
        UserCabinetRole.objects.create(user=chief, cabinet=cabinet, role=UserRoles.CHIEF_ENGINEER, status=ApprovalStatus.APPROVED)
        client.force_login(chief)
        response = client.post(
            reverse('personnel:evaluation_create', kwargs={'unique_id': personnel.unique_id}),
            {'phase': catalog_value(site.pk, main_tpl.pk), 'note_chiffree': '15', 'mention_qualitative': '', 'observation': 'Bon travail.'},
        )
        assert response.status_code == 302, response.context and response.context['form'].errors
        assert PersonnelEvaluation.objects.get(personnel=personnel).phase.name == MAIN

    def test_other_errors_do_not_add_a_bogus_etape_error(self, cabinet, site, personnel, main_tpl):
        from personnel.forms import PersonnelEvaluationForm
        from personnel.models import SiteAssignment
        SiteAssignment.objects.create(personnel=personnel, site=site, role='Ouvrier', start_date='2026-01-01', daily_rate=Decimal('10'))
        form = PersonnelEvaluationForm(
            data={'phase': catalog_value(site.pk, main_tpl.pk), 'note_chiffree': '15', 'observation': ''},
            cabinet=cabinet, personnel=personnel,
        )
        assert not form.is_valid()
        assert 'observation' in form.errors
        assert 'phase' not in form.errors
        assert not ProjectPhase.objects.filter(site=site, name=MAIN).exists()

    def test_planning_submission_form_lists_catalog(self, director_client, site, main_tpl):
        response = director_client.get(reverse('projects:planning_submission_create', kwargs={'site_id': site.unique_id}))
        assert response.status_code == 200
        assert catalog_value(site.pk, main_tpl.pk).encode() in response.content


@pytest.mark.django_db
class TestSitePhasesEndpoint:
    def test_returns_own_etapes_then_catalog_with_group(self, director_client, site, phase, main_tpl):
        data = director_client.get(reverse('finance:site_phases_data'), {'site': site.pk}).json()['results']
        assert data[0] == {'id': phase.pk, 'text': phase.name}
        catalog = [r for r in data if r.get('group')]
        assert {'id': catalog_value(site.pk, main_tpl.pk), 'text': MAIN, 'group': 'Catalogue des étapes'} in catalog

    def test_variance_badge_endpoint_accepts_a_catalog_value(self, director_client, site, material, main_tpl):
        response = director_client.get(reverse('pricing:material_usage_comparison'), {
            'site': site.pk, 'phase': catalog_value(site.pk, main_tpl.pk), 'material': material.pk, 'quantity': '5',
        })
        assert response.status_code == 200
        assert response.json() == {'ok': False, 'reason': 'phase_not_found'}

    def test_catalog_entry_disappears_once_the_chantier_has_it(self, director_client, site, main_tpl):
        main_tpl.instantiate_for_site(site, include_subs=False)
        data = director_client.get(reverse('finance:site_phases_data'), {'site': site.pk}).json()['results']
        assert catalog_value(site.pk, main_tpl.pk) not in [r['id'] for r in data]


@pytest.mark.django_db
class TestPhaseCreateFromCatalog:
    def _url(self, site):
        return reverse('projects:phase_create', kwargs={'site_id': site.unique_id})

    def test_form_lists_catalog_etapes_and_sub_etapes(self, director_client, site, main_tpl, sub_tpl):
        response = director_client.get(self._url(site))
        assert response.status_code == 200
        values = [o['value'] for o in response.context['form'].catalog_options]
        assert str(main_tpl.pk) in values and str(sub_tpl.pk) in values

    def test_picking_a_main_etape_fills_name_and_category_and_adds_its_sub_etapes(
        self, director_client, site, main_tpl, sub_tpl, sub_tpl2,
    ):
        response = director_client.post(self._url(site), {
            'catalog_template': main_tpl.pk, 'include_sub_templates': 'on',
            'name': '', 'category': '', 'parent_phase': '', 'start_date': '', 'end_date': '',
        })
        assert response.status_code == 302
        main = ProjectPhase.objects.get(site=site, name=MAIN)
        assert main.category == PhaseCategory.GROS_OEUVRE
        assert set(main.sub_phases.values_list('name', flat=True)) == {SUB, SUB2}

    def test_sub_etapes_skipped_when_unchecked(self, director_client, site, main_tpl, sub_tpl):
        director_client.post(self._url(site), {
            'catalog_template': main_tpl.pk, 'name': '', 'category': '', 'parent_phase': '',
            'start_date': '', 'end_date': '',
        })
        assert not ProjectPhase.objects.get(site=site, name=MAIN).sub_phases.exists()

    def test_picking_a_sub_etape_creates_its_parent(self, director_client, site, main_tpl, sub_tpl):
        response = director_client.post(self._url(site), {
            'catalog_template': sub_tpl.pk, 'name': '', 'category': '', 'parent_phase': '',
            'start_date': '', 'end_date': '',
        })
        assert response.status_code == 302
        sub = ProjectPhase.objects.get(site=site, name=SUB)
        assert sub.parent_phase.name == MAIN

    def test_name_can_be_changed_after_picking(self, director_client, site, main_tpl):
        director_client.post(self._url(site), {
            'catalog_template': main_tpl.pk, 'name': 'Fondations bloc A', 'category': '', 'parent_phase': '',
            'start_date': '', 'end_date': '',
        })
        assert ProjectPhase.objects.filter(site=site, name='Fondations bloc A').exists()

    def test_parent_select_offers_catalog_main_etapes(self, director_client, site, main_tpl):
        response = director_client.post(self._url(site), {
            'name': 'Zz Béton de propreté', 'category': '', 'start_date': '', 'end_date': '',
            'parent_phase': catalog_value(site.pk, main_tpl.pk),
        })
        assert response.status_code == 302
        child = ProjectPhase.objects.get(site=site, name='Zz Béton de propreté')
        assert child.parent_phase.name == MAIN

    def test_free_text_etape_still_works(self, director_client, site):
        response = director_client.post(self._url(site), {
            'name': 'Étape libre', 'category': '', 'parent_phase': '', 'start_date': '', 'end_date': '',
        })
        assert response.status_code == 302
        assert ProjectPhase.objects.filter(site=site, name='Étape libre').exists()

    def test_needs_a_name_or_a_catalog_etape(self, director_client, site):
        count = ProjectPhase.objects.filter(site=site).count()
        response = director_client.post(self._url(site), {
            'name': '', 'category': '', 'parent_phase': '', 'start_date': '', 'end_date': '',
        })
        assert response.status_code == 200
        assert 'name' in response.context['form'].errors
        assert ProjectPhase.objects.filter(site=site).count() == count

    def test_edit_form_has_no_catalog_picker(self, director_client, site, phase):
        response = director_client.get(reverse('projects:phase_update', kwargs={'unique_id': phase.unique_id}))
        assert response.status_code == 200
        assert 'catalog_template' not in response.context['form'].fields
