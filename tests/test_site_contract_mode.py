"""Tests for the 2026-10-07 "contract mode" feature: each Site is created
with a `contract_mode` (pré-établi dès la création, changeable later by a
director) that determines which of the Personnel/Materials/Finance tabs
are available, via `CONTRACT_MODE_MODULES` / `Site.get_enabled_modules()`
/ `Site.has_module()`.
"""
import pytest
from django.urls import reverse

from chantiermobile.constants import ContractMode, CONTRACT_MODE_MODULES


@pytest.mark.django_db
class TestContractModeModules:
    @pytest.mark.parametrize('mode,expected', [
        (ContractMode.CLE_EN_MAIN, {'personnel', 'materials', 'finance'}),
        (ContractMode.LIVRAISON_ETAPES, {'personnel', 'materials', 'finance'}),
        (ContractMode.MAIN_OEUVRE_SEULEMENT, {'personnel', 'finance'}),
        (ContractMode.SUIVI_SEULEMENT, set()),
    ])
    def test_get_enabled_modules_per_mode(self, site_factory, mode, expected):
        site = site_factory(contract_mode=mode)
        assert site.get_enabled_modules() == expected

    def test_has_module_true_for_enabled(self, site_factory):
        site = site_factory(contract_mode=ContractMode.MAIN_OEUVRE_SEULEMENT)
        assert site.has_module('personnel') is True
        assert site.has_module('finance') is True

    def test_has_module_false_for_disabled(self, site_factory):
        site = site_factory(contract_mode=ContractMode.MAIN_OEUVRE_SEULEMENT)
        assert site.has_module('materials') is False

    def test_suivi_seulement_disables_everything(self, site_factory):
        site = site_factory(contract_mode=ContractMode.SUIVI_SEULEMENT)
        assert site.has_module('personnel') is False
        assert site.has_module('materials') is False
        assert site.has_module('finance') is False

    def test_default_contract_mode_is_cle_en_main(self, site_factory):
        site = site_factory()
        assert site.contract_mode == ContractMode.CLE_EN_MAIN
        assert site.get_enabled_modules() == {'personnel', 'materials', 'finance'}

    def test_unrecognized_mode_fails_open(self, site_factory):
        site = site_factory()
        site.contract_mode = 'SOME_FUTURE_MODE_NOT_IN_DICT'
        assert site.get_enabled_modules() == {'personnel', 'materials', 'finance'}

    def test_all_contract_mode_values_covered_by_dict(self):
        for mode in ContractMode.values:
            assert mode in CONTRACT_MODE_MODULES


@pytest.mark.django_db
class TestSiteFormContractMode:
    def test_create_site_defaults_to_cle_en_main(self, director_client, cabinet):
        from projects.models import Site
        response = director_client.post(reverse('projects:site_create'), {
            'name': 'Chantier Test Avenue', 'location': 'Kinshasa',
            'status': 'PLANNING', 'contract_mode': ContractMode.CLE_EN_MAIN,
            'start_date': '2026-10-07', 'expected_end_date': '2027-01-07',
        })
        assert response.status_code == 302
        site = Site.objects.get(name='Chantier Test Avenue')
        assert site.contract_mode == ContractMode.CLE_EN_MAIN

    def test_create_site_with_suivi_seulement(self, director_client):
        from projects.models import Site
        response = director_client.post(reverse('projects:site_create'), {
            'name': 'Chantier Suivi', 'location': 'Kinshasa',
            'status': 'PLANNING', 'contract_mode': ContractMode.SUIVI_SEULEMENT,
            'start_date': '2026-10-07', 'expected_end_date': '2027-01-07',
        })
        assert response.status_code == 302
        site = Site.objects.get(name='Chantier Suivi')
        assert site.contract_mode == ContractMode.SUIVI_SEULEMENT

    def test_contract_mode_changeable_by_director(self, director_client, site):
        from projects.models import Site
        assert site.contract_mode == ContractMode.CLE_EN_MAIN
        response = director_client.post(
            reverse('projects:site_update', kwargs={'unique_id': site.unique_id}),
            {
                'name': site.name, 'location': site.location, 'status': site.status,
                'contract_mode': ContractMode.MAIN_OEUVRE_SEULEMENT,
                'start_date': site.start_date, 'expected_end_date': site.expected_end_date,
            },
        )
        assert response.status_code == 302
        site.refresh_from_db()
        assert site.contract_mode == ContractMode.MAIN_OEUVRE_SEULEMENT


@pytest.mark.django_db
class TestSiteDetailTabGating:
    def test_cle_en_main_shows_all_tabs(self, director_client, site_factory):
        site = site_factory(contract_mode=ContractMode.CLE_EN_MAIN)
        response = director_client.get(reverse('projects:site_detail', kwargs={'unique_id': site.unique_id}))
        content = response.content.decode()
        assert 'id="personnel-tab"' in content
        assert 'id="materials-tab"' in content
        assert 'id="finance-tab"' in content
        assert 'Non disponible pour ce type de contrat' not in content

    def test_suivi_seulement_hides_all_tabs(self, director_client, site_factory):
        site = site_factory(contract_mode=ContractMode.SUIVI_SEULEMENT)
        response = director_client.get(reverse('projects:site_detail', kwargs={'unique_id': site.unique_id}))
        content = response.content.decode()
        assert 'id="personnel-tab"' not in content
        assert 'id="materials-tab"' not in content
        assert 'id="finance-tab"' not in content

    def test_main_oeuvre_seulement_hides_only_materials(self, director_client, site_factory):
        site = site_factory(contract_mode=ContractMode.MAIN_OEUVRE_SEULEMENT)
        response = director_client.get(reverse('projects:site_detail', kwargs={'unique_id': site.unique_id}))
        content = response.content.decode()
        assert 'id="personnel-tab"' in content
        assert 'id="materials-tab"' not in content
        assert 'id="finance-tab"' in content

    def test_enabled_modules_in_context(self, director_client, site_factory):
        site = site_factory(contract_mode=ContractMode.MAIN_OEUVRE_SEULEMENT)
        response = director_client.get(reverse('projects:site_detail', kwargs={'unique_id': site.unique_id}))
        assert response.context['enabled_modules'] == {'personnel', 'finance'}
