"""
Tests for the "Caissier / Magasinier" feature set added from the client's
meeting notes (Dépenses nature+personnel, Matériel free-text, Magasinier
stock movements + facture, Achats caisse + report, Paiement proof +
director notification, Devis photo alternative).
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.core.exceptions import ValidationError
from django.core import mail
from django.urls import reverse

from chantiermobile.constants import (
    UserRoles, ApprovalStatus, ExpenseNature, ExpenseStatus, CaisseType, StockMovementType,
    PurchaseOrderStatus, InvoiceStatus, DevisStatus, PaymentMethod,
)


# ============================================================================
# Shared fixtures
# ============================================================================

@pytest.fixture
def cashier_user(db, cabinet):
    from django.contrib.auth import get_user_model
    from accounts.models import UserCabinetRole
    User = get_user_model()
    u = User.objects.create_user(username='cashier', email='cashier@example.com', password='testpass123')
    UserCabinetRole.objects.create(user=u, cabinet=cabinet, role=UserRoles.CASHIER, status=ApprovalStatus.APPROVED)
    return u


@pytest.fixture
def cashier_client(client, cashier_user):
    client.login(username='cashier', password='testpass123')
    return client


@pytest.fixture
def magasinier_user(db, cabinet):
    from django.contrib.auth import get_user_model
    from accounts.models import UserCabinetRole
    User = get_user_model()
    u = User.objects.create_user(username='magasinier', email='magasinier@example.com', password='testpass123')
    UserCabinetRole.objects.create(user=u, cabinet=cabinet, role=UserRoles.MAGASINIER, status=ApprovalStatus.APPROVED)
    return u


@pytest.fixture
def magasinier_client(client, magasinier_user):
    client.login(username='magasinier', password='testpass123')
    return client


@pytest.fixture
def supplier(db, cabinet):
    from procurement.models import Supplier
    return Supplier.objects.create(cabinet=cabinet, name='Quincaillerie Test')


@pytest.fixture
def stock_item(db, site):
    from procurement.models import StockItem
    return StockItem.objects.create(
        site=site, name='Ciment 50kg', unit='sac',
        quantity_on_hand=Decimal('10.00'), reorder_threshold=Decimal('5.00'),
    )


@pytest.fixture
def purchase_order(db, site, supplier):
    from procurement.models import PurchaseOrder
    return PurchaseOrder.objects.create(
        site=site, supplier=supplier, order_number='BC-FEAT-TEST-001',
        order_date=date.today(), status=PurchaseOrderStatus.BROUILLON,
    )


@pytest.fixture
def po_line(db, purchase_order, stock_item):
    from procurement.models import PurchaseOrderLine
    return PurchaseOrderLine.objects.create(
        purchase_order=purchase_order, stock_item=stock_item,
        quantity=Decimal('20.00'), unit_price=Decimal('15.00'),
    )


@pytest.fixture
def site_assignment_factory(db):
    from personnel.models import SiteAssignment

    def create_assignment(**kwargs):
        defaults = {
            'role': "Chef d'équipe",
            'start_date': date.today() - timedelta(days=10),
            'end_date': None,
            'daily_rate': Decimal('50.00'),
        }
        defaults.update(kwargs)
        return SiteAssignment.objects.create(**defaults)

    return create_assignment


# ============================================================================
# Dépenses: nature (Matériel / Main d'œuvre) + site-scoped personnel
# ============================================================================

@pytest.mark.django_db
class TestExpenseNatureAndPersonnel:

    def test_personnel_not_assigned_to_site_is_rejected(self, site, expense_category, user, personnel):
        """Expense.clean() blocks a personnel link when that person has no
        SiteAssignment on the expense's site — closes the gap where a
        client could bypass the form's site-scoped dropdown."""
        from finance.models import Expense
        expense = Expense(
            site=site, requester=user, category=expense_category,
            nature=ExpenseNature.MAIN_DOEUVRE, personnel=personnel,
            amount=Decimal('100.00'), expense_date=date.today(),
            description="Main d'œuvre",
        )
        with pytest.raises(ValidationError) as exc_info:
            expense.clean()
        assert 'personnel' in exc_info.value.message_dict

    def test_personnel_assigned_to_site_is_accepted(self, site, expense_category, user, personnel, site_assignment_factory):
        from finance.models import Expense
        site_assignment_factory(personnel=personnel, site=site)
        expense = Expense(
            site=site, requester=user, category=expense_category,
            nature=ExpenseNature.MAIN_DOEUVRE, personnel=personnel,
            amount=Decimal('100.00'), expense_date=date.today(),
            description="Main d'œuvre",
        )
        expense.clean()  # should not raise

    def test_form_requires_personnel_for_main_doeuvre_nature(self, site, expense_category):
        from finance.forms import ExpenseForm
        form = ExpenseForm(data={
            'site': site.pk, 'category': expense_category.pk,
            'nature': ExpenseNature.MAIN_DOEUVRE,
            'amount': '100.00', 'expense_date': date.today(),
            'description': 'Main d\'œuvre sans personnel',
        })
        assert not form.is_valid()
        assert 'personnel' in form.errors

    def test_form_nature_defaults_to_materiel_when_omitted(self, site, expense_category):
        """Existing callers that don't send 'nature' (legacy integrations,
        pre-existing tests) must keep working — falls back to MATERIEL."""
        from finance.forms import ExpenseForm
        form = ExpenseForm(data={
            'site': site.pk, 'category': expense_category.pk,
            'amount': '100.00', 'expense_date': date.today(),
            'description': 'Sans nature',
        })
        assert form.is_valid(), form.errors
        assert form.cleaned_data['nature'] == ExpenseNature.MATERIEL

    def test_form_personnel_queryset_scoped_to_posted_site(self, site, site_factory, expense_category, personnel_factory, site_assignment_factory):
        """The personnel dropdown only accepts people assigned to the
        submitted site — not personnel assigned elsewhere."""
        from finance.forms import ExpenseForm
        other_site = site_factory(name='Other Site')
        on_site = personnel_factory(first_name='OnSite')
        off_site = personnel_factory(first_name='OffSite')
        site_assignment_factory(personnel=on_site, site=site)
        site_assignment_factory(personnel=off_site, site=other_site)

        form = ExpenseForm(data={
            'site': site.pk, 'category': expense_category.pk,
            'nature': ExpenseNature.MAIN_DOEUVRE, 'personnel': off_site.pk,
            'amount': '100.00', 'expense_date': date.today(),
            'description': 'Wrong site personnel',
        })
        assert not form.is_valid()
        assert 'personnel' in form.errors

        form2 = ExpenseForm(data={
            'site': site.pk, 'category': expense_category.pk,
            'nature': ExpenseNature.MAIN_DOEUVRE, 'personnel': on_site.pk,
            'amount': '100.00', 'expense_date': date.today(),
            'description': 'Right site personnel',
        })
        assert form2.is_valid(), form2.errors

    def test_expense_report_denied_without_role(self, engineer_client):
        # engineer_client and accountant_client share conftest's function-scoped
        # `client` fixture, so a single test requesting both would have the
        # second login silently overwrite the first's session — kept as two
        # separate tests instead.
        response = engineer_client.get(reverse('finance:expense_report'))
        assert response.status_code == 302

    def test_expense_report_allowed_with_role(self, accountant_client):
        response = accountant_client.get(reverse('finance:expense_report'))
        assert response.status_code == 200

    def test_expense_report_pdf_returns_pdf(self, accountant_client, expense_factory):
        expense_factory(amount=Decimal('250.00'))
        response = accountant_client.get(reverse('finance:expense_report_pdf'))
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'

    def test_expense_report_per_site_summary_ignores_site_filter(
        self, accountant_client, site, site_factory, expense_factory,
    ):
        """expenses_by_site (the "Dépenses par chantier" summary at the top
        of the report) stays a whole-cabinet overview even when the report's
        own 'site' filter narrows the detail table below — that's what lets
        a director scan every chantier at once, then drill into one."""
        other_site = site_factory(name='Autre Chantier')
        expense_factory(site=site, amount=Decimal('400.00'), status=ExpenseStatus.APPROVED)
        expense_factory(site=other_site, amount=Decimal('600.00'), status=ExpenseStatus.PAID)
        expense_factory(site=other_site, amount=Decimal('1000.00'), status=ExpenseStatus.PENDING)

        response = accountant_client.get(reverse('finance:expense_report'), {'site': site.pk})
        rows = {row['site'].pk: row['total'] for row in response.context['expenses_by_site']}
        assert rows[site.pk] == Decimal('400.00')
        assert rows[other_site.pk] == Decimal('600.00')  # pending expense excluded

    def test_expense_report_per_site_summary_link_drills_into_site(self, accountant_client, site, expense_factory):
        expense_factory(site=site, amount=Decimal('123.00'), status=ExpenseStatus.APPROVED)
        response = accountant_client.get(reverse('finance:expense_report'))
        assert f'site={site.pk}' in response.content.decode()


