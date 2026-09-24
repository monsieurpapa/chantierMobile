"""
Tests for item 15 (PDF export half) of the Directors/Engineers audit:
invoices, contracts, payroll lists and salary payment lists had no PDF
export — a director needing to hand a client an invoice or file a payroll
list on paper had no way to print one from the app. All four now reuse
core.pdf_utils.render_table_report_pdf (already used for expense/caisse/
achats/stock reports): invoice and contract exports render as a simple
"Champ/Valeur" document, payroll and salary-payment exports render as a
one-row-per-line-item table.

These tests check permission/cabinet scoping (mirroring each detail
view's own access rule) and that each endpoint actually returns a PDF.
"""
import pytest
from datetime import date
from decimal import Decimal
from django.urls import reverse

from accounts.models import Cabinet, UserCabinetRole
from chantiermobile.constants import UserRoles, ApprovalStatus
from finance.models import PayrollList, PayrollListItem, SalaryPaymentList, SalaryPaymentItem


@pytest.mark.django_db
class TestInvoicePdfExport:
    def test_director_can_export_invoice_pdf(self, director_client, invoice):
        response = director_client.get(reverse('revenue:invoice_pdf', kwargs={'pk': invoice.pk}))
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'

    def test_invoice_pdf_blocked_for_other_cabinet(self, client, django_user_model, invoice):
        other_cabinet = Cabinet.objects.create(name='Autre Cabinet')
        outsider = django_user_model.objects.create_user(username='outsider_inv', password='testpass123')
        UserCabinetRole.objects.create(user=outsider, cabinet=other_cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
        client.login(username='outsider_inv', password='testpass123')

        response = client.get(reverse('revenue:invoice_pdf', kwargs={'pk': invoice.pk}))
        assert response.status_code == 302
        assert response['Content-Type'] != 'application/pdf'

    def test_invoice_detail_page_shows_export_link(self, director_client, invoice):
        response = director_client.get(reverse('revenue:invoice_detail', kwargs={'pk': invoice.pk}))
        assert response.status_code == 200
        assert reverse('revenue:invoice_pdf', kwargs={'pk': invoice.pk}) in response.content.decode()


@pytest.mark.django_db
class TestContractPdfExport:
    def test_director_can_export_contract_pdf(self, director_client, contract):
        response = director_client.get(reverse('revenue:contract_pdf', kwargs={'pk': contract.pk}))
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'

    def test_contract_pdf_blocked_for_other_cabinet(self, client, django_user_model, contract):
        other_cabinet = Cabinet.objects.create(name='Autre Cabinet 2')
        outsider = django_user_model.objects.create_user(username='outsider_contract', password='testpass123')
        UserCabinetRole.objects.create(user=outsider, cabinet=other_cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
        client.login(username='outsider_contract', password='testpass123')

        response = client.get(reverse('revenue:contract_pdf', kwargs={'pk': contract.pk}))
        assert response.status_code == 302
        assert response['Content-Type'] != 'application/pdf'

    def test_contract_list_shows_export_link(self, director_client, contract):
        response = director_client.get(reverse('revenue:contract_list'))
        assert response.status_code == 200
        assert reverse('revenue:contract_pdf', kwargs={'pk': contract.pk}) in response.content.decode()


@pytest.mark.django_db
class TestPayrollPdfExport:
    def test_director_can_export_payroll_pdf(self, director_client, site, personnel_factory):
        payroll_list = PayrollList.objects.create(site=site)
        person = personnel_factory()
        PayrollListItem.objects.create(payroll_list=payroll_list, personnel=person, amount=Decimal('150.00'))

        response = director_client.get(reverse('finance:payroll_detail_pdf', kwargs={'pk': payroll_list.pk}))
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'

    def test_worker_cannot_export_payroll_pdf(self, client, cabinet, site, django_user_model):
        payroll_list = PayrollList.objects.create(site=site)
        worker = django_user_model.objects.create_user(username='worker_payroll_pdf', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        client.login(username='worker_payroll_pdf', password='testpass123')

        response = client.get(reverse('finance:payroll_detail_pdf', kwargs={'pk': payroll_list.pk}))
        assert response.status_code == 302
        assert response['Content-Type'] != 'application/pdf'

    def test_payroll_detail_page_shows_export_link(self, director_client, site):
        payroll_list = PayrollList.objects.create(site=site)
        response = director_client.get(reverse('finance:payroll_detail', kwargs={'pk': payroll_list.pk}))
        assert response.status_code == 200
        assert reverse('finance:payroll_detail_pdf', kwargs={'pk': payroll_list.pk}) in response.content.decode()


@pytest.mark.django_db
class TestSalaryPaymentPdfExport:
    def test_director_can_export_salary_payment_pdf(self, director_client, cabinet, personnel_factory):
        spl = SalaryPaymentList.objects.create(cabinet=cabinet)
        person = personnel_factory()
        SalaryPaymentItem.objects.create(salary_payment_list=spl, personnel=person, period='2026-09', amount=Decimal('500.00'))

        response = director_client.get(reverse('finance:salary_payment_detail_pdf', kwargs={'pk': spl.pk}))
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'

    def test_worker_cannot_export_salary_payment_pdf(self, client, cabinet, django_user_model):
        spl = SalaryPaymentList.objects.create(cabinet=cabinet)
        worker = django_user_model.objects.create_user(username='worker_salary_pdf', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        client.login(username='worker_salary_pdf', password='testpass123')

        response = client.get(reverse('finance:salary_payment_detail_pdf', kwargs={'pk': spl.pk}))
        assert response.status_code == 302
        assert response['Content-Type'] != 'application/pdf'

    def test_salary_payment_detail_page_shows_export_link(self, director_client, cabinet):
        spl = SalaryPaymentList.objects.create(cabinet=cabinet)
        response = director_client.get(reverse('finance:salary_payment_detail', kwargs={'pk': spl.pk}))
        assert response.status_code == 200
        assert reverse('finance:salary_payment_detail_pdf', kwargs={'pk': spl.pk}) in response.content.decode()
