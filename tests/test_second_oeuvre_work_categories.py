"""Tests for the 2026-10-19 second œuvre WorkCategory extension (point 2
of the lost-commits redo list): WorkCategory gains PLOMBERIE/ELECTRICITE/
MENUISERIE/PEINTURE/REVETEMENTS, and the two of those with a
well-established generic BTP ratio (PEINTURE, REVETEMENTS) get a
global-default MaterialConsumptionRatio seeded via
0006_seed_second_oeuvre_ratios — so a cabinet's WORK_ITEM price-library
items in those categories explode into material requirements out of the
box, exactly like BETON/ACIER/COFFRAGE/MACONNERIE already do.

PLOMBERIE/ELECTRICITE/MENUISERIE are deliberately left unseeded (see
WorkCategory's own docstring) — a single generic ratio would be
misleading for fixture-count/cable-run/carpentry-dimension pricing, so
those categories exist for a cabinet's own ratio rows, not a shipped
default.

This suite runs with --nomigrations (see pytest.ini), so RunPython seed
migrations never execute on their own against the test database —
TestSeededSecondOeuvreRatios instead re-runs 0006's own seed_ratios()
function directly against the real models, the same pattern already
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


@pytest.fixture
def dqe(db, cabinet, site):
    return DQE.objects.create(cabinet=cabinet, site=site, reference='DQE-2OE-001', title='Test DQE', status=DQEStatus.DRAFT)


def _work_item(cabinet, work_category, code):
    return PriceLibraryItem.objects.create(
        cabinet=cabinet, code=code, designation=f'Ouvrage {code}',
        item_type=PriceItemType.WORK_ITEM, work_category=work_category,
        unit='m2', unit_price=Decimal('10.00'),
    )


@pytest.mark.django_db
class TestSecondOeuvreWorkCategoriesExist:
    def test_new_categories_are_valid_choices(self):
        values = {choice.value for choice in WorkCategory}
        assert {'PLOMBERIE', 'ELECTRICITE', 'MENUISERIE', 'PEINTURE', 'REVETEMENTS'} <= values

    def test_price_library_item_accepts_a_new_category(self, cabinet):
        item = _work_item(cabinet, WorkCategory.PEINTURE, 'OUV-PEINT')
        item.full_clean()
        assert item.work_category == WorkCategory.PEINTURE


@pytest.mark.django_db
class TestSeededSecondOeuvreRatios:
    """Re-runs 0006_seed_second_oeuvre_ratios's real seed_ratios()
    function (see _FakeApps above) rather than assuming migration data
    is already present — this suite runs with --nomigrations, so that
    data is never actually seeded by the migration framework itself."""

    @pytest.fixture(autouse=True)
    def _run_seed_migration(self, db):
        import importlib
        migration_module = importlib.import_module(
            'pricing.migrations.0006_seed_second_oeuvre_ratios'
        )
        migration_module.seed_ratios(_FakeApps(), None)

    def test_peinture_ratio_is_seeded_as_a_global_default(self):
        peinture = Material.objects.get(name='Peinture')
        ratio = MaterialConsumptionRatio.objects.get(cabinet=None, work_category=WorkCategory.PEINTURE, material=peinture)
        assert ratio.ratio == Decimal('0.2000')

    def test_revetements_ratios_are_seeded_as_global_defaults(self):
        colle = Material.objects.get(name='Colle à carrelage')
        joint = Material.objects.get(name='Joint de carrelage')
        carreaux = Material.objects.get(name='Carreaux')

        colle_ratio = MaterialConsumptionRatio.objects.get(cabinet=None, work_category=WorkCategory.REVETEMENTS, material=colle)
        joint_ratio = MaterialConsumptionRatio.objects.get(cabinet=None, work_category=WorkCategory.REVETEMENTS, material=joint)
        carreaux_ratio = MaterialConsumptionRatio.objects.get(cabinet=None, work_category=WorkCategory.REVETEMENTS, material=carreaux)

        assert colle_ratio.ratio == Decimal('3.0000')
        assert joint_ratio.ratio == Decimal('0.3000')
        assert carreaux_ratio.ratio == Decimal('1.1000')

    @pytest.mark.parametrize('category', ['PLOMBERIE', 'ELECTRICITE', 'MENUISERIE'])
    def test_catalog_specific_trades_are_not_seeded(self, category):
        """Deliberate: no generic default makes sense for these — see
        WorkCategory's own docstring."""
        assert not MaterialConsumptionRatio.objects.filter(cabinet=None, work_category=category).exists()