# ============================================================================
# Matériel: free-text fallback when not in the catalog
# ============================================================================

@pytest.mark.django_db
class TestMaterialRequestItemFreeText:

    def test_requires_material_or_material_name(self, material_request):
        from materials.models import MaterialRequestItem
        item = MaterialRequestItem(request=material_request, quantity=Decimal('1.00'))
        with pytest.raises(ValidationError):
            item.clean()

    def test_cannot_set_both_material_and_material_name(self, material_request, material):
        from materials.models import MaterialRequestItem
        item = MaterialRequestItem(
            request=material_request, material=material, material_name='Sable',
            quantity=Decimal('1.00'),
        )
        with pytest.raises(ValidationError):
            item.clean()

    def test_free_text_item_is_valid_and_has_zero_estimated_cost(self, material_request):
        from materials.models import MaterialRequestItem
        item = MaterialRequestItem(
            request=material_request, material_name='Sable de rivière',
            quantity=Decimal('3.00'),
        )
        item.clean()  # should not raise
        item.save()
        assert item.display_name == 'Sable de rivière'
        assert item.estimated_cost == 0

    def test_catalog_item_display_name_and_cost(self, material_request, material):
        from materials.models import MaterialRequestItem
        item = MaterialRequestItem.objects.create(
            request=material_request, material=material, quantity=Decimal('2.00'),
        )
        assert item.display_name == material.name
        assert item.estimated_cost == material.estimated_cost_per_unit * item.quantity

    def test_multiple_free_text_items_allowed_on_same_request(self, material_request):
        """NULL != NULL for the (request, material) unique constraint, so
        several free-text (material=NULL) rows on one request must not
        collide — unlike two identical catalog materials (see
        test_critical_business_logic.py::test_material_request_unique_material_constraint)."""
        from materials.models import MaterialRequestItem
        MaterialRequestItem.objects.create(request=material_request, material_name='Sable', quantity=Decimal('1.00'))
        MaterialRequestItem.objects.create(request=material_request, material_name='Gravier', quantity=Decimal('2.00'))
        assert material_request.items.count() == 2

    def test_form_accepts_material_name_only(self, material_request):
        from materials.forms import MaterialRequestItemForm
        form = MaterialRequestItemForm(data={'material_name': 'Ciment', 'quantity': '1.00', 'notes': ''})
        assert form.is_valid(), form.errors


