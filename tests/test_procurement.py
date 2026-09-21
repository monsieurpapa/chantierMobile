"""
Tests for the procurement app (Achats / Bons de commande + Stocks):
Supplier, StockItem, PurchaseOrder, PurchaseOrderLine, StockMovement.
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.core.exceptions import ValidationError
from django.urls import reverse

from chantiermobile.constants import PurchaseOrderStatus, StockMovementType
from procurement.models import Supplier, StockItem, PurchaseOrder, PurchaseOrderLine, StockMovement


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def supplier(db, cabinet):
    return Supplier.objects.create(
        cabinet=cabinet,
        name='Quincaillerie Générale',
        contact_name='Jean Dupont',
        phone='+250700000000',
        email='contact@quincaillerie.example',
    )


@pytest.fixture
def stock_item(db, site):
    return StockItem.objects.create(
        site=site,
        name='Ciment 50kg',
        unit='sac',
        quantity_on_hand=Decimal('10.00'),
        reorder_threshold=Decimal('5.00'),
    )


@pytest.fixture
def purchase_order(db, site, supplier):
    return PurchaseOrder.objects.create(
        site=site,
        supplier=supplier,
        order_number='BC-TEST-001',
        order_date=date.today(),
        status=PurchaseOrderStatus.BROUILLON,
    )


@pytest.fixture
def po_line(db, purchase_order, stock_item):
    return PurchaseOrderLine.objects.create(
        purchase_order=purchase_order,
        stock_item=stock_item,
        quantity=Decimal('20.00'),
        unit_price=Decimal('15.00'),
    )


# ============================================================================
# Supplier
# ============================================================================

@pytest.mark.django_db
class TestSupplier:
    def test_str(self, supplier):
        assert str(supplier) == 'Quincaillerie Générale'

    def test_total_orders(self, supplier, purchase_order):
        assert supplier.total_orders == 1


# ============================================================================
# StockItem / StockMovement
# ============================================================================

@pytest.mark.django_db
class TestStockItem:
    def test_default_quantity_zero(self, site):
        item = StockItem.objects.create(site=site, name='Sable', unit='m3')
        assert item.quantity_on_hand == 0

    def test_is_below_reorder_threshold(self, stock_item):
        assert stock_item.is_below_reorder_threshold is False
        stock_item.quantity_on_hand = Decimal('5.00')
        stock_item.save(update_fields=['quantity_on_hand'])
        assert stock_item.is_below_reorder_threshold is True

    def test_no_threshold_never_flags(self, site):
        item = StockItem.objects.create(site=site, name='Sable', unit='m3', quantity_on_hand=0)
        assert item.is_below_reorder_threshold is False

    def test_negative_reorder_threshold_invalid(self, stock_item):
        stock_item.reorder_threshold = Decimal('-1.00')
        with pytest.raises(ValidationError):
            stock_item.full_clean()


@pytest.mark.django_db
class TestStockMovement:
    def test_in_movement_increases_quantity(self, stock_item):
        StockMovement.objects.create(
            stock_item=stock_item,
            movement_type=StockMovementType.IN,
            quantity=Decimal('5.00'),
            movement_date=date.today(),
        )
        stock_item.refresh_from_db()
        assert stock_item.quantity_on_hand == Decimal('15.00')

    def test_out_movement_decreases_quantity(self, stock_item):
        StockMovement.objects.create(
            stock_item=stock_item,
            movement_type=StockMovementType.OUT,
            quantity=Decimal('4.00'),
            movement_date=date.today(),
        )
        stock_item.refresh_from_db()
        assert stock_item.quantity_on_hand == Decimal('6.00')

    def test_out_movement_cannot_exceed_stock(self, stock_item):
        movement = StockMovement(
            stock_item=stock_item,
            movement_type=StockMovementType.OUT,
            quantity=Decimal('100.00'),
            movement_date=date.today(),
        )
        with pytest.raises(ValidationError):
            movement.full_clean()

    def test_out_movement_save_guards_negative_even_without_clean(self, stock_item):
        movement = StockMovement(
            stock_item=stock_item,
            movement_type=StockMovementType.OUT,
            quantity=Decimal('100.00'),
            movement_date=date.today(),
        )
        with pytest.raises(ValidationError):
            movement.save()
        stock_item.refresh_from_db()
        assert stock_item.quantity_on_hand == Decimal('10.00')

    def test_adjustment_can_be_negative(self, stock_item):
        StockMovement.objects.create(
            stock_item=stock_item,
            movement_type=StockMovementType.ADJUSTMENT,
            quantity=Decimal('-2.00'),
            movement_date=date.today(),
        )
        stock_item.refresh_from_db()
        assert stock_item.quantity_on_hand == Decimal('8.00')

    def test_adjustment_zero_invalid(self, stock_item):
        movement = StockMovement(
            stock_item=stock_item,
            movement_type=StockMovementType.ADJUSTMENT,
            quantity=Decimal('0.00'),
            movement_date=date.today(),
        )
        with pytest.raises(ValidationError):
            movement.full_clean()

    def test_in_movement_zero_or_negative_invalid(self, stock_item):
        movement = StockMovement(
            stock_item=stock_item,
            movement_type=StockMovementType.IN,
            quantity=Decimal('-1.00'),
            movement_date=date.today(),
        )
        with pytest.raises(ValidationError):
            movement.full_clean()


# ============================================================================
# PurchaseOrder / PurchaseOrderLine
# ============================================================================

@pytest.mark.django_db
class TestPurchaseOrderLine:
    def test_line_total(self, po_line):
        assert po_line.line_total == Decimal('300.00')

    def test_remaining_quantity(self, po_line):
        assert po_line.remaining_quantity == Decimal('20.00')

    def test_negative_quantity_invalid(self, purchase_order, stock_item):
        line = PurchaseOrderLine(
            purchase_order=purchase_order, stock_item=stock_item,
            quantity=Decimal('-1.00'), unit_price=Decimal('1.00'),
        )
        with pytest.raises(ValidationError):
            line.full_clean()

    def test_stock_item_must_share_site(self, purchase_order, cabinet):
        from projects.models import Site
        from chantiermobile.constants import SiteStatus
        other_site = Site.objects.create(
            cabinet=cabinet, name='Autre chantier', location='Ailleurs',
            status=SiteStatus.ACTIVE, start_date=date.today(),
        )
        other_item = StockItem.objects.create(site=other_site, name='Sable', unit='m3')
        line = PurchaseOrderLine(
            purchase_order=purchase_order, stock_item=other_item,
            quantity=Decimal('1.00'), unit_price=Decimal('1.00'),
        )
        with pytest.raises(ValidationError):
            line.full_clean()


@pytest.mark.django_db
class TestPurchaseOrder:
    def test_total_ht(self, purchase_order, po_line):
        assert purchase_order.total_ht == Decimal('300.00')

    def test_expected_delivery_before_order_date_invalid(self, purchase_order):
        purchase_order.expected_delivery_date = purchase_order.order_date - timedelta(days=1)
        with pytest.raises(ValidationError):
            purchase_order.full_clean()

    def test_invalid_status_transition(self, purchase_order):
        purchase_order.status = PurchaseOrderStatus.RECUE
        with pytest.raises(ValidationError):
            purchase_order.full_clean()

    def test_receive_requires_sent_status(self, purchase_order, po_line):
        with pytest.raises(ValidationError):
            purchase_order.receive()

    def test_receive_full_delivery(self, purchase_order, po_line, stock_item):
        purchase_order.status = PurchaseOrderStatus.ENVOYEE
        purchase_order.full_clean()
        purchase_order.save()

        purchase_order.receive()

        po_line.refresh_from_db()
        stock_item.refresh_from_db()
        purchase_order.refresh_from_db()

        assert po_line.quantity_received == Decimal('20.00')
        assert stock_item.quantity_on_hand == Decimal('30.00')  # 10 initial + 20 received
        assert purchase_order.status == PurchaseOrderStatus.RECUE
        assert purchase_order.is_fully_received is True

    def test_receive_partial_delivery(self, purchase_order, po_line, stock_item):
        purchase_order.status = PurchaseOrderStatus.ENVOYEE
        purchase_order.full_clean()
        purchase_order.save()

        purchase_order.receive(lines_received={po_line.id: Decimal('5.00')})

        po_line.refresh_from_db()
        stock_item.refresh_from_db()
        purchase_order.refresh_from_db()

        assert po_line.quantity_received == Decimal('5.00')
        assert stock_item.quantity_on_hand == Decimal('15.00')
        assert purchase_order.status == PurchaseOrderStatus.RECUE_PARTIELLE

        # Receiving the remainder completes it
        purchase_order.receive()
        po_line.refresh_from_db()
        purchase_order.refresh_from_db()
        assert po_line.quantity_received == Decimal('20.00')
        assert purchase_order.status == PurchaseOrderStatus.RECUE

    def test_receive_creates_stock_movement_linked_to_line(self, purchase_order, po_line):
        purchase_order.status = PurchaseOrderStatus.ENVOYEE
        purchase_order.full_clean()
        purchase_order.save()

        purchase_order.receive()

        movement = StockMovement.objects.get(purchase_order_line=po_line)
        assert movement.movement_type == StockMovementType.IN
        assert movement.quantity == Decimal('20.00')


# ============================================================================
# Views — smoke tests for auth/role gating and core flows
# ============================================================================

@pytest.mark.django_db
class TestProcurementViews:
    def test_supplier_list_requires_login(self, client):
        response = client.get(reverse('procurement:supplier_list'))
        assert response.status_code == 302

    def test_supplier_list_accessible_to_director(self, director_client, supplier):
        response = director_client.get(reverse('procurement:supplier_list'))
        assert response.status_code == 200
        assert supplier in response.context['suppliers']

    def test_supplier_create_requires_role(self, engineer_client):
        response = engineer_client.get(reverse('procurement:supplier_create'))
        # ENGINEER is not in allowed_roles for supplier_create -> redirected
        assert response.status_code == 302

    def test_supplier_create_by_director(self, director_client):
        response = director_client.post(reverse('procurement:supplier_create'), {
            'name': 'Nouveau Fournisseur',
            'contact_name': '',
            'phone': '',
            'email': '',
            'address': '',
            'notes': '',
        })
        assert response.status_code == 302
        assert Supplier.objects.filter(name='Nouveau Fournisseur').exists()

    def test_stock_item_detail_shows_movements(self, director_client, stock_item):
        response = director_client.get(reverse('procurement:stock_item_detail', kwargs={'pk': stock_item.pk}))
        assert response.status_code == 200
        assert response.context['stock_item'] == stock_item

    def test_purchase_order_detail(self, director_client, purchase_order, po_line):
        response = director_client.get(reverse('procurement:purchase_order_detail', kwargs={'pk': purchase_order.pk}))
        assert response.status_code == 200
        assert response.context['purchase_order'].total_ht == Decimal('300.00')

    def test_purchase_order_send_and_receive_flow(self, director_client, purchase_order, po_line, stock_item):
        send_url = reverse('procurement:purchase_order_send', kwargs={'pk': purchase_order.pk})
        response = director_client.post(send_url)
        assert response.status_code == 302
        purchase_order.refresh_from_db()
        assert purchase_order.status == PurchaseOrderStatus.ENVOYEE

        receive_url = reverse('procurement:purchase_order_receive', kwargs={'pk': purchase_order.pk})
        response = director_client.post(receive_url)
        assert response.status_code == 302
        purchase_order.refresh_from_db()
        stock_item.refresh_from_db()
        assert purchase_order.status == PurchaseOrderStatus.RECUE
        assert stock_item.quantity_on_hand == Decimal('30.00')

    def test_cabinet_scoping_hides_other_cabinets_suppliers(self, director_client, supplier, db):
        from accounts.models import Cabinet
        other_cabinet = Cabinet.objects.create(name='Autre Cabinet')
        other_supplier = Supplier.objects.create(cabinet=other_cabinet, name='Fournisseur Étranger')

        response = director_client.get(reverse('procurement:supplier_list'))
        suppliers = list(response.context['suppliers'])
        assert supplier in suppliers
        assert other_supplier not in suppliers
