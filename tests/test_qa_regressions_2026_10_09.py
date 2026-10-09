"""Regression tests for bugs found by /qa on 2026-10-09.
Report: .gstack/qa-reports/qa-report-localhost-2026-10-09.md

ISSUE-001 — 'Structure du chantier' had no level to edit for a site that
            predates SiteLevel (or was created outside the Site form).
ISSUE-002 — a step (phase) picked on a NEW DQE line / état de besoin item
            was rejected: the row form's phase queryset was none() on a
            create POST.
ISSUE-003 — a blank first DQE line blocked saving even when another line
            held the data (min_num made row 0 mandatory).
ISSUE-004 — the source DQE picked on a NEW devis was rejected: source_dqe
            queryset was none() on a create POST.
"""
import pytest
from datetime import date
from decimal import Decimal
from django.urls import reverse

from chantiermobile.constants import PriceItemType, WorkCategory
from materials.forms import MaterialRequestItemFormSet
from materials.models import MaterialRequest
from pricing.forms import DQELineFormSet
from pricing.models import DQE, PriceLibraryItem
from projects.models import SiteLevel
from revenue.forms import DevisForm


def _management(prefix, total, initial=0):
    return {
        f'{prefix}-TOTAL_FORMS': str(total),
        f'{prefix}-INITIAL_FORMS': str(initial),
        f'{prefix}-MIN_NUM_FORMS': '1',
        f'{prefix}-MAX_NUM_FORMS': '1000',
    }


@pytest.fixture
def price_item(db, cabinet):
    return PriceLibraryItem.objects.create(
        cabinet=cabinet, code='OUV-BETON-QA', designation='Béton dosé 350',
        item_type=PriceItemType.WORK_ITEM, work_category=WorkCategory.BETON,
        unit='m3', unit_price=Decimal('180.00'),
    )


def _dqe_line(prefix, i, item=None, phase=None, quantity='', unit_price=''):
    return {
        f'{prefix}-{i}-price_item': str(item.pk) if item else '',
        f'{prefix}-{i}-phase': str(phase.pk) if phase else '',
        f'{prefix}-{i}-designation': '',
        f'{prefix}-{i}-quantity': quantity,
        f'{prefix}-{i}-unit_price': unit_price,
    }


@pytest.mark.django_db
class TestIssue001StructurePageSyncsLevels:
    def test_opening_structure_page_creates_missing_levels(self, director_client, site):
        site.floor_count = 2
        site.basement_count = 1
        site.save(update_fields=['floor_count', 'basement_count'])
        assert not site.levels.exists()  # never went through the Site form

        response = director_client.get(
            reverse('projects:site_structure_update', kwargs={'unique_id': site.unique_id}))

        assert response.status_code == 200
        indexes = list(site.levels.order_by('level_index').values_list('level_index', flat=True))
        assert indexes == [-1, 0, 1, 2]
        assert response.context['levels_formset'].total_form_count() == 4

    def test_reopening_does_not_duplicate_levels(self, director_client, site):
        url = reverse('projects:site_structure_update', kwargs={'unique_id': site.unique_id})
        director_client.get(url)
        director_client.get(url)
        assert SiteLevel.all_objects.filter(site=site).count() == 1


@pytest.mark.django_db
class TestIssue002PhaseAcceptedOnCreate:
    def test_new_dqe_line_accepts_phase_of_submitted_site(self, site, phase, price_item):
        data = {'site': str(site.pk), **_management('lines', 1),
                **_dqe_line('lines', 0, price_item, phase, '10', '180')}
        formset = DQELineFormSet(data, instance=DQE(), prefix='lines')
        assert formset.is_valid(), formset.errors
        assert formset.forms[0].cleaned_data['phase'] == phase

    def test_new_dqe_line_rejects_phase_of_another_site(self, site, site_factory, phase_factory, price_item):
        other_phase = phase_factory(site_factory(name='Autre chantier'))
        data = {'site': str(site.pk), **_management('lines', 1),
                **_dqe_line('lines', 0, price_item, other_phase, '10', '180')}
        formset = DQELineFormSet(data, instance=DQE(), prefix='lines')
        assert not formset.is_valid()
        assert 'phase' in formset.forms[0].errors

    def test_new_material_request_item_accepts_phase_of_submitted_site(self, site, phase, material):
        data = {
            'site': str(site.pk), **_management('items', 1),
            'items-0-material': str(material.pk), 'items-0-material_name': '',
            'items-0-phase': str(phase.pk), 'items-0-quantity': '100', 'items-0-notes': '',
        }
        formset = MaterialRequestItemFormSet(data, instance=MaterialRequest(), prefix='items')
        assert formset.is_valid(), formset.errors
        assert formset.forms[0].cleaned_data['phase'] == phase


@pytest.mark.django_db
class TestIssue003BlankDqeRowAllowed:
    def test_blank_first_row_with_filled_second_row_is_valid(self, site, price_item):
        data = {'site': str(site.pk), **_management('lines', 2),
                **_dqe_line('lines', 0),
                **_dqe_line('lines', 1, price_item, None, '195.34', '180')}
        formset = DQELineFormSet(data, instance=DQE(), prefix='lines')
        assert formset.is_valid(), formset.errors

    def test_all_rows_blank_still_requires_one_line(self, site):
        data = {'site': str(site.pk), **_management('lines', 2),
                **_dqe_line('lines', 0), **_dqe_line('lines', 1)}
        formset = DQELineFormSet(data, instance=DQE(), prefix='lines')
        assert not formset.is_valid()
        assert formset.non_form_errors()


@pytest.mark.django_db
class TestIssue004SourceDqeAcceptedOnCreate:
    def test_new_devis_accepts_dqe_of_submitted_site(self, cabinet, site):
        dqe = DQE.objects.create(cabinet=cabinet, site=site, reference='DQE-QA', title='QA')
        form = DevisForm(data={
            'site': str(site.pk), 'devis_number': 'DEV-QA', 'source_dqe': str(dqe.pk),
            'client_name': 'Client QA', 'issue_date': date.today().isoformat(),
        })
        form.is_valid()
        assert 'source_dqe' not in form.errors

    def test_new_devis_rejects_dqe_of_another_site(self, cabinet, site, site_factory):
        other = site_factory(name='Autre chantier')
        dqe = DQE.objects.create(cabinet=cabinet, site=other, reference='DQE-OTHER', title='Autre')
        form = DevisForm(data={
            'site': str(site.pk), 'devis_number': 'DEV-QA', 'source_dqe': str(dqe.pk),
            'client_name': 'Client QA', 'issue_date': date.today().isoformat(),
        })
        assert not form.is_valid()
        assert 'source_dqe' in form.errors
