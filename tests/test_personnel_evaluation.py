"""Tests for the 2026-10-19 "Évaluation du personnel par étape" feature
(meeting-note backlog): the Ingénieur en Chef (and, per the standing
default, director-tier — HR_ADMIN_ROLES) can cote a worker per étape
from their profile page, and every cotation is kept as its own
append-only history row rather than a single mutable score.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import UserCabinetRole
from personnel.models import PersonnelEvaluation, SiteAssignment
from chantiermobile.constants import UserRoles, ApprovalStatus, EvaluationMention

User = get_user_model()


@pytest.fixture
def chief_engineer_user(db, cabinet):
    user = User.objects.create_user(username='chief_eng', email='chief_eng@example.com', password='testpass123')
    UserCabinetRole.objects.create(user=user, cabinet=cabinet, role=UserRoles.CHIEF_ENGINEER, status=ApprovalStatus.APPROVED)
    return user


@pytest.fixture
def chief_engineer_client(client, chief_engineer_user):
    client.login(username='chief_eng', password='testpass123')
    return client


@pytest.fixture
def plain_engineer_user(db, cabinet):
    user = User.objects.create_user(username='plain_eng', email='plain_eng@example.com', password='testpass123')
    UserCabinetRole.objects.create(user=user, cabinet=cabinet, role=UserRoles.ENGINEER, status=ApprovalStatus.APPROVED)
    return user


@pytest.fixture
def plain_engineer_client(client, plain_engineer_user):
    client.login(username='plain_eng', password='testpass123')
    return client


@pytest.fixture
def assigned_personnel(db, personnel, site):
    """`personnel` with a real history on `site`, so phase-site checks
    pass."""
    SiteAssignment.objects.create(personnel=personnel, site=site, role='Ouvrier', start_date='2026-01-01', daily_rate=Decimal('10'))
    return personnel


@pytest.mark.django_db
class TestPersonnelEvaluationModel:
    def test_requires_at_least_one_rating_dimension(self, assigned_personnel, phase):
        evaluation = PersonnelEvaluation(personnel=assigned_personnel, phase=phase, observation='Bon travail')
        with pytest.raises(ValidationError):
            evaluation.full_clean()

    def test_numeric_note_alone_is_valid(self, assigned_personnel, phase):
        evaluation = PersonnelEvaluation(personnel=assigned_personnel, phase=phase, observation='Bon travail', note_chiffree=15)
        evaluation.full_clean()  # must not raise

    def test_mention_alone_is_valid(self, assigned_personnel, phase):
        evaluation = PersonnelEvaluation(
            personnel=assigned_personnel, phase=phase, observation='Bon travail',
            mention_qualitative=EvaluationMention.BON,
        )
        evaluation.full_clean()  # must not raise

    def test_note_above_20_is_rejected(self, assigned_personnel, phase):
        evaluation = PersonnelEvaluation(personnel=assigned_personnel, phase=phase, observation='x', note_chiffree=25)
        with pytest.raises(ValidationError):
            evaluation.full_clean()

    def test_phase_from_unrelated_site_is_rejected_at_model_level(self, personnel, phase):
        """`personnel` here has NO SiteAssignment at all (unlike
        `assigned_personnel`) — the model-level history check should
        catch this when personnel_id is already set, e.g. direct ORM use."""
        evaluation = PersonnelEvaluation(personnel=personnel, phase=phase, observation='x', note_chiffree=10)
        with pytest.raises(ValidationError):
            evaluation.full_clean()

    def test_multiple_evaluations_are_kept_as_separate_history_rows(self, assigned_personnel, phase):
        PersonnelEvaluation.objects.create(personnel=assigned_personnel, phase=phase, observation='Premier passage', note_chiffree=10)
        PersonnelEvaluation.objects.create(personnel=assigned_personnel, phase=phase, observation='Deuxième passage', note_chiffree=16)
        assert assigned_personnel.evaluations.count() == 2


@pytest.mark.django_db
class TestPersonnelEvaluationCreateView:
    def test_chief_engineer_can_submit_an_evaluation(self, chief_engineer_client, assigned_personnel, phase):
        response = chief_engineer_client.post(
            reverse('personnel:evaluation_create', kwargs={'unique_id': assigned_personnel.unique_id}),
            {'phase': phase.pk, 'note_chiffree': '14', 'mention_qualitative': '', 'observation': 'Travail soigné sur la semelle.'},
        )
        assert response.status_code == 302, getattr(response, 'context', None) and response.context['form'].errors
        evaluation = assigned_personnel.evaluations.get()
        assert evaluation.note_chiffree == 14
        assert evaluation.evaluated_by_id is not None

    def test_plain_engineer_cannot_submit_an_evaluation(self, plain_engineer_client, assigned_personnel, phase):
        response = plain_engineer_client.post(
            reverse('personnel:evaluation_create', kwargs={'unique_id': assigned_personnel.unique_id}),
            {'phase': phase.pk, 'note_chiffree': '14', 'observation': 'x'},
        )
        # RoleRequiredMixin bounces back with a flash message rather than
        # raising a hard 403 — see core/mixins.py's dispatch() docstring.
        assert response.status_code == 302
        assert assigned_personnel.evaluations.count() == 0

    def test_missing_both_rating_dimensions_is_rejected(self, chief_engineer_client, assigned_personnel, phase):
        response = chief_engineer_client.post(
            reverse('personnel:evaluation_create', kwargs={'unique_id': assigned_personnel.unique_id}),
            {'phase': phase.pk, 'observation': 'x'},
        )
        assert response.status_code == 200
        assert assigned_personnel.evaluations.count() == 0

    def test_phase_from_a_site_personnel_never_worked_on_is_rejected(self, chief_engineer_client, personnel, phase):
        """`personnel` (not `assigned_personnel`) has no SiteAssignment at
        all — caught by the form's own site-history check (see
        PersonnelEvaluationForm.clean())."""
        response = chief_engineer_client.post(
            reverse('personnel:evaluation_create', kwargs={'unique_id': personnel.unique_id}),
            {'phase': phase.pk, 'note_chiffree': '10', 'observation': 'x'},
        )
        assert response.status_code == 200
        assert personnel.evaluations.count() == 0

    def test_evaluation_history_shown_on_personnel_detail_page(self, chief_engineer_client, assigned_personnel, phase):
        PersonnelEvaluation.objects.create(personnel=assigned_personnel, phase=phase, observation='Excellent coffrage', note_chiffree=18)
        response = chief_engineer_client.get(reverse('personnel:personnel_detail', kwargs={'unique_id': assigned_personnel.unique_id}))
        assert response.status_code == 200
        assert 'Excellent coffrage'.encode() in response.content
        assert b'18/20' in response.content