# ============================================================================
# Magasinier role: stock entries/exits + optional facture attachment
# ============================================================================

@pytest.mark.django_db
class TestMagasinierRoleAndStockMovements:

    def test_magasinier_can_record_stock_movement(self, magasinier_client, stock_item):
        url = reverse('procurement:stock_movement_create', kwargs={'pk': stock_item.pk})
        response = magasinier_client.post(url, {
            'movement_type': StockMovementType.IN,
            'quantity': '5.00',
            'movement_date': date.today(),
            'notes': 'Livraison',
        }, follow=True)
        assert response.status_code == 200
        stock_item.refresh_from_db()
        assert stock_item.quantity_on_hand == Decimal('15.00')

    def test_magasinier_cannot_create_stock_item_catalog_entry(self, magasinier_client, site):
        """MAGASINIER may record movements against existing stock items but
        not create new catalog entries — that stays DIRECTOR/CHIEF_ENGINEER."""
        response = magasinier_client.get(reverse('procurement:stock_item_create'))
        assert response.status_code == 302

    def test_engineer_without_magasinier_role_cannot_record_movement(self, engineer_client, stock_item):
        url = reverse('procurement:stock_movement_create', kwargs={'pk': stock_item.pk})
        response = engineer_client.post(url, {
            'movement_type': StockMovementType.IN,
            'quantity': '5.00',
            'movement_date': date.today(),
        }, follow=True)
        stock_item.refresh_from_db()
        # Rejected by can_act_for_cabinet — quantity must be unchanged.
        assert stock_item.quantity_on_hand == Decimal('10.00')

    def test_stock_movement_facture_upload(self, stock_item, mock_file_upload):
        from procurement.forms import StockMovementForm
        form = StockMovementForm(data={
            'movement_type': StockMovementType.IN,
            'quantity': '2.00',
            'movement_date': date.today(),
        }, files={'facture': mock_file_upload})
        assert form.is_valid(), form.errors
        movement = form.save(commit=False)
        movement.stock_item = stock_item
        movement.full_clean()
        movement.save()
        assert movement.facture.name


