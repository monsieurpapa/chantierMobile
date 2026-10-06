"""Tests for the 2026-10-06 "mouvement caisse -> Achat matériaux" feature:

- The caisse mouvement form gets a dynamic line-item section (description
  du matériel / quantité / P.U. / prix total) — CaisseTransactionMaterialLine,
  via CaisseTransactionMaterialLineFormSet.
- Each line is catalog-linked (materials.Material) or free-text, same XOR
  as materials.MaterialRequestItem.
- These lines then show up in the chantier's "Matériaux" tab
  (templates/projects/site_detail.html), scoped by the mouvement's `site`.
- This is a financial record only (confirmed scope): it does not touch
  procurement.StockItem/StockMovement — the chantier's actual
  stock-on-hand keeps being tracked by the magasinier, and the technical
  team already has a daily/weekly/monthly historical view of it via the
  pre-existing procurement.StockReportView (not modified here beyond a
  link into it from the Matériaux tab).
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from finance.models import (
    Caisse, CaisseTransaction, CaisseTransactionCategory, CaisseTransactionMaterialLine,
    MATERIALS_PURCHASE_CATEGORY_NAME,
)
from chantiermobile.constants import CaisseTransactionType, CaisseType


@pytest.fixture
def caisse_factory(db, cabinet):
    def create_caisse(**kwargs):
        defaults = {'cabinet': cabinet, 'name': 'Caisse Test', 'caisse_type': CaisseType.PRINCIPALE}
        defaults.update(kwargs)
        return Caisse.objects.create(**defaults)
    return create_caisse


@pytest.fixture
def caisse(caisse_factory):
    return caisse_factory()


@pytest.fixture
def materials_category(db):
    # Seeded in production via finance.migrations.0013, but pytest.ini runs
    # with --nomigrations, so data migrations never run against the test
    # DB — create it explicitly here.
    return CaisseTransactionCategory.objects.create(name=MATERIALS_PURCHASE_CATEGORY_NAME)


def _material_management_data(prefix='material', total=1, initial=0):
    return {
        f'{prefix}-TOTAL_FORMS': str(total),
        f'{prefix}-INITIAL_FORMS': str(initial),
        f'{prefix}-MIN_NUM_FORMS': '0',
        f'{prefix}-MAX_NUM_FORMS': '1000',
    }


def _transaction_payload(site=None, category=None, **overrides):
    payload = {
        'transaction_type': CaisseTransactionType.SORTIE,
        'amount': '500.00',
        'date': '2026-10-06',
        'description': 'Achat ciment',
    }
    if site is not None:
        payload['site'] = str(site.pk)
    if category is not None:
        payload['category'] = str(category.pk)
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestCaisseTransactionMaterialLineModel:
    def test_catalog_linked_line_computes_total(self, caisse, user, material_factory):
        material = material_factory(name='Ciment', unit='sac')
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('100.00'),
            date='2026-10-06', recorded_by=user,
        )
        line = CaisseTransactionMaterialLine.objects.create(
            transaction=tx, material=material, quantity=Decimal('10'), unit_price=Decimal('5.00'),
        )
        assert line.line_total == Decimal('50.00')
        assert line.display_name == 'Ciment'

    def test_free_text_line_computes_total(self, caisse, user):
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('100.00'),
            date='2026-10-06', recorded_by=user,
        )
        line = CaisseTransactionMaterialLine.objects.create(
            transaction=tx, material_name='Sable fin', quantity=Decimal('3'), unit_price=Decimal('20.00'),
        )
        assert line.line_total == Decimal('60.00')
        assert line.display_name == 'Sable fin'

    def test_clean_rejects_neither_material_nor_name(self, caisse, user):
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('100.00'),
            date='2026-10-06', recorded_by=user,
        )
        line = CaisseTransactionMaterialLine(transaction=tx, quantity=Decimal('1'), unit_price=Decimal('1.00'))
        with pytest.raises(Exception):
            line.full_clean()

    def test_clean_rejects_both_material_and_name(self, caisse, user, material_factory):
        material = material_factory()
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('100.00'),
            date='2026-10-06', recorded_by=user,
        )
        line = CaisseTransactionMaterialLine(
            transaction=tx, material=material, material_name='Dup', quantity=Decimal('1'), unit_price=Decimal('1.00'),
        )
        with pytest.raises(Exception):
            line.full_clean()


@pytest.mark.django_db
class TestCaisseTransactionFormMaterialSection:
    def test_create_with_catalog_and_free_text_lines(self, director_client, caisse, site, materials_category, material_factory):
        material = material_factory(name='Ciment', unit='sac')
        payload = _transaction_payload(site=site, category=materials_category)
        payload.update(_material_management_data(total=2))
        payload.update({
            'material-0-material': str(material.pk),
            'material-0-quantity': '10',
            'material-0-unit_price': '5.00',
            'material-1-material_name': 'Sable fin',
            'material-1-quantity': '3',
            'material-1-unit_price': '20.00',
        })
        response = director_client.post(
            reverse('finance:caisse_transaction_create', kwargs={'pk': caisse.pk}), payload,
        )
        assert response.status_code == 302, getattr(response, 'context', None) and response.context.get('form').errors

        tx = CaisseTransaction.objects.get(description='Achat ciment')
        lines = list(tx.material_lines.all())
        assert len(lines) == 2
        assert sum(l.line_total for l in lines) == Decimal('110.00')

    def test_legacy_post_without_material_section_still_saves_transaction(self, director_client, caisse, site, materials_category):
        """A POST missing the formset's management fields entirely (an
        older client, a direct API call, a page without JS) must not
        500 — treated as "no material lines submitted"."""
        payload = _transaction_payload(site=site, category=materials_category)
        response = director_client.post(
            reverse('finance:caisse_transaction_create', kwargs={'pk': caisse.pk}), payload,
        )
        assert response.status_code == 302
        tx = CaisseTransaction.objects.get(description='Achat ciment')
        assert tx.material_lines.count() == 0

    def test_line_with_neither_catalog_nor_free_text_is_rejected(self, director_client, caisse, site, materials_category):
        payload = _transaction_payload(site=site, category=materials_category)
        payload.update(_material_management_data(total=1))
        payload.update({'material-0-quantity': '1', 'material-0-unit_price': '1.00'})
        response = director_client.post(
            reverse('finance:caisse_transaction_create', kwargs={'pk': caisse.pk}), payload,
        )
        assert response.status_code == 200
        assert not CaisseTransaction.objects.filter(description='Achat ciment').exists()

    def test_update_adds_a_second_material_line(self, director_client, caisse, site, materials_category, user):
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('500.00'),
            date='2026-10-06', site=site, category=materials_category, recorded_by=user,
        )
        existing = CaisseTransactionMaterialLine.objects.create(
            transaction=tx, material_name='Ciment', quantity=Decimal('10'), unit_price=Decimal('5.00'),
        )
        payload = _transaction_payload(site=site, category=materials_category)
        payload.update(_material_management_data(total=2, initial=1))
        payload.update({
            'material-0-id': str(existing.pk),
            'material-0-material_name': 'Ciment',
            'material-0-quantity': '10',
            'material-0-unit_price': '5.00',
            'material-1-material_name': 'Fer à béton',
            'material-1-quantity': '2',
            'material-1-unit_price': '30.00',
        })
        response = director_client.post(
            reverse('finance:caisse_transaction_update', kwargs={'pk': tx.pk}), payload,
        )
        assert response.status_code == 302, getattr(response, 'context', None) and response.context.get('form').errors
        assert tx.material_lines.count() == 2
        assert tx.material_lines.filter(material_name='Fer à béton').exists()


@pytest.mark.django_db
class TestSiteDetailMaterialsTab:
    def test_purchase_lines_shown_on_chantier_materials_tab(self, director_client, caisse, site, materials_category, user):
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('500.00'),
            date='2026-10-06', site=site, category=materials_category, recorded_by=user,
        )
        CaisseTransactionMaterialLine.objects.create(
            transaction=tx, material_name='Ciment Portland', quantity=Decimal('10'), unit_price=Decimal('5.00'),
        )
        response = director_client.get(reverse('projects:site_detail', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Ciment Portland' in content
        assert '50' in content  # line_total = 10 * 5.00

    def test_purchase_line_from_another_site_not_shown(self, director_client, caisse, site, site_factory, materials_category, user):
        other_site = site_factory(name='Autre Chantier')
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('500.00'),
            date='2026-10-06', site=other_site, category=materials_category, recorded_by=user,
        )
        CaisseTransactionMaterialLine.objects.create(
            transaction=tx, material_name='Tuyaux PVC', quantity=Decimal('4'), unit_price=Decimal('15.00'),
        )
        response = director_client.get(reverse('projects:site_detail', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 200
        assert 'Tuyaux PVC' not in response.content.decode()

    def test_stock_history_link_visible_to_engineer(self, engineer_client, site):
        response = engineer_client.get(reverse('projects:site_detail', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 200
        assert reverse('procurement:stock_report').encode() in response.content
