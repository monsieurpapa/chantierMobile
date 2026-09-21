"""
Tests for the Administration/HR module additions (Phase A of the ATGC
proposal build-out): Personnel status/category/trade/monthly_salary,
worker "dossier" documents, congés (leave) and jours fériés (holidays),
and SiteAssignment labor-agreement fields.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import UserCabinetRole
from chantiermobile.constants import UserRoles, ApprovalStatus, PersonnelStatus, AgentCategory, Trade, LeaveType
from personnel.models import Personnel, PersonnelDocument, Leave, Holiday, SiteAssignment


@pytest.mark.django_db
class TestPersonnelFields:
    def test_new_fields_have_sane_defaults(self, personnel_factory):
        p = personnel_factory()
        assert p.status == PersonnelStatus.ACTIF
        assert p.category == AgentCategory.TERRAIN
        assert p.trade == ''
        assert p.monthly_salary is None
        assert p.is_eligible is True

    def test_trade_and_monthly_salary_can_be_set(self, personnel_factory):
        p = personnel_factory(trade=Trade.MACON, monthly_salary=Decimal('450.00'), category=AgentCategory.ADMINISTRATION)
        assert p.trade == Trade.MACON
        assert p.monthly_salary == Decimal('450.00')
        assert p.category == AgentCategory.ADMINISTRATION

    def test_inactive_worker_is_not_eligible(self, personnel_factory):
        p = personnel_factory(status=PersonnelStatus.NON_ELIGIBLE)
        assert p.is_eligible is False


@pytest.mark.django_db
class TestPersonnelListFilters:
    def test_status_filter(self, director_client, cabinet, personnel_factory):
        personnel_factory(first_name='Active', status=PersonnelStatus.ACTIF)
        personnel_factory(first_name='Inactive', status=PersonnelStatus.INACTIF)
        response = director_client.get(reverse('personnel:personnel_list'), {'status': 'INACTIF'})
        assert response.status_code == 200
        names = [p.first_name for p in response.context['personnel_list']]
        assert names == ['Inactive']

    def test_trade_filter(self, director_client, personnel_factory):
        personnel_factory(first_name='Mason', trade=Trade.MACON)
        personnel_factory(first_name='Painter', trade=Trade.PEINTRE)
        response = director_client.get(reverse('personnel:personnel_list'), {'trade': 'PEINTRE'})
        names = [p.first_name for p in response.context['personnel_list']]
        assert names == ['Painter']


@pytest.mark.django_db
class TestPersonnelDocuments:
    def test_director_can_upload_document(self, director_client, personnel_factory):
        p = personnel_factory()
        f = SimpleUploadedFile("cni.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        url = reverse('personnel:document_create', kwargs={'unique_id': p.unique_id})
        response = director_client.post(url, {'label': 'Copie CNI', 'file': f})
        assert response.status_code == 302
        assert PersonnelDocument.objects.filter(personnel=p, label='Copie CNI').exists()

    def test_worker_cannot_upload_document(self, client, cabinet, personnel_factory, django_user_model):
        worker = django_user_model.objects.create_user(username='worker1', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        client.login(username='worker1', password='testpass123')
        p = personnel_factory()
        f = SimpleUploadedFile("cni.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        url = reverse('personnel:document_create', kwargs={'unique_id': p.unique_id})
        response = client.post(url, {'label': 'Copie CNI', 'file': f})
        assert response.status_code == 302
        assert not PersonnelDocument.objects.filter(personnel=p).exists()

    def test_document_from_other_cabinet_is_protected(self, client, django_user_model, cabinet, personnel_factory):
        """A DIRECTOR in one cabinet must not delete another cabinet's document."""
        from accounts.models import Cabinet
        other_cabinet = Cabinet.objects.create(name='Other Cabinet', address='x', tax_id='OTH')
        other_director = django_user_model.objects.create_user(username='other_director', password='testpass123')
        UserCabinetRole.objects.create(user=other_director, cabinet=other_cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)

        p = personnel_factory(cabinet=cabinet)
        doc = PersonnelDocument.objects.create(personnel=p, label='Contrat', file=SimpleUploadedFile("c.pdf", b"x"))

        client.login(username='other_director', password='testpass123')
        response = client.post(reverse('personnel:document_delete', kwargs={'pk': doc.pk}))
        assert response.status_code in (302, 403)
        assert PersonnelDocument.objects.filter(pk=doc.pk).exists()