# ============================================================================
# Achats: caisse tag + filterable report
# ============================================================================

@pytest.mark.django_db
class TestCaisseAndAchatsReport:

    def test_purchase_order_defaults_to_caisse_principale(self, purchase_order):
        assert purchase_order.caisse == CaisseType.PRINCIPALE

    def test_achats_report_denied_without_role(self, engineer_client):
        response = engineer_client.get(reverse('procurement:achats_report'))
        assert response.status_code == 302

    def test_achats_report_allowed_with_role(self, director_client):
        response = director_client.get(reverse('procurement:achats_report'))
        assert response.status_code == 200

    def test_achats_report_filters_by_caisse(self, director_client, site, supplier):
        from procurement.models import PurchaseOrder
        PurchaseOrder.objects.create(
            site=site, supplier=supplier, order_number='BC-PRINCIPALE',
            order_date=date.today(), caisse=CaisseType.PRINCIPALE,
        )
        PurchaseOrder.objects.create(
            site=site, supplier=supplier, order_number='BC-SECONDAIRE',
            order_date=date.today(), caisse=CaisseType.SECONDAIRE,
        )
        response = director_client.get(reverse('procurement:achats_report'), {'caisse': CaisseType.SECONDAIRE})
        assert response.status_code == 200
        order_numbers = {po.order_number for po in response.context['purchase_orders']}
        assert order_numbers == {'BC-SECONDAIRE'}

    def test_achats_report_pdf_returns_pdf(self, director_client, purchase_order, po_line):
        response = director_client.get(reverse('procurement:achats_report_pdf'))
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'


# ============================================================================
# Paiement: preuve de paiement + notification automatique des directeurs
# ============================================================================

@pytest.mark.django_db
class TestPaymentProofAndDirectorNotification:

    def test_payment_form_accepts_proof_of_payment(self, invoice, mock_file_upload):
        from revenue.forms import PaymentForm
        form = PaymentForm(data={
            'invoice': invoice.pk, 'amount': '500.00', 'payment_date': date.today(),
            'method': PaymentMethod.CASH, 'reference': 'REF-1',
        }, files={'proof_of_payment': mock_file_upload})
        assert form.is_valid(), form.errors
        payment = form.save()
        assert payment.proof_of_payment.name

    def test_notify_directors_of_payment_emails_approved_directors_only(self, contract, director_user):
        from revenue.models import Invoice, Payment
        from revenue.notifications import notify_directors_of_payment
        from accounts.models import UserCabinetRole
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # A second, PENDING (not yet approved) director must NOT be emailed.
        pending_director = User.objects.create_user(username='pending_dir', email='pending@example.com', password='x')
        UserCabinetRole.objects.create(
            user=pending_director, cabinet=contract.site.cabinet, role=UserRoles.DIRECTOR,
            status=ApprovalStatus.PENDING,
        )

        invoice = Invoice.objects.create(
            contract=contract, invoice_number='INV-NOTIFY-1', amount=Decimal('1000.00'),
            issued_date=date.today(), due_date=date.today() + timedelta(days=30),
            status=InvoiceStatus.SENT,
        )
        payment = Payment.objects.create(
            invoice=invoice, amount=Decimal('400.00'), payment_date=date.today(),
            method=PaymentMethod.CASH,
        )
        mail.outbox = []
        notify_directors_of_payment(payment, recorded_by=director_user)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [director_user.email]
        assert 'pending@example.com' not in mail.outbox[0].to

    def test_notify_directors_of_payment_no_directors_does_not_raise(self, contract):
        """Cabinet with no approved DIRECTOR — best-effort, silent no-op."""
        from revenue.models import Invoice, Payment
        from revenue.notifications import notify_directors_of_payment

        invoice = Invoice.objects.create(
            contract=contract, invoice_number='INV-NOTIFY-2', amount=Decimal('1000.00'),
            issued_date=date.today(), due_date=date.today() + timedelta(days=30),
            status=InvoiceStatus.SENT,
        )
        payment = Payment.objects.create(
            invoice=invoice, amount=Decimal('100.00'), payment_date=date.today(),
            method=PaymentMethod.CASH,
        )
        mail.outbox = []
        notify_directors_of_payment(payment)  # should not raise
        assert len(mail.outbox) == 0

    def test_payment_create_view_triggers_director_notification(self, cashier_client, cashier_user, cabinet, contract, director_user):
        from revenue.models import Invoice
        invoice = Invoice.objects.create(
            contract=contract, invoice_number='INV-NOTIFY-3', amount=Decimal('1000.00'),
            issued_date=date.today(), due_date=date.today() + timedelta(days=30),
            status=InvoiceStatus.SENT,
        )
        mail.outbox = []
        response = cashier_client.post(reverse('revenue:payment_create', kwargs={'invoice_id': invoice.pk}), {
            'invoice': invoice.pk, 'amount': '250.00', 'payment_date': date.today(),
            'method': PaymentMethod.CASH, 'reference': 'REF-X',
        }, follow=True)
        assert response.status_code == 200
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [director_user.email]


