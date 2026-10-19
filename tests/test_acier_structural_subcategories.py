"""Tests for the 2026-10-19 ACIER structural sub-category extension
(point 4 of the lost-commits redo list): WorkCategory gains
ACIER_SEMELLES/ACIER_POTEAUX/ACIER_POUTRES/ACIER_DALLES, each with its
own global-default MaterialConsumptionRatio (0008_seed_acier_structural_
ratios), so DQELine.exploded_requirements() no longer sums every
structural element's reinforcement under one blended ACIER ratio —
semelles, poteaux, poutres and dalles reinforce at genuinely different
kg-of-acier-per-m³-of-béton densities.

Generic ACIER (1:1 kg/kg, seeded by 0004) stays available unchanged for
existing/legacy items — this extension is additive, not a replacement.

This suite runs with --nomigrations (see pytest.ini), so RunPython seed
migrations never execute on their own against the test database —
tests that need their seeded data re-run the real seed_ratios()
functions directly against the real models, the same pattern already
used by tests/test_stock_and_material_workflow.py's
TestValidatedStatusMigratedForward for materials/migrations/0012.
"""
from decimal import Decimal

import pytest

from pricing.models import PriceLibraryItem, DQE, DQELine, MaterialConsumptionRatio
from materials.models import Material
from chantiermobile.constants import PriceItemType, WorkCategory, DQEStatus


class _FakeApps:
    """Minimal stand-in for the historical `apps` migrations receive —
    --nomigrations means there's no real historical state to fetch, so
    this just hands the migration function the real, current models."""
    _models = {
        ('materials', 'Material'): Material,
        ('pricing', 'MaterialConsumptionRatio'): MaterialConsumptionRatio,
    }

    def get_model(self, app_label, model_name):
        return self._models[(app_label, model_name)]


def _run_seed_migration(dotted_module_name):
    import importlib
    migration_module = importlib.import_module(dotted_module_name)
    migration_module.seed_ratios(_FakeApps(), None)


@pytest.fixture
def dqe(db, cabinet, site):
    return DQE.objects.create(cabinet=cabinet, site=site, reference='DQE-ACIER-001', title='Test DQE', status=DQEStatus.DRAFT)


@pytest.fixture
def with_acier_structural_ratios(db):
    """Re-runs 0004 (generic ACIER + the shared Material row) then 0008
    (the four structural sub-category ratios) so a test sees exactly
    what a real deploy's database would have after both migrations."""
    _run_seed_migration('pricing.migrations.0004_seed_material_consumption_ratios')
    _run_seed_migration('pricing.migrations.0008_seed_acier_structural_ratios')


def _work_item(cabinet, work_category, code):
    return PriceLibraryItem.objects.create(
        cabinet=cabinet, code=code, designation=f'Ouvrage {code}',
        item_type=PriceItemType.WORK_ITEM, work_category=work_category,
        unit='m3', unit_price=Decimal('150.00'),
    )


@pytest.mark.django_db
class TestAcierStructuralSubcategoriesExist:
    def test_new_categories_are_valid_choices(self):
        values = {choice.value for choice in WorkCategory}
        assert {'ACIER_SEMELLES', 'ACIER_POTEAUX', 'ACIER_POUTRES', 'ACIER_DALLES'} <= values
        # Generic ACIER must still be there — this is additive.
        assert 'ACIER' in values

    def test_price_library_item_accepts_a_structural_subcategory(self, cabinet):
        item = _work_item(cabinet, WorkCategory.ACIER_POUTRES, 'OUV-ACIER-POUTRE')
        item.full_clean()
        assert item.work_category == WorkCategory.ACIER_POUTRES


@pytest.mark.django_db
class TestSeededAcierStructuralRatios:
    @pytest.mark.parametrize('category,expected_ratio', [
        ('ACIER_SEMELLES', Decimal('50.0000')),
        ('ACIER_POTEAUX', Decimal('150.0000')),
        ('ACIER_POUTRES', Decimal('200.0000')),
        ('ACIER_DALLES', Decimal('60.0000')),
    ])
    def test_each_subcategory_has_its_own_global_default_ratio(self, with_acier_structural_ratios, category, expected_ratio):
        acier = Material.objects.get(name='Acier / armatures')
        ratio = MaterialConsumptionRatio.objects.get(cabinet=None, work_category=category, material=acier)
        assert ratio.ratio == expected_ratio

    def test_generic_acier_ratio_is_untouched(self, with_acier_structural_ratios):
        """The pre-existing generic ACIER (1:1 kg/kg) ratio from
        0004_seed_material_consumption_ratios must still be exactly
        what it was — this extension doesn't replace it."""
        acier = Material.objects.get(name='Acier / armatures')
        ratio = MaterialConsumptionRatio.objects.get(cabinet=None, work_category=WorkCategory.ACIER, material=acier)
        assert ratio.ratio == Decimal('1.0000')

    def test_both_seed_migrations_reuse_the_same_material_row(self, with_acier_structural_ratios):
        """0008 must not create a second, duplicate 'Acier / armatures'
        Material row alongside 0004's."""
        assert Material.objects.filter(name='Acier / armatures').count() == 1


