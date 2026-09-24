"""
Tests for item 14 of the Directors/Engineers audit: there was no
attendance/pointage tracking at all — Expense.personnel and
PayrollListItem existed, but nothing recorded who actually showed up on
a given day, which is what a chef de chantier fills in every morning in
practice. personnel.models.Attendance + AttendanceDailyView (bulk entry,
one row per assigned worker) and AttendanceHistoryView (read-only log)
close that gap.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.urls import reverse

from accounts.models import Cabinet, UserCabinetRole
from chantiermobile.constants import UserRoles, ApprovalStatus, AttendanceStatus
from personnel.models import SiteAssignment, Attendance


@pytest.fixture
def crew(site, personnel_factory):
    a = personnel_factory(first_name='Amani', last_name='Tshimanga')
    b = personnel_factory(first_name='Beatrice', last_name='Ngoy')
    SiteAssignment.objects.create(personnel=a, site=site, role='Maçon', start_date=date.today() - timedelta(days=30), daily_rate=Decimal('15.00'))
    SiteAssignment.objects.create(personnel=b, site=site, role='Manœuvre', start_date=date.today() - timedelta(days=30), daily_rate=Decimal('10.00'))
    return a, b


@pytest.mark.django_db
class TestAttendanceDailyView:
    def test_director_sees_one_row_per_assigned_worker(self, director_client, site, crew):
        response = director_client.get(reverse('personnel:attendance_daily', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 200
        rows = response.context['rows']
        assert len(rows) == 2
        assert all(r['status'] == AttendanceStatus.PRESENT for r in rows)

    def test_submitting_attendance_creates_records(self, director_client, site, crew):
        a, b = crew
        today = date.today()
        response = director_client.post(
            reverse('personnel:attendance_daily', kwargs={'unique_id': site.unique_id}),
            {
                'date': today.isoformat(),
                f'status_{a.pk}': AttendanceStatus.PRESENT,
                f'status_{b.pk}': AttendanceStatus.ABSENT,
                f'notes_{b.pk}': 'Congé maladie non déclaré',
            },
        )
        assert response.status_code == 302
        record_a = Attendance.objects.get(personnel=a, site=site, date=today)
        record_b = Attendance.objects.get(personnel=b, site=site, date=today)
        assert record_a.status == AttendanceStatus.PRESENT
        assert record_b.status == AttendanceStatus.ABSENT
        assert record_b.notes == 'Congé maladie non déclaré'

    def test_resubmitting_same_day_updates_not_duplicates(self, director_client, site, crew):
        a, b = crew
        today = date.today()
        url = reverse('personnel:attendance_daily', kwargs={'unique_id': site.unique_id})
        director_client.post(url, {'date': today.isoformat(), f'status_{a.pk}': AttendanceStatus.PRESENT, f'status_{b.pk}': AttendanceStatus.PRESENT})
        director_client.post(url, {'date': today.isoformat(), f'status_{a.pk}': AttendanceStatus.RETARD, f'status_{b.pk}': AttendanceStatus.PRESENT})

        assert Attendance.objects.filter(personnel=a, site=site, date=today).count() == 1
        assert Attendance.objects.get(personnel=a, site=site, date=today).status == AttendanceStatus.RETARD

    def test_engineer_can_record_attendance_for_own_site(self, engineer_client, engineer_user, site, crew):
        site.lead_engineer = engineer_user
        site.save()
        response = engineer_client.get(reverse('personnel:attendance_daily', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 200
        assert len(response.context['rows']) == 2

    def test_engineer_cannot_record_attendance_for_a_site_they_dont_lead(self, engineer_client, site, crew):
        response = engineer_client.get(reverse('personnel:attendance_daily', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 302
        assert response['Location'] == reverse('projects:site_detail', kwargs={'unique_id': site.unique_id})

    def test_worker_cannot_record_attendance(self, client, cabinet, site, django_user_model, crew):
        worker = django_user_model.objects.create_user(username='worker_attendance', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        client.login(username='worker_attendance', password='testpass123')

        response = client.get(reverse('personnel:attendance_daily', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 302


@pytest.mark.django_db
class TestAttendanceHistoryView:
    def test_history_lists_recorded_attendance(self, director_client, site, crew, user):
        a, b = crew
        Attendance.objects.create(personnel=a, site=site, date=date.today(), status=AttendanceStatus.PRESENT, recorded_by=user)
        Attendance.objects.create(personnel=b, site=site, date=date.today(), status=AttendanceStatus.ABSENT, recorded_by=user)

        response = director_client.get(reverse('personnel:attendance_history', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 200
        assert len(response.context['records']) == 2

    def test_history_scoped_to_site(self, director_client, site, site_factory, personnel_factory, user):
        other_site = site_factory(name='Autre chantier')
        other_person = personnel_factory(first_name='Claude', last_name='Ilunga')
        Attendance.objects.create(personnel=other_person, site=other_site, date=date.today(), status=AttendanceStatus.PRESENT, recorded_by=user)

        response = director_client.get(reverse('personnel:attendance_history', kwargs={'unique_id': site.unique_id}))
        assert list(response.context['records']) == []
