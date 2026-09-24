"""
Tests for the invoice send/cancel workflow (revenue.views.invoice_send /
invoice_cancel) added to close a real dead end: an invoice created through
InvoiceCreateView always started life as DRAFT (the model's own default —
'status' was removed from InvoiceForm's editable fields, see forms.py),
and there was no InvoiceUpdateView and no other action anywhere that could
ever move it out of DRAFT. PaymentCreateView's own invoice queryset only
ever offers SENT/OVERDUE invoices, so a DRAFT invoice was permanently
unpayable through the UI before this.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta

from django.urls import reverse

from chantiermobile.constants import InvoiceStatus
from revenue.models import Invoice
from core.models import StatusChangeLog


@pytest.mark.django_db
class TestInvoiceForm:
    def test_status_is_not_an_editable_field(self):
        """Every other status-driven workflow in this app (Devis,
        SituationTravaux, MaterialRequest, Expense...) changes status only
        through a dedicated action endpoint, never a raw dropdown on the
        create form — Invoice should be no exception."""
        from revenue.forms import InvoiceForm
        assert 'status' not in InvoiceForm.Meta.fields

    def test_invoice_created_through_the_view_always_starts_draft(self, accountant_client, contract):
        response = accountant_client.post(
            reverse('revenue:invoice_create_from_contract', kwargs={'contract_id': contract.pk}),
            {
                'contract': contract.pk,
                'invoice_number': 'INV-FORM-001',
                'amount': '5000.00',
                'issued_date': date.today(),
                'due_date': date.today() + timedelta(days=30),
                # Even if a client tried to slip a 'status' param in, the
                # form doesn't declare that field, so it's simply ignored.
                'status': InvoiceStatus.SENT,
            },
        )
        invoice = Invoice.objects.get(invoice_number='INV-FORM-001')
        assert invoice.status == InvoiceStatus.DRAFT


@pytest.mark.django_db
class TestInvoiceSend:
    def test_director_can_send_a_draft_invoice(self, director_client, invoice):
        assert invoice.status == InvoiceStatus.DRAFT
        response = director_client.post(reverse('revenue:invoice_send', kwargs={'pk': invoice.pk}))
        assert response.status_code == 302
        invoice.refresh_from_db()
        assert invoice.status == InvoiceStatus.SENT

    def test_accountant_can_send_a_draft_invoice(self, accountant_client, invoice):
        response = accountant_client.post(reverse('revenue:invoice_send', kwargs={'pk': invoice.pk}))
        invoice.refresh_from_db()
        assert invoice.status == InvoiceStatus.SENT

    def test_sending_logs_a_status_change(self, director_client, invoice):
        director_client.post(reverse('revenue:invoice_send', kwargs={'pk': invoice.pk}))
        log = StatusChangeLog.objects.filter(object_id=invoice.pk).latest('changed_at')
        assert log.old_status == InvoiceStatus.DRAFT
        assert log.new_status == InvoiceStatus.SENT

    def test_cannot_send_an_already_sent_invoice(self, director_client, invoice_factory):
        invoice = invoice_factory(status=InvoiceStatus.SENT, invoice_number='INV-002')
        response = director_client.post(reverse('revenue:invoice_send', kwargs={'pk': invoice.pk}))
        assert response.status_code == 302
        invoice.refresh_from_db()
        assert invoice.status == InvoiceStatus.SENT  # unchanged, not double-logged

    def test_cannot_send_a_paid_invoice(self, director_client, invoice_factory):
        invoice = invoice_factory(status=InvoiceStatus.PAID, invoice_number='INV-003')
        director_client.post(reverse('revenue:invoice_send', kwargs={'pk': invoice.pk}))
        invoice.refresh_from_db()
        assert invoice.status == InvoiceStatus.PAID

    def test_engineer_cannot_send_an_invoice(self, engineer_client, invoice):
        """ENGINEER isn't in INVOICE_ACTION_ROLES — billing stays with
        Director/Accountant, same circle as who can create an invoice."""
        response = engineer_client.post(reverse('revenue:invoice_send', kwargs={'pk': invoice.pk}))
        assert response.status_code == 302
        invoice.refresh_from_db()
        assert invoice.status == InvoiceStatus.DRAFT

    def test_get_request_does_not_send(self, director_client, invoice):
        """This is a state-changing action — only POST should have any effect."""
        director_client.get(reverse('revenue:invoice_send', kwargs={'pk': invoice.pk}))
        invoice.refresh_from_db()
        assert invoice.status == InvoiceStatus.DRAFT


@pytest.mark.django_db
class TestInvoiceCancel:
    def test_director_can_cancel_a_draft_invoice(self, director_client, invoice):
        response = director_client.post(reverse('revenue:invoice_cancel', kwargs={'pk': invoice.pk}))
        assert response.status_code == 302
        invoice.refresh_from_db()
        assert invoice.status == InvoiceStatus.CANCELLED

    def test_cancelling_logs_a_status_change(self, director_client, invoice):
        director_client.post(reverse('revenue:invoice_cancel', kwargs={'pk': invoice.pk}))
        log = StatusChangeLog.objects.filter(object_id=invoice.pk).latest('changed_at')
        assert log.old_status == InvoiceStatus.DRAFT
        assert log.new_status == InvoiceStatus.CANCELLED

    def test_cannot_cancel_a_sent_invoice(self, director_client, invoice_factory):
        """Matches Invoice.clean()'s valid_transitions — SENT can only go
        to PAID/OVERDUE, not CANCELLED, once a client has already seen it."""
        invoice = invoice_factory(status=InvoiceStatus.SENT, invoice_number='INV-004')
        director_client.post(reverse('revenue:invoice_cancel', kwargs={'pk': invoice.pk}))
        invoice.refresh_from_db()
        assert invoice.status == InvoiceStatus.SENT

    def test_engineer_cannot_cancel_an_invoice(self, engineer_client, invoice):
        engineer_client.post(reverse('revenue:invoice_cancel', kwargs={'pk': invoice.pk}))
        invoice.refresh_from_db()
        assert invoice.status == InvoiceStatus.DRAFT


@pytest.mark.django_db
class TestInvoicePayableAfterSend:
    """End-to-end: the whole point of invoice_send is that it unblocks the
    payment flow PaymentCreateView already had, which only ever accepted
    SENT/OVERDUE invoices."""

    def test_draft_invoice_is_not_offered_on_the_payment_form(self, accountant_client, invoice):
        response = accountant_client.get(reverse('revenue:payment_create_standalone'))
        assert invoice not in response.context['form'].fields['invoice'].queryset

    def test_sent_invoice_is_offered_and_payable(self, accountant_client, invoice):
        accountant_client.post(reverse('revenue:invoice_send', kwargs={'pk': invoice.pk}))
        invoice.refresh_from_db()

        response = accountant_client.get(reverse('revenue:payment_create_standalone'))
        assert invoice in response.context['form'].fields['invoice'].queryset

        response = accountant_client.post(reverse('revenue:payment_create', kwargs={'invoice_id': invoice.pk}), {
            'invoice': invoice.pk,
            'amount': str(invoice.amount),
            'payment_date': date.today(),
            'method': 'CASH',
            'reference': 'FULL-PAYMENT',
        })
        assert response.status_code == 302
        invoice.refresh_from_db()
        assert invoice.status == InvoiceStatus.PAID
