"""
Tests for item 6 of the Directors/Engineers audit: an ENGINEER previously
had no way to assign personnel to their own site, or to declare leave for
their own crew — SiteAssignmentCreateView and LeaveCreateView both
required HR_ADMIN_ROLES (DIRECTOR-tier or CHIEF_ENGINEER only). The fix
adds ENGINEER to their allowed roles, but scopes what they can actually
submit to their own led site(s) — Site.lead_engineer — rather than
handing them the same cabinet-wide reach HR_ADMIN_ROLES has (assigning
anyone to any site, holidays, any personnel's dossier, deciding anyone's
leave).
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.urls import reverse

from accounts.models import UserCabinetRole
from personnel.models import Personnel, SiteAssignment, Leave
from chantiermobile.constants import UserRoles, ApprovalStatus


@pytest.fixture
def personnel_factory(db, cabinet):
    def create(**kwargs):
        defaults = {
            'first_name': 'Jean', 'last_name': 'Ouvrier',
            'default_daily_rate': Decimal('10.00'), 'cabinet': cabinet,
        }
        defaults.update(kwargs)
        return Personnel.objects.create(**defaults)
    return create


@pytest.mark.django_db
class TestEngineerSiteAssignment:
    def test_engineer_can_assign_personnel_to_own_site(self, engineer_client, engineer_user, site, personnel_factory):
        site.lead_engineer = engineer_user
        site.save(update_fields=['lead_engineer'])
        person = personnel_factory()

        response = engineer_client.post(reverse('personnel:assignment_create'), {
            'personnel': person.pk, 'site': site.pk, 'role': 'Maçon',
            'start_date': date.today().isoformat(), 'daily_rate': '15.00',
        })
        assert response.status_code == 302
        assert SiteAssignment.objects.filter(site=site, personnel=person).exists()

    def test_engineer_cannot_assign_to_a_site_they_dont_lead(self, engineer_client, site, personnel_factory):
        """site.lead_engineer is left unset, so this engineer has no claim
        on it even though they belong to the same cabinet."""
        person = personnel_factory()

        response = engineer_client.post(reverse('personnel:assignment_create'), {
            'personnel': person.pk, 'site': site.pk, 'role': 'Maçon',
            'start_date': date.today().isoformat(), 'daily_rate': '15.00',
        })
        assert response.status_code == 200  # form re-rendered: site not a valid choice
        assert not SiteAssignment.objects.filter(site=site, personnel=person).exists()

    def test_worker_still_blocked_from_assignment_create(self, client, cabinet, django_user_model):
        worker = django_user_model.objects.create_user(username='worker_assign', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        client.login(username='worker_assign', password='testpass123')

        response = client.get(reverse('personnel:assignment_create'))
        assert response.status_code == 302

    def test_director_still_assigns_to_any_site(self, director_client, site, personnel_factory):
        """Regression guard: full-access roles are unaffected."""
        person = personnel_factory()

        response = director_client.post(reverse('personnel:assignment_create'), {
            'personnel': person.pk, 'site': site.pk, 'role': "Chef d'équipe",
            'start_date': date.today().isoformat(), 'daily_rate': '20.00',
        })
        assert response.status_code == 302
        assert SiteAssignment.objects.filter(site=site, personnel=person).exists()


@pytest.mark.django_db
class TestEngineerLeave:
    def test_engineer_can_declare_leave_for_own_crew(self, engineer_client, engineer_user, site, personnel_factory):
        site.lead_engineer = engineer_user
        site.save(update_fields=['lead_engineer'])
        person = personnel_factory()
        SiteAssignment.objects.create(personnel=person, site=site, role='Maçon', start_date=date.today(), daily_rate=Decimal('15.00'))

        response = engineer_client.post(reverse('personnel:leave_create'), {
            'personnel': person.pk, 'leave_type': 'CONGE',
            'start_date': date.today().isoformat(),
            'end_date': (date.today() + timedelta(days=2)).isoformat(),
            'reason': 'Congé annuel',
        })
        assert response.status_code == 302
        assert Leave.objects.filter(personnel=person).exists()

    def test_engineer_cannot_declare_leave_for_someone_outside_their_crew(self, engineer_client, personnel_factory):
        person = personnel_factory()  # no assignment to any site this engineer leads

        response = engineer_client.post(reverse('personnel:leave_create'), {
            'personnel': person.pk, 'leave_type': 'CONGE',
            'start_date': date.today().isoformat(),
            'end_date': (date.today() + timedelta(days=2)).isoformat(),
            'reason': 'x',
        })
        assert response.status_code == 200  # form re-rendered: personnel not a valid choice
        assert not Leave.objects.filter(personnel=person).exists()

    def test_engineer_still_cannot_decide_leave(self, engineer_client, engineer_user, site, personnel_factory):
        """Creating a leave is now open to an engineer for their own crew,
        but deciding (approve/reject) one stays an HR_ADMIN_ROLES action —
        no self-review-style shortcut here."""
        site.lead_engineer = engineer_user
        site.save(update_fields=['lead_engineer'])
        person = personnel_factory()
        SiteAssignment.objects.create(personnel=person, site=site, role='Maçon', start_date=date.today(), daily_rate=Decimal('15.00'))
        leave = Leave.objects.create(personnel=person, leave_type='CONGE', start_date=date.today(), end_date=date.today() + timedelta(days=1))

        response = engineer_client.post(reverse('personnel:leave_approve', kwargs={'pk': leave.pk}))
        assert response.status_code == 302
        leave.refresh_from_db()
        assert leave.status == ApprovalStatus.PENDING

    def test_director_can_still_declare_leave_for_anyone(self, director_client, personnel_factory):
        """Regression guard: full-access roles are unaffected."""
        person = personnel_factory()

        response = director_client.post(reverse('personnel:leave_create'), {
            'personnel': person.pk, 'leave_type': 'CONGE',
            'start_date': date.today().isoformat(),
            'end_date': (date.today() + timedelta(days=2)).isoformat(),
            'reason': 'x',
        })
        assert response.status_code == 302
        assert Leave.objects.filter(personnel=person).exists()
