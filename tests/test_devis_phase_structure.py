"""Tests for the 2026-10-19 devis étape/sous-étape structure feature:
`DevisLine.phase` + `Devis.lines_grouped_by_phase()` — lets a devis be
presented DPGF-style (lots/postes, with subtotals) by étape/sous-étape,
mirroring the one-level-deep `ProjectPhase` model already used by DQE, so
a devis and its source DQE read the same way étape by étape."""
from datetime import date
from decimal import Decimal

import pytest

from revenue.forms import DevisLineFormSet
from revenue.models import Devis, DevisLine


def _management_data(prefix, total, initial=0):
    return {
        f'{prefix}-TOTAL_FORMS': str(total),
        f'{prefix}-INITIAL_FORMS': str(initial),
        f'{prefix}-MIN_NUM_FORMS': '0',
        f'{prefix}-MAX_NUM_FORMS': '1000',
    }


@pytest.fixture
def devis(db, site):
    return Devis.objects.create(
        site=site, devis_number='DEV-PHASE-001', client_name='Client Test',
        issue_date=date.today(),
    )


@pytest.mark.django_db
class TestLinesGroupedByPhase:
    def test_no_lines_returns_empty_list(self, devis):
        assert devis.lines_grouped_by_phase() == []

    def test_lines_with_no_phase_land_in_one_unassigned_group(self, devis):
        DevisLine.objects.create(devis=devis, order=1, designation='A', unit='u', quantity=10, unit_price_ht=10)
        DevisLine.objects.create(devis=devis, order=2, designation='B', unit='u', quantity=10, unit_price_ht=10)

        groups = devis.lines_grouped_by_phase()
        assert len(groups) == 1
        assert groups[0]['phase'] is None
        assert [l.designation for l in groups[0]['lines']] == ['A', 'B']
        assert groups[0]['subtotal'] == Decimal('200.00')
        assert groups[0]['subtotal_with_children'] == Decimal('200.00')
        assert groups[0]['sub_groups'] == []

    def test_lines_under_same_top_level_phase_grouped_with_subtotal(self, devis, phase_factory):
        fondations = phase_factory(devis.site, name='Fondations')
        DevisLine.objects.create(devis=devis, order=1, phase=fondations, designation='A', unit='u', quantity=5, unit_price_ht=100)
        DevisLine.objects.create(devis=devis, order=2, phase=fondations, designation='B', unit='u', quantity=5, unit_price_ht=100)

        groups = devis.lines_grouped_by_phase()
        assert len(groups) == 1
        assert groups[0]['phase'] == fondations
        assert [l.designation for l in groups[0]['lines']] == ['A', 'B']
        assert groups[0]['subtotal'] == Decimal('1000.00')
        assert groups[0]['subtotal_with_children'] == groups[0]['subtotal']
        assert groups[0]['sub_groups'] == []

    def test_sub_phase_lines_nest_under_their_parent_with_own_subtotal(self, devis, phase_factory):
        gros_oeuvre = phase_factory(devis.site, name='Gros œuvre')
        semelles = phase_factory(devis.site, name='Semelles', parent_phase=gros_oeuvre)
        DevisLine.objects.create(devis=devis, order=1, phase=gros_oeuvre, designation='Direct', unit='u', quantity=10, unit_price_ht=100)
        DevisLine.objects.create(devis=devis, order=2, phase=semelles, designation='Sous A', unit='u', quantity=5, unit_price_ht=50)
        DevisLine.objects.create(devis=devis, order=3, phase=semelles, designation='Sous B', unit='u', quantity=5, unit_price_ht=50)

        groups = devis.lines_grouped_by_phase()
        assert len(groups) == 1
        top = groups[0]
        assert top['phase'] == gros_oeuvre
        assert top['subtotal'] == Decimal('1000.00')
        assert len(top['sub_groups']) == 1
        sub = top['sub_groups'][0]
        assert sub['phase'] == semelles
        assert sub['subtotal'] == Decimal('500.00')
        assert top['subtotal_with_children'] == top['subtotal'] + sub['subtotal']
        assert top['subtotal_with_children'] == Decimal('1500.00')

    def test_unassigned_group_comes_after_phase_groups(self, devis, phase_factory):
        fondations = phase_factory(devis.site, name='Fondations')
        DevisLine.objects.create(devis=devis, order=1, phase=fondations, designation='A', unit='u', quantity=1, unit_price_ht=100)
        DevisLine.objects.create(devis=devis, order=2, designation='B', unit='u', quantity=1, unit_price_ht=50)

        groups = devis.lines_grouped_by_phase()
        assert len(groups) == 2
        assert groups[0]['phase'] == fondations
        assert groups[-1]['phase'] is None

    def test_total_across_groups_matches_devis_total_ht(self, devis, phase_factory):
        gros_oeuvre = phase_factory(devis.site, name='Gros œuvre')
        semelles = phase_factory(devis.site, name='Semelles', parent_phase=gros_oeuvre)
        DevisLine.objects.create(devis=devis, order=1, phase=gros_oeuvre, designation='Direct', unit='u', quantity=10, unit_price_ht=100)
        DevisLine.objects.create(devis=devis, order=2, phase=semelles, designation='Sous', unit='u', quantity=4, unit_price_ht=100)
        DevisLine.objects.create(devis=devis, order=3, designation='Hors étape', unit='u', quantity=1, unit_price_ht=50)

        groups = devis.lines_grouped_by_phase()
        grand_total = sum(
            (g['subtotal_with_children'] if g['phase'] else g['subtotal']) for g in groups
        )
        assert grand_total == devis.total_ht
        assert grand_total == Decimal('1450.00')


@pytest.mark.django_db
class TestPhaseAcceptedOnDevisCreate:
    """DevisLineForm's `phase` queryset is scoped to the parent devis'
    submitted `site` (see DevisLineForm.__init__) — a brand-new devis
    (no pk yet) must still accept a phase of the site being submitted
    alongside it, and reject one from any other site."""

    def test_new_devis_line_accepts_phase_of_submitted_site(self, db, site, phase_factory):
        phase = phase_factory(site, name='Fondations')
        data = {'site': str(site.pk)}
        data.update(_management_data('lines', total=1))
        data.update({
            'lines-0-phase': str(phase.pk),
            'lines-0-designation': 'Terrassement',
            'lines-0-unit': 'm3',
            'lines-0-quantity': '10',
            'lines-0-unit_price_ht': '100',
            'lines-0-order': '1',
        })
        formset = DevisLineFormSet(data, instance=Devis(), prefix='lines')
        assert formset.is_valid(), formset.errors

    def test_new_devis_line_rejects_phase_of_another_site(self, db, site, site_factory, phase_factory):
        other_site = site_factory(name='Autre Chantier')
        other_phase = phase_factory(other_site, name='Fondations')
        data = {'site': str(site.pk)}
        data.update(_management_data('lines', total=1))
        data.update({
            'lines-0-phase': str(other_phase.pk),
            'lines-0-designation': 'Terrassement',
            'lines-0-unit': 'm3',
            'lines-0-quantity': '10',
            'lines-0-unit_price_ht': '100',
            'lines-0-order': '1',
        })
        formset = DevisLineFormSet(data, instance=Devis(), prefix='lines')
        assert not formset.is_valid()
        assert 'phase' in formset.forms[0].errors
