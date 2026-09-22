"""
Tests for wire-transfer purchases (cashier proof entry + financier
validation) and supplier credit tracking — Phase B3 of the Finance /
Achats module build-out.
"""
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from procurement.models import Supplier, PurchaseOrder, SupplierCredit
from finance.models import Caisse
from chantiermobile.constants import PurchasePaymentMethod, PurchaseOrderStatus, CaisseType, CaisseTransactionType


@pytest.fixture
def supplier_factory(db, cabinet):
    def create_supplier(**kwargs):
        defaults = {'cabinet': cabinet, 'name': 'Fournisseur Test'}
        defaults.update(kwargs)
        return Supplier.objects.create(**defaults)
    return create_supplier


@pytest.fixture
def supplier(db, supplier_factory):
    return supplier_factory()


@pytest.fixture
def purchase_order_factory(db, site, supplier):
    def create_po(**kwargs):
        defaults = {
            'site': site, 'supplier': supplier, 'order_number': f'PO-{PurchaseOrder.objects.count() + 1:04d}',
            'order_date': date.today(), 'status': PurchaseOrderStatus.BROUILLON,
            'payment_method': PurchasePaymentMethod.VIREMENT,
        }
        defaults.update(kwargs)
        return PurchaseOrder.objects.create(**defaults)
    return create_po


@pytest.fixture
def purchase_order(db, purchase_order_factory):
    return purchase_order_factory()


@pytest.fixture
def caisse_factory(db, cabinet):
    def create_caisse(**kwargs):
        defaults = {'cabinet': cabinet, 'name': 'Caisse Test', 'caisse_type': CaisseType.PRINCIPALE}
        defaults.update(kwargs)
        return Caisse.objects.create(**defaults)
    return create_caisse


@pytest.fixture
def cashier_user(db, cabinet):
    from django.contrib.auth import get_user_model
    from accounts.models import UserCabinetRole
    from chantiermobile.constants import UserRoles, ApprovalStatus
    user = get_user_model().objects.create_user(username='cashier_wt', password='testpass123')
    UserCabinetRole.objects.create(user=user, cabinet=cabinet, role=UserRoles.CASHIER, status=ApprovalStatus.APPROVED)
    return user


@pytest.fixture
def cashier_client(client, cashier_user):
    client.login(username='cashier_wt', password='testpass123')
    return client


@pytest.fixture
def financier_user(db, cabinet):
    from django.contrib.auth import get_user_model
    from accounts.models import UserCabinetRole
    from chantiermobile.constants import UserRoles, ApprovalStatus
    user = get_user_model().objects.create_user(username='financier_wt', password='testpass123')
    UserCabinetRole.objects.create(user=user, cabinet=cabinet, role=UserRoles.FINANCIER, status=ApprovalStatus.APPROVED)
    return user


@pytest.fixture
def financier_client(client, financier_user):
    client.login(username='financier_wt', password='testpass123')
    return client


def _proof_file():
    return SimpleUploadedFile('proof.pdf', b'%PDF-1.4 fake content', content_type='application/pdf')


@pytest.mark.django_db
class TestPurchaseOrderWireTransferModel:
    def test_submit_transfer_proof_requires_virement(self, purchase_order_factory):
        po = purchase_order_factory(payment_method=PurchasePaymentMethod.CAISSE)
        with pytest.raises(ValidationError):
            po.submit_transfer_proof(None, _proof_file())

    def test_submit_then_validate(self, purchase_order, cashier_user, financier_user):
        assert not purchase_order.is_transfer_validated
        purchase_order.submit_transfer_proof(cashier_user, _proof_file())
        purchase_order.refresh_from_db()
        assert purchase_order.transfer_proof
        assert purchase_order.entered_by_cashier == cashier_user
        assert not purchase_order.is_transfer_validated

        purchase_order.validate_transfer(financier_user)
        purchase_order.refresh_from_db()
        assert purchase_order.is_transfer_validated
        assert purchase_order.validated_by_financier == financier_user

    def test_cannot_validate_without_proof(self, purchase_order, financier_user):
        with pytest.raises(ValidationError):
            purchase_order.validate_transfer(financier_user)

    def test_resubmitting_proof_resets_validation(self, purchase_order, cashier_user, financier_user):
        purchase_order.submit_transfer_proof(cashier_user, _proof_file())
        purchase_order.validate_transfer(financier_user)
        assert purchase_order.is_transfer_validated

        purchase_order.submit_transfer_proof(cashier_user, _proof_file())
        purchase_order.refresh_from_db()
        assert not purchase_order.is_transfer_validated


