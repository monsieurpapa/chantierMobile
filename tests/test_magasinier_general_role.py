"""Tests for the 2026-10-07 "Magasinier Général" role: read-only,
cross-cabinet visibility into all sites' expenses (the Expense Report)
and stock reports — but no write rights beyond those of a regular
MAGASINIER (who is scoped to the sites they're actually assigned to and
cannot act cabinet-wide either, per STOCK_ACTION_ROLES/CAISSE_MANAGE_ROLES
not listing either Magasinier role).
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from chantiermobile.constants import UserRoles, ApprovalStatus


@pytest.fixture
def magasinier_general_user(db, cabinet):
    from django.contrib.auth import get_user_model
    from accounts.models import UserCabinetRole
    User = get_user_model()
    u = User.objects.create_user(username='magasinier_gen', email='magasinier_gen@example.com', password='testpass123')
    UserCabinetRole.objects.create(user=u, cabinet=cabinet, role=UserRoles.MAGASINIER_GENERAL, status=ApprovalStatus.APPROVED)
    return u


@pytest.fixture
def magasinier_general_client(client, magasinier_general_user):
    client.login(username='magasinier_gen', password='testpass123')
    return client


@pytest.fixture
def magasinier_user(db, cabinet):
    from django.contrib.auth import get_user_model
    from accounts.models import UserCabinetRole
    User = get_user_model()
    u = User.objects.create_user(username='magasinier_plain', email='magasinier_plain@example.com', password='testpass123')
    UserCabinetRole.objects.create(user=u, cabinet=cabinet, role=UserRoles.MAGASINIER, status=ApprovalStatus.APPROVED)
    return u


@pytest.fixture
def magasinier_client(client, magasinier_user):
    client.login(username='magasinier_plain', password='testpass123')
    return client


@pytest.mark.django_db
class TestMagasinierGeneralRoleExists:
    def test_role_is_a_valid_choice(self):
        assert 'MAGASINIER_GENERAL' in UserRoles.values


@pytest.mark.django_db
class TestExpenseReportAccess:
    def test_magasinier_general_can_view_expense_report(self, magasinier_general_client):
        response = magasinier_general_client.get(reverse('finance:expense_report'))
        assert response.status_code == 200

    def test_plain_magasinier_cannot_view_expense_report(self, magasinier_client):
        response = magasinier_client.get(reverse('finance:expense_report'))
        assert response.status_code == 302

    def test_expense_report_is_cross_cabinet_not_site_scoped(
        self, magasinier_general_client, site_factory, cabinet, expense_category, magasinier_general_user,
    ):
        """A Magasinier Général sees expenses across every site in their
        cabinet, not only ones they're individually assigned to — unlike
        the per-site scoping a regular Magasinier would get elsewhere."""
        from datetime import date
        from finance.models import Expense
        site_a = site_factory(name='Chantier A', cabinet=cabinet)
        site_b = site_factory(name='Chantier B', cabinet=cabinet)
        Expense.objects.create(
            site=site_a, requester=magasinier_general_user, category=expense_category,
            amount=Decimal('100.00'), expense_date=date.today(), description='Achat de ciment',
        )
        Expense.objects.create(
            site=site_b, requester=magasinier_general_user, category=expense_category,
            amount=Decimal('200.00'), expense_date=date.today(), description='Achat de sable',
        )
        response = magasinier_general_client.get(reverse('finance:expense_report'))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Achat de ciment' in content
        assert 'Achat de sable' in content


@pytest.mark.django_db
class TestStockReportAccess:
    def test_magasinier_general_can_view_stock_report(self, magasinier_general_client):
        response = magasinier_general_client.get(reverse('procurement:stock_report'))
        assert response.status_code == 200

    def test_plain_magasinier_can_also_view_stock_report(self, magasinier_client):
        """Stock report visibility was already cabinet-wide for plain
        Magasinier before this feature — unaffected by this change."""
        response = magasinier_client.get(reverse('procurement:stock_report'))
        assert response.status_code == 200


@pytest.mark.django_db
class TestMagasinierGeneralNoExtraWriteRights:
    def test_cannot_create_caisse_transaction(self, magasinier_general_client, cabinet):
        from finance.models import Caisse
        caisse = Caisse.objects.create(cabinet=cabinet, name='Caisse Principale')
        response = magasinier_general_client.post(
            reverse('finance:caisse_transaction_create', kwargs={'pk': caisse.pk}),
            {'transaction_type': 'ENTREE', 'amount': '500.00', 'description': 'Test'},
        )
        assert response.status_code == 302
        assert not caisse.transactions.exists()

    def test_cannot_record_stock_movement(self, magasinier_general_client, site):
        from procurement.models import StockItem
        item = StockItem.objects.create(site=site, name='Ciment', unit='sac', quantity_on_hand=Decimal('10'))
        response = magasinier_general_client.post(
            reverse('procurement:stock_movement_create', kwargs={'pk': item.pk}),
            {'movement_type': 'IN', 'quantity': '5', 'movement_date': '2026-10-07'},
        )
        item.refresh_from_db()
        assert item.quantity_on_hand == Decimal('10')

    def test_plain_magasinier_can_record_stock_movement_on_assigned_site(self, magasinier_client, site):
        """Contrast: a plain Magasinier retains their existing write
        rights (STOCK_ACTION_ROLES) — this feature adds no new write
        ability to either role."""
        from procurement.models import StockItem
        item = StockItem.objects.create(site=site, name='Sable', unit='m3', quantity_on_hand=Decimal('10'))
        response = magasinier_client.post(
            reverse('procurement:stock_movement_create', kwargs={'pk': item.pk}),
            {'movement_type': 'IN', 'quantity': '5', 'movement_date': '2026-10-07', 'motif': 'Livraison'},
        )
        assert response.status_code == 302
        item.refresh_from_db()
        assert item.quantity_on_hand == Decimal('15')
