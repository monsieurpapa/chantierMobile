"""
Tests for the Gestion des projets gaps closed in this phase: assigning a
lead engineer to a site, submitting a planning for review by the
concerned engineer(s), and the lead engineer closing out project phases.
"""
import pytest
from datetime import date
from django.urls import reverse
from django.core.exceptions import ValidationError

from projects.models import Site, ProjectPhase, PlanningSubmission
from chantiermobile.constants import PlanningStatus, PhaseStatus


@pytest.mark.django_db
class TestSiteLeadEngineer:
    def test_assign_lead_engineer(self, site, engineer_user):
        site.lead_engineer = engineer_user
        site.save()
        site.refresh_from_db()
        assert site.lead_engineer == engineer_user

    def test_director_can_assign_lead_engineer_via_view(self, director_client, site, engineer_user):
        response = director_client.post(reverse('projects:site_update', kwargs={'unique_id': site.unique_id}), {
            'name': site.name, 'location': site.location, 'status': site.status,
            'lead_engineer': engineer_user.pk,
        })
        assert response.status_code == 302
        site.refresh_from_db()
        assert site.lead_engineer == engineer_user


@pytest.mark.django_db
class TestProjectPhaseClosure:
    def test_close_sets_fields(self, site, user):
        phase = ProjectPhase.objects.create(site=site, name='Fondations')
        assert not phase.is_closed
        phase.close(user, notes='Travaux terminés')
        phase.refresh_from_db()
        assert phase.is_closed
        assert phase.status == PhaseStatus.CLOTUREE
        assert phase.closed_by == user
        assert phase.closed_at is not None
        assert phase.closure_notes == 'Travaux terminés'

    def test_cannot_close_twice(self, site, user):
        phase = ProjectPhase.objects.create(site=site, name='Fondations')
        phase.close(user)
        with pytest.raises(ValidationError):
            phase.close(user)

    def test_engineer_can_close_phase_view(self, engineer_client, engineer_user, site):
        phase = ProjectPhase.objects.create(site=site, name='Toiture')
        response = engineer_client.post(reverse('projects:phase_close', kwargs={'unique_id': phase.unique_id}), {
            'notes': 'OK',
        })
        assert response.status_code == 302
        phase.refresh_from_db()
        assert phase.is_closed
        assert phase.closed_by == engineer_user

    def test_worker_cannot_close_phase(self, client, cabinet, site, django_user_model):
        from accounts.models import UserCabinetRole
        from chantiermobile.constants import UserRoles, ApprovalStatus
        worker = django_user_model.objects.create_user(username='worker_phase', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        phase = ProjectPhase.objects.create(site=site, name='Plomberie')

        client.login(username='worker_phase', password='testpass123')
        response = client.post(reverse('projects:phase_close', kwargs={'unique_id': phase.unique_id}), {'notes': ''})
        assert response.status_code == 302
        phase.refresh_from_db()
        assert not phase.is_closed


@pytest.mark.django_db
class TestPlanningSubmission:
    def test_submit_then_approve(self, site, user, engineer_user):
        submission = PlanningSubmission.objects.create(site=site, description='Plan de la semaine 1')
        assert submission.status == PlanningStatus.BROUILLON
        submission.submit(user)
        submission.refresh_from_db()
        assert submission.status == PlanningStatus.SOUMISE
        assert submission.submitted_by == user

        submission.approve(engineer_user, notes='Validé')
        submission.refresh_from_db()
        assert submission.status == PlanningStatus.APPROUVEE
        assert submission.reviewed_by == engineer_user

    def test_reject(self, site, user, engineer_user):
        submission = PlanningSubmission.objects.create(site=site, description='Plan incomplet')
        submission.submit(user)
        submission.reject(engineer_user, notes='À revoir')
        submission.refresh_from_db()
        assert submission.status == PlanningStatus.REJETEE

    def test_cannot_submit_twice(self, site, user):
        submission = PlanningSubmission.objects.create(site=site, description='x')
        submission.submit(user)
        with pytest.raises(ValidationError):
            submission.submit(user)

    def test_cannot_review_a_draft(self, site, engineer_user):
        submission = PlanningSubmission.objects.create(site=site, description='x')
        with pytest.raises(ValidationError):
            submission.approve(engineer_user)

    def test_director_can_create_and_submit_via_view(self, director_client, site):
        response = director_client.post(reverse('projects:planning_submission_create', kwargs={'site_id': site.unique_id}), {
            'phase': '', 'description': 'Planification initiale du chantier',
        })
        assert response.status_code == 302
        submission = PlanningSubmission.objects.get(site=site)
        assert submission.status == PlanningStatus.SOUMISE

    def test_engineer_can_approve_via_view(self, engineer_client, engineer_user, site, user):
        submission = PlanningSubmission.objects.create(site=site, description='x')
        submission.submit(user)
        response = engineer_client.post(reverse('projects:planning_submission_approve', kwargs={'pk': submission.pk}), {
            'notes': 'ok',
        })
        assert response.status_code == 302
        submission.refresh_from_db()
        assert submission.status == PlanningStatus.APPROUVEE

    def test_worker_cannot_approve_via_view(self, client, cabinet, site, django_user_model, user):
        from accounts.models import UserCabinetRole
        from chantiermobile.constants import UserRoles, ApprovalStatus
        worker = django_user_model.objects.create_user(username='worker_plan', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        submission = PlanningSubmission.objects.create(site=site, description='x')
        submission.submit(user)

        client.login(username='worker_plan', password='testpass123')
        response = client.post(reverse('projects:planning_submission_approve', kwargs={'pk': submission.pk}), {'notes': ''})
        submission.refresh_from_db()
        assert submission.status == PlanningStatus.SOUMISE