@pytest.mark.django_db
class TestExplodedRequirementsDoNotBlendStructuralElements:
    """Exercises exploded_requirements() against locally-created ratios
    (same convention as test_devis_material_comparison.py's ciment_ratio
    fixture) — independent of migration machinery, so this correctness
    guarantee holds regardless of whether any seed migration has run."""

    def test_semelles_and_poteaux_explode_at_their_own_density(self, cabinet, dqe):
        """The core correctness guarantee: two different structural
        elements, same material, must NOT be summed under one ratio —
        each DQELine explodes using only its own work_category's rate."""
        acier = Material.objects.create(name='Acier (test)', unit='kg')
        MaterialConsumptionRatio.objects.create(cabinet=None, work_category=WorkCategory.ACIER_SEMELLES, material=acier, ratio=Decimal('50.0000'), ratio_unit='kg/m3')
        MaterialConsumptionRatio.objects.create(cabinet=None, work_category=WorkCategory.ACIER_POTEAUX, material=acier, ratio=Decimal('150.0000'), ratio_unit='kg/m3')

        semelles_item = _work_item(cabinet, WorkCategory.ACIER_SEMELLES, 'OUV-SEM')
        poteaux_item = _work_item(cabinet, WorkCategory.ACIER_POTEAUX, 'OUV-POT')

        semelles_line = DQELine.objects.create(
            dqe=dqe, price_item=semelles_item, designation='Semelles bloc A',
            quantity=Decimal('10'), unit_price=semelles_item.unit_price,
        )
        poteaux_line = DQELine.objects.create(
            dqe=dqe, price_item=poteaux_item, designation='Poteaux bloc A',
            quantity=Decimal('10'), unit_price=poteaux_item.unit_price,
        )

        semelles_exploded = semelles_line.exploded_requirements()
        poteaux_exploded = poteaux_line.exploded_requirements()

        assert semelles_exploded[acier.id] == Decimal('10') * Decimal('50.0000')
        assert poteaux_exploded[acier.id] == Decimal('10') * Decimal('150.0000')
        # Not summed together, and not equal to each other.
        assert semelles_exploded[acier.id] != poteaux_exploded[acier.id]

    def test_dalles_explode_at_their_own_density(self, cabinet, dqe):
        acier = Material.objects.create(name='Acier (test 2)', unit='kg')
        MaterialConsumptionRatio.objects.create(cabinet=None, work_category=WorkCategory.ACIER_DALLES, material=acier, ratio=Decimal('60.0000'), ratio_unit='kg/m3')
        item = _work_item(cabinet, WorkCategory.ACIER_DALLES, 'OUV-DALLE')
        line = DQELine.objects.create(dqe=dqe, price_item=item, designation='Dalle RDC', quantity=Decimal('20'), unit_price=item.unit_price)
        assert line.exploded_requirements()[acier.id] == Decimal('20') * Decimal('60.0000')

    def test_cabinet_override_still_takes_precedence_over_subcategory_default(self, cabinet, dqe):
        """Mirrors the existing override-preference guarantee already
        tested for BETON/MACONNERIE — a cabinet-specific row for the
        same (work_category, material) wins over the global default."""
        acier = Material.objects.create(name='Acier (test 3)', unit='kg')
        MaterialConsumptionRatio.objects.create(cabinet=None, work_category=WorkCategory.ACIER_POUTRES, material=acier, ratio=Decimal('200.0000'), ratio_unit='kg/m3')
        MaterialConsumptionRatio.objects.create(
            cabinet=cabinet, work_category=WorkCategory.ACIER_POUTRES, material=acier,
            ratio=Decimal('220.0000'), ratio_unit='kg/m3',
        )
        item = _work_item(cabinet, WorkCategory.ACIER_POUTRES, 'OUV-POUTRE-OVERRIDE')
        line = DQELine.objects.create(dqe=dqe, price_item=item, designation='Poutres surdimensionnées', quantity=Decimal('5'), unit_price=item.unit_price)

        exploded = line.exploded_requirements()
        assert exploded[acier.id] == Decimal('5') * Decimal('220.0000')