@pytest.mark.django_db
class TestLeaveWorkflow:
    def test_director_can_declare_leave(self, director_client, personnel_factory):
        p = personnel_factory()
        url = reverse('personnel:leave_create')
        response = director_client.post(url, {
            'personnel': p.pk,
            'leave_type': LeaveType.CONGE,
            'start_date': date.today(),
            'end_date': date.today() + timedelta(days=5),
            'reason': 'Congé annuel',
        })
        assert response.status_code == 302
        leave = Leave.objects.get(personnel=p)
        assert leave.status == ApprovalStatus.PENDING
        assert leave.duration_days == 6

    def test_end_before_start_is_rejected(self, director_client, personnel_factory):
        p = personnel_factory()
        response = director_client.post(reverse('personnel:leave_create'), {
            'personnel': p.pk,
            'leave_type': LeaveType.CONGE,
            'start_date': date.today(),
            'end_date': date.today() - timedelta(days=1),
            'reason': 'Invalid',
        })
        assert response.status_code == 200  # form redisplayed with errors
        assert not Leave.objects.filter(personnel=p).exists()

    def test_director_can_approve_leave(self, director_client, user, personnel_factory):
        p = personnel_factory()
        leave = Leave.objects.create(
            personnel=p, leave_type=LeaveType.CONGE,
            start_date=date.today(), end_date=date.today() + timedelta(days=2),
        )
        response = director_client.post(reverse('personnel:leave_approve', kwargs={'pk': leave.pk}))
        assert response.status_code == 302
        leave.refresh_from_db()
        assert leave.status == ApprovalStatus.APPROVED
        assert leave.decided_by == user
        assert leave.decided_at is not None

    def test_engineer_cannot_approve_leave(self, engineer_client, personnel_factory):
        p = personnel_factory()
        leave = Leave.objects.create(
            personnel=p, leave_type=LeaveType.CONGE,
            start_date=date.today(), end_date=date.today() + timedelta(days=2),
        )
        response = engineer_client.post(reverse('personnel:leave_approve', kwargs={'pk': leave.pk}))
        leave.refresh_from_db()
        assert leave.status == ApprovalStatus.PENDING


@pytest.mark.django_db
class TestHolidays:
    def test_director_can_add_holiday(self, director_client, cabinet):
        response = director_client.post(reverse('personnel:holiday_create'), {
            'name': "Fête de l'indépendance",
            'date': date(date.today().year, 6, 30),
        })
        assert response.status_code == 302
        assert Holiday.objects.filter(cabinet=cabinet, name="Fête de l'indépendance").exists()

    def test_holiday_list_scoped_to_cabinet(self, director_client, cabinet):
        from accounts.models import Cabinet
        other_cabinet = Cabinet.objects.create(name='Other', address='x', tax_id='OTH2')
        Holiday.objects.create(cabinet=cabinet, name='Mine', date=date.today())
        Holiday.objects.create(cabinet=other_cabinet, name='Theirs', date=date.today())
        response = director_client.get(reverse('personnel:holiday_list'))
        names = [h.name for h in response.context['holiday_list']]
        assert names == ['Mine']


@pytest.mark.django_db
class TestSiteAssignmentAgreement:
    def test_assignment_can_carry_agreement_document(self, personnel_factory, site):
        p = personnel_factory()
        f = SimpleUploadedFile("convention.pdf", b"%PDF-1.4", content_type="application/pdf")
        assignment = SiteAssignment.objects.create(
            personnel=p, site=site, role='Chef de chantier',
            start_date=date.today(), daily_rate=Decimal('20.00'),
            agreement_document=f, agreement_notes='Paiement hebdomadaire',
        )
        assert assignment.agreement_document.name
        assert assignment.agreement_notes == 'Paiement hebdomadaire'