@pytest.mark.django_db
class TestPurchaseOrderWireTransferViews:
    def test_cashier_can_submit_proof(self, cashier_client, purchase_order):
        response = cashier_client.post(
            reverse('procurement:purchase_order_submit_transfer_proof', kwargs={'pk': purchase_order.pk}),
            {'transfer_proof': _proof_file()},
        )
        assert response.status_code == 302
        purchase_order.refresh_from_db()
        assert purchase_order.transfer_proof

    def test_engineer_cannot_submit_proof(self, engineer_client, purchase_order, site):
        response = engineer_client.post(
            reverse('procurement:purchase_order_submit_transfer_proof', kwargs={'pk': purchase_order.pk}),
            {'transfer_proof': _proof_file()},
        )
        assert response.status_code == 302
        purchase_order.refresh_from_db()
        assert not purchase_order.transfer_proof

    def test_financier_can_validate(self, financier_client, purchase_order, cashier_user):
        purchase_order.submit_transfer_proof(cashier_user, _proof_file())
        response = financier_client.post(
            reverse('procurement:purchase_order_validate_transfer', kwargs={'pk': purchase_order.pk}),
        )
        assert response.status_code == 302
        purchase_order.refresh_from_db()
        assert purchase_order.is_transfer_validated

    def test_cashier_cannot_validate(self, cashier_client, purchase_order, cashier_user):
        purchase_order.submit_transfer_proof(cashier_user, _proof_file())
        response = cashier_client.post(
            reverse('procurement:purchase_order_validate_transfer', kwargs={'pk': purchase_order.pk}),
        )
        purchase_order.refresh_from_db()
        assert not purchase_order.is_transfer_validated


@pytest.mark.django_db
class TestSupplierCreditModel:
    def test_outstanding_balance_and_full_payment(self, supplier):
        credit = SupplierCredit.objects.create(supplier=supplier, amount=Decimal('1000.00'), date=date.today())
        assert credit.outstanding_balance == Decimal('1000.00')
        assert not credit.is_fully_paid

        credit.record_payment(Decimal('400.00'), None)
        credit.refresh_from_db()
        assert credit.outstanding_balance == Decimal('600.00')

        credit.record_payment(Decimal('600.00'), None)
        credit.refresh_from_db()
        assert credit.is_fully_paid

    def test_overpayment_rejected(self, supplier):
        credit = SupplierCredit.objects.create(supplier=supplier, amount=Decimal('500.00'), date=date.today())
        with pytest.raises(ValidationError):
            credit.record_payment(Decimal('600.00'), None)

    def test_payment_posts_caisse_exit(self, supplier, caisse_factory, user):
        caisse = caisse_factory()
        caisse.record(CaisseTransactionType.ENTREE, Decimal('1000.00'), user)
        credit = SupplierCredit.objects.create(supplier=supplier, amount=Decimal('300.00'), date=date.today())

        credit.record_payment(Decimal('300.00'), user, caisse=caisse)
        assert caisse.balance == Decimal('700.00')

    def test_supplier_total_credit_outstanding(self, supplier):
        SupplierCredit.objects.create(supplier=supplier, amount=Decimal('100.00'), date=date.today())
        SupplierCredit.objects.create(supplier=supplier, amount=Decimal('200.00'), paid_amount=Decimal('50.00'), date=date.today())
        assert supplier.total_credit_outstanding == Decimal('250.00')


@pytest.mark.django_db
class TestSupplierCreditViews:
    def test_accountant_can_list_and_create_credit(self, accountant_client, supplier):
        response = accountant_client.get(reverse('procurement:supplier_credit_list'))
        assert response.status_code == 200

        response = accountant_client.post(reverse('procurement:supplier_credit_create'), {
            'supplier': supplier.pk, 'amount': '750.00', 'date': date.today().isoformat(),
        })
        assert response.status_code == 302
        assert SupplierCredit.objects.filter(supplier=supplier, amount=Decimal('750.00')).exists()

    def test_engineer_cannot_view_credit_list(self, engineer_client):
        response = engineer_client.get(reverse('procurement:supplier_credit_list'))
        assert response.status_code == 302

    def test_repay_view(self, accountant_client, supplier):
        credit = SupplierCredit.objects.create(supplier=supplier, amount=Decimal('200.00'), date=date.today())
        response = accountant_client.post(reverse('procurement:supplier_credit_repay', kwargs={'pk': credit.pk}), {
            'amount': '200.00',
        })
        assert response.status_code == 302
        credit.refresh_from_db()
        assert credit.is_fully_paid

    def test_repay_rejects_overpayment(self, accountant_client, supplier):
        credit = SupplierCredit.objects.create(supplier=supplier, amount=Decimal('200.00'), date=date.today())
        response = accountant_client.post(reverse('procurement:supplier_credit_repay', kwargs={'pk': credit.pk}), {
            'amount': '500.00',
        })
        assert response.status_code == 302
        credit.refresh_from_db()
        assert credit.paid_amount == Decimal('0.00')