# ============================================================================
# Contrat: solde client automatique
# ============================================================================

@pytest.mark.django_db
class TestContractClientBalance:

    def test_total_paid_and_client_balance(self, contract):
        from revenue.models import Invoice, Payment
        invoice = Invoice.objects.create(
            contract=contract, invoice_number='INV-BAL-1', amount=Decimal('20000.00'),
            issued_date=date.today(), due_date=date.today() + timedelta(days=30),
            status=InvoiceStatus.SENT,
        )
        Payment.objects.create(invoice=invoice, amount=Decimal('5000.00'), payment_date=date.today(), method=PaymentMethod.CASH)
        Payment.objects.create(invoice=invoice, amount=Decimal('3000.00'), payment_date=date.today(), method=PaymentMethod.CASH)

        assert contract.total_paid == Decimal('8000.00')
        assert contract.client_balance == contract.total_value - Decimal('8000.00')

    def test_client_balance_with_no_payments_equals_total_value(self, contract):
        assert contract.total_paid == 0
        assert contract.client_balance == contract.total_value


# ============================================================================
# Devis: photo alternative to manual line entry
# ============================================================================

def _devis_management_form(total=0, initial=0):
    return {
        'lines-TOTAL_FORMS': str(total),
        'lines-INITIAL_FORMS': str(initial),
        'lines-MIN_NUM_FORMS': '0',
        'lines-MAX_NUM_FORMS': '1000',
    }


@pytest.mark.django_db
class TestDevisPhotoAlternative:

    def test_create_with_photo_skips_line_requirement(self, director_client, site, sample_image_file):
        data = {
            'site': site.pk, 'devis_number': 'DEV-PHOTO-1', 'client_name': 'Client Photo',
            'issue_date': date.today(), 'notes': '', 'photo': sample_image_file,
        }
        data.update(_devis_management_form(total=0))
        # Django's test Client has no separate `files=` kwarg — a file-like
        # value inside `data` is what triggers multipart encoding.
        response = director_client.post(
            reverse('revenue:devis_create'), data, follow=True,
        )
        assert response.status_code == 200
        from revenue.models import Devis
        devis = Devis.objects.get(devis_number='DEV-PHOTO-1')
        assert devis.photo
        assert devis.total_items == 0

    def test_create_without_photo_requires_at_least_one_line(self, director_client, site):
        data = {
            'site': site.pk, 'devis_number': 'DEV-NOPHOTO-1', 'client_name': 'Client',
            'issue_date': date.today(), 'notes': '',
        }
        data.update(_devis_management_form(total=0))
        response = director_client.post(reverse('revenue:devis_create'), data, follow=True)
        assert response.status_code == 200
        from revenue.models import Devis
        assert not Devis.objects.filter(devis_number='DEV-NOPHOTO-1').exists()

    def test_update_with_photo_skips_line_requirement(self, director_client, site, sample_image_file):
        from revenue.models import Devis
        devis = Devis.objects.create(
            site=site, devis_number='DEV-UPD-1', client_name='Client',
            issue_date=date.today(),
        )
        data = {
            'site': site.pk, 'devis_number': 'DEV-UPD-1', 'client_name': 'Client',
            'issue_date': date.today(), 'notes': '', 'photo': sample_image_file,
        }
        data.update(_devis_management_form(total=0))
        response = director_client.post(
            reverse('revenue:devis_update', kwargs={'pk': devis.pk}), data, follow=True,
        )
        assert response.status_code == 200
        devis.refresh_from_db()
        assert devis.photo
