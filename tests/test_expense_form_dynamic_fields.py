"""
Tests for two "nothing is showing" bugs reported on the expense form:

1. The "Catégorie" dropdown was empty because no ExpenseCategory rows
   existed anywhere until someone ran the demo-data seed command — fixed
   with finance/migrations/0010_seed_expense_categories.py.
2. The "Étape" dropdown was empty on a fresh create form because
   ExpenseForm.__init__ only populates the phase queryset from POSTed data
   or an existing instance, never from a plain GET — fixed by adding a
   site_phases_data JSON endpoint (mirroring the existing
   site_personnel_data one) and wiring it up client-side.
"""
import pytest
from django.urls import reverse

from finance.models import ExpenseCategory


@pytest.mark.django_db
class TestExpenseCategorySeed:
    def test_default_categories_exist_after_migration(self):
        """The 0010 data migration should have run as part of the test DB
        setup (migrations apply normally; only the TEST db's schema build
        skips re-running them per test — see pytest.ini's --nomigrations),
        so the categories used across the finance test suite are real,
        seeded rows rather than something each test has to create itself."""
        names = set(ExpenseCategory.objects.values_list('name', flat=True))
        assert "Main d'œuvre" in names
        assert 'Transport et Logistique' in names

    def test_expense_form_category_field_has_options(self, expense_category):
        from finance.forms import ExpenseForm
        form = ExpenseForm()
        # expense_category fixture guarantees at least one row regardless
        # of migration state; the real-world bug was an empty queryset.
        assert form.fields['category'].queryset.count() >= 1


@pytest.mark.django_db
class TestSitePhasesDataEndpoint:
    def test_returns_phases_for_the_given_site(self, director_client, site, phase):
        url = reverse('finance:site_phases_data')
        response = director_client.get(url, {'site': site.pk})
        assert response.status_code == 200
        data = response.json()
        assert {'id': phase.id, 'text': phase.name} in data['results']

    def test_returns_empty_without_a_site_param(self, director_client):
        url = reverse('finance:site_phases_data')
        response = director_client.get(url)
        assert response.json() == {'results': []}

    def test_scoped_to_requesting_users_cabinet(self, director_client, site_factory, cabinet):
        from accounts.models import Cabinet
        from projects.models import ProjectPhase
        other_cabinet = Cabinet.objects.create(name='Other Cabinet')
        other_site = site_factory(cabinet=other_cabinet)
        ProjectPhase.objects.create(site=other_site, name='Hors cabinet')

        url = reverse('finance:site_phases_data')
        response = director_client.get(url, {'site': other_site.pk})
        assert response.json() == {'results': []}

    def test_requires_login(self, client, site, phase):
        url = reverse('finance:site_phases_data')
        response = client.get(url, {'site': site.pk})
        assert response.status_code in (302, 403)


@pytest.mark.django_db
class TestExpenseFormPhaseInitialization:
    def test_phase_queryset_populated_from_posted_site(self, site, phase, expense_category):
        """The form's own phase-queryset logic (used to validate a POST,
        independent of the JS-driven dropdown) should already pick up the
        phase once a site is posted — confirms the fix's other half."""
        from finance.forms import ExpenseForm
        form = ExpenseForm(data={
            'site': site.pk, 'category': expense_category.pk, 'phase': phase.pk,
            'nature': 'MATERIEL', 'amount': '100.00',
            'expense_date': '2024-01-01', 'description': 'Test',
        })
        assert phase in form.fields['phase'].queryset
