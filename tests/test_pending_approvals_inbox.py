"""
Tests for item 12 of the Directors/Engineers audit: there was no single
place to see everything awaiting your decision — a director had to check
the expense list, material request list, avenant list, each site's
planning tab, and the leave list separately, each filtered to "pending"
by hand. core.approvals.get_pending_approvals() (surfaced at
/approbations/) aggregates all of it, scoped to exactly what the viewer
could actually act on if they clicked through — these tests check that
scoping mirrors each action view's own role/status checks.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.urls import reverse

from accounts.models import UserCabinetRole
from chantiermobile.constants import (
    UserRoles, ApprovalStatus, ExpenseStatus, MaterialRequestStatus, AvenantStatus, PlanningStatus,
)
from finance.models import Expense, ExpenseCategory, Avenant
from materials.models import Material, MaterialRequest, MaterialRequestItem
from projects.models import PlanningSubmission


@pytest.fixture
def expense_category(db):
    return ExpenseCategory.objects.create(name='Matériaux')


@pytest.fixture
def pending_expense(db, site, user, expense_category):
    return Expense.objects.create(
        site=site, requester=user, category=expense_category,
        amount=Decimal('500.00'), expense_date=date.today(),
        description='Ciment', status=ExpenseStatus.PENDING,
    )


@pytest.fixture
def magasinier_client(client, cabinet, django_user_model):
    magasinier = django_user_model.objects.create_user(username='magasinier_inbox', password='testpass123')
    UserCabinetRole.objects.create(user=magasinier, cabinet=cabinet, role=UserRoles.MAGASINIER, status=ApprovalStatus.APPROVED)
    client.login(username='magasinier_inbox', password='testpass123')
    return client


@pytest.fixture
def dt_client(client, cabinet, django_user_model):
    dt = django_user_model.objects.create_user(username='dt_inbox', password='testpass123')
    UserCabinetRole.objects.create(user=dt, cabinet=cabinet, role=UserRoles.DIRECTEUR_TECHNIQUE, status=ApprovalStatus.APPROVED)
    client.login(username='dt_inbox', password='testpass123')
    return client


@pytest.mark.django_db
class TestPendingApprovalsInbox:
    def test_director_sees_pending_expense(self, director_client, pending_expense):
        response = director_client.get(reverse('pending_approvals'))
        assert response.status_code == 200
        types = [a['type'] for a in response.context['approvals']]
        assert 'expense' in types

    def test_worker_sees_empty_inbox(self, client, cabinet, django_user_model, pending_expense):
        worker = django_user_model.objects.create_user(username='worker_inbox', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        client.login(username='worker_inbox', password='testpass123')

        response = client.get(reverse('pending_approvals'))
        assert response.status_code == 200
        assert response.context['approvals'] == []

    def test_magasinier_sees_pending_but_not_validated_material_request(self, magasinier_client, site):
        material = Material.objects.create(name='Sable', unit='m3')
        pending_req = MaterialRequest.objects.create(site=site, status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=pending_req, material=material, quantity=Decimal('2.00'))
        validated_req = MaterialRequest.objects.create(site=site, status=MaterialRequestStatus.VALIDATED)
        MaterialRequestItem.objects.create(request=validated_req, material=material, quantity=Decimal('2.00'))

        response = magasinier_client.get(reverse('pending_approvals'))
        review_urls = [a['review_url'] for a in response.context['approvals']]
        assert reverse('materials:request_detail', kwargs={'pk': pending_req.pk}) in review_urls
        assert reverse('materials:request_detail', kwargs={'pk': validated_req.pk}) not in review_urls

    def test_directeur_technique_sees_both_pending_and_validated_material_requests(self, dt_client, site):
        """DIRECTEUR_TECHNIQUE is in both MATERIAL_REQUEST_VALIDATE_ROLES
        (magasinier_validate) and FINAL_AUTHORIZATION_ROLES (authorize) —
        unlike a plain MAGASINIER, they can act at either stage."""
        material = Material.objects.create(name='Sable', unit='m3')
        pending_req = MaterialRequest.objects.create(site=site, status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=pending_req, material=material, quantity=Decimal('2.00'))
        validated_req = MaterialRequest.objects.create(site=site, status=MaterialRequestStatus.VALIDATED)
        MaterialRequestItem.objects.create(request=validated_req, material=material, quantity=Decimal('2.00'))

        response = dt_client.get(reverse('pending_approvals'))
        review_urls = [a['review_url'] for a in response.context['approvals']]
        assert reverse('materials:request_detail', kwargs={'pk': validated_req.pk}) in review_urls
        assert reverse('materials:request_detail', kwargs={'pk': pending_req.pk}) in review_urls

    def test_accountant_does_not_see_material_requests_or_avenants(self, accountant_client, site):
        material = Material.objects.create(name='Sable', unit='m3')
        pending_req = MaterialRequest.objects.create(site=site, status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=pending_req, material=material, quantity=Decimal('2.00'))
        Avenant.objects.create(site=site, amount=Decimal('1000.00'), justification='x', status=AvenantStatus.PENDING)

        response = accountant_client.get(reverse('pending_approvals'))
        types = [a['type'] for a in response.context['approvals']]
        assert 'material_request' not in types
        assert 'avenant' not in types

    def test_engineer_sees_others_planning_submission_but_not_their_own(self, engineer_client, engineer_user, site, user):
        others_submission = PlanningSubmission.objects.create(site=site, description='Plan du directeur')
        others_submission.submit(user)
        own_submission = PlanningSubmission.objects.create(site=site, description="Plan de l'ingénieur")
        own_submission.submit(engineer_user)

        response = engineer_client.get(reverse('pending_approvals'))
        review_urls = [a['review_url'] for a in response.context['approvals'] if a['type'] == 'planning']
        site_url = reverse('projects:site_detail', kwargs={'unique_id': site.unique_id})
        # Both submissions point at the same site page, so instead check the
        # count directly: only the director's submission should be pickable.
        planning_items = [a for a in response.context['approvals'] if a['type'] == 'planning']
        assert len(planning_items) == 1
        assert planning_items[0]['requested_by_name'] == user.get_full_name()

    def test_pending_approvals_scoped_to_cabinet(self, director_client, cabinet, site_factory, user):
        """Regression guard mirroring TestBudgetCabinetScoping: a director
        of cabinet A must not see cabinet B's pending expense."""
        from accounts.models import Cabinet
        other_cabinet = Cabinet.objects.create(name='Autre Cabinet')
        other_site = site_factory(cabinet=other_cabinet)
        category = ExpenseCategory.objects.create(name='Autre')
        other_expense = Expense.objects.create(
            site=other_site, category=category, amount=Decimal('300.00'),
            expense_date=date.today(), description='x', status=ExpenseStatus.PENDING,
        )

        response = director_client.get(reverse('pending_approvals'))
        review_urls = [a['review_url'] for a in response.context['approvals']]
        assert reverse('finance:expense_detail', kwargs={'pk': other_expense.pk}) not in review_urls