@pytest.mark.django_db
class TestExplodedRequirementsForSecondOeuvre:
    """Exercises exploded_requirements() against locally-created ratios
    (same convention as test_devis_material_comparison.py's ciment_ratio
    fixture) — independent of whether 0006's seed migration has run, so
    this correctness guarantee doesn't depend on migration machinery at
    all, only on MaterialConsumptionRatio + WorkCategory themselves."""

    def test_peinture_work_item_explodes_via_its_ratio(self, cabinet, dqe):
        peinture = Material.objects.create(name='Peinture (test)', unit='L')
        MaterialConsumptionRatio.objects.create(
            cabinet=None, work_category=WorkCategory.PEINTURE, material=peinture,
            ratio=Decimal('0.2000'), ratio_unit='L/m2',
        )
        item = _work_item(cabinet, WorkCategory.PEINTURE, 'OUV-PEINT-2')
        line = DQELine.objects.create(dqe=dqe, price_item=item, designation='Peinture murs', quantity=Decimal('50'), unit_price=item.unit_price)

        exploded = line.exploded_requirements()
        assert exploded[peinture.id] == Decimal('50') * Decimal('0.2000')

    def test_revetements_work_item_explodes_into_all_three_materials(self, cabinet, dqe):
        colle = Material.objects.create(name='Colle (test)', unit='kg')
        joint = Material.objects.create(name='Joint (test)', unit='kg')
        carreaux = Material.objects.create(name='Carreaux (test)', unit='m2')
        for material, ratio in [(colle, '3.0000'), (joint, '0.3000'), (carreaux, '1.1000')]:
            MaterialConsumptionRatio.objects.create(
                cabinet=None, work_category=WorkCategory.REVETEMENTS, material=material,
                ratio=Decimal(ratio), ratio_unit='x/m2',
            )
        item = _work_item(cabinet, WorkCategory.REVETEMENTS, 'OUV-REV-1')
        line = DQELine.objects.create(dqe=dqe, price_item=item, designation='Carrelage séjour', quantity=Decimal('20'), unit_price=item.unit_price)

        exploded = line.exploded_requirements()
        assert exploded[colle.id] == Decimal('20') * Decimal('3.0000')
        assert exploded[joint.id] == Decimal('20') * Decimal('0.3000')
        assert exploded[carreaux.id] == Decimal('20') * Decimal('1.1000')

    def test_menuiserie_work_item_explodes_to_nothing_without_a_cabinet_ratio(self, cabinet, dqe):
        """No seeded default for this category — exploded_requirements()
        returns an empty dict until the cabinet defines its own ratio."""
        item = _work_item(cabinet, WorkCategory.MENUISERIE, 'OUV-MENUIS-1')
        line = DQELine.objects.create(dqe=dqe, price_item=item, designation='Porte bois', quantity=Decimal('3'), unit_price=item.unit_price)
        assert line.exploded_requirements() == {}

    def test_cabinet_can_override_with_its_own_menuiserie_ratio(self, cabinet, dqe):
        bois = Material.objects.create(name='Bois de menuiserie', unit='m2')
        MaterialConsumptionRatio.objects.create(
            cabinet=cabinet, work_category=WorkCategory.MENUISERIE, material=bois,
            ratio=Decimal('1.5000'), ratio_unit='m2/unité',
        )
        item = _work_item(cabinet, WorkCategory.MENUISERIE, 'OUV-MENUIS-2')
        line = DQELine.objects.create(dqe=dqe, price_item=item, designation='Porte bois', quantity=Decimal('3'), unit_price=item.unit_price)

        exploded = line.exploded_requirements()
        assert exploded[bois.id] == Decimal('3') * Decimal('1.5000')
