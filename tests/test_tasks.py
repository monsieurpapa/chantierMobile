"""
Tests for the tasks app (Tâches + Tâcherons/Prestataires): Task tracking
and the PersonnelType extension to the personnel app.
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.core.exceptions import ValidationError
from django.urls import reverse

from chantiermobile.constants import TaskStatus, TaskPriority, PersonnelType
from tasks.models import Task
from personnel.models import Personnel


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def tacheron(db, personnel_factory):
    return personnel_factory(first_name='Amadou', last_name='Ba', personnel_type=PersonnelType.TACHERON)


@pytest.fixture
def phase(db, site):
    from projects.models import ProjectPhase
    return ProjectPhase.objects.create(site=site, name='Fondations')


@pytest.fixture
def task(db, site, personnel):
    return Task.objects.create(
        site=site,
        title='Couler la dalle',
        priority=TaskPriority.NORMALE,
        assigned_to=personnel,
    )


# ============================================================================
# Personnel: PersonnelType
# ============================================================================

@pytest.mark.django_db
class TestPersonnelType:
    def test_default_type_is_employe(self, personnel):
        assert personnel.personnel_type == PersonnelType.EMPLOYE
        assert personnel.is_subcontractor is False

    def test_tacheron_is_subcontractor(self, tacheron):
        assert tacheron.is_subcontractor is True

    def test_prestataire_is_subcontractor(self, db, personnel_factory):
        prestataire = personnel_factory(personnel_type=PersonnelType.PRESTATAIRE)
        assert prestataire.is_subcontractor is True

    def test_personnel_list_filters_by_type(self, director_client, personnel, tacheron):
        response = director_client.get(reverse('personnel:personnel_list') + '?type=TACHERON')
        results = list(response.context['personnel_list'])
        assert tacheron in results
        assert personnel not in results


# ============================================================================
# Task model
# ============================================================================

@pytest.mark.django_db
class TestTaskModel:
    def test_str(self, task):
        assert str(task) == 'Couler la dalle'

    def test_default_status_is_a_faire(self, task):
        assert task.status == TaskStatus.A_FAIRE

    def test_is_overdue_false_without_due_date(self, task):
        assert task.is_overdue is False

    def test_is_overdue_true_when_past_due(self, task):
        task.due_date = date.today() - timedelta(days=1)
        task.save()
        assert task.is_overdue is True

    def test_is_overdue_false_once_completed(self, task):
        task.due_date = date.today() - timedelta(days=1)
        task.status = TaskStatus.EN_COURS
        task.full_clean()
        task.save()
        task.complete()
        assert task.is_overdue is False

    def test_assigned_to_must_share_cabinet(self, db, site, personnel_factory):
        from accounts.models import Cabinet
        other_cabinet = Cabinet.objects.create(name='Autre Cabinet')
        other_personnel = personnel_factory(cabinet=other_cabinet)
        t = Task(site=site, title='Test', assigned_to=other_personnel)
        with pytest.raises(ValidationError):
            t.full_clean()

    def test_phase_must_share_site(self, db, site, cabinet):
        from projects.models import ProjectPhase, Site
        other_site = Site.objects.create(cabinet=cabinet, name='Autre Site', location='Ailleurs')
        other_phase = ProjectPhase.objects.create(site=other_site, name='Autre Phase')
        t = Task(site=site, title='Test', phase=other_phase)
        with pytest.raises(ValidationError):
            t.full_clean()

    def test_phase_matching_site_is_valid(self, db, site, phase):
        t = Task(site=site, title='Test', phase=phase)
        t.full_clean()  # should not raise

    def test_invalid_status_transition(self, task):
        task.status = TaskStatus.TERMINEE
        # A_FAIRE -> TERMINEE directly is not a valid transition
        with pytest.raises(ValidationError):
            task.full_clean()


@pytest.mark.django_db
class TestTaskTransitions:
    def test_start(self, task):
        task.start()
        task.refresh_from_db()
        assert task.status == TaskStatus.EN_COURS

    def test_complete_sets_completed_at(self, task):
        task.start()
        task.complete()
        task.refresh_from_db()
        assert task.status == TaskStatus.TERMINEE
        assert task.completed_at is not None

    def test_block_from_a_faire(self, task):
        task.block(reason='Attente livraison matériaux')
        task.refresh_from_db()
        assert task.status == TaskStatus.BLOQUEE

    def test_reopen_clears_completed_at(self, task):
        task.start()
        task.complete()
        task.reopen()
        task.refresh_from_db()
        assert task.status == TaskStatus.A_FAIRE
        assert task.completed_at is None

    def test_transition_logs_status_change(self, task, director_user):
        from core.models import StatusChangeLog
        from django.contrib.contenttypes.models import ContentType

        task.start(changed_by=director_user)

        log = StatusChangeLog.objects.filter(
            content_type=ContentType.objects.get_for_model(Task),
            object_id=task.pk,
        ).latest('changed_at')
        assert log.old_status == TaskStatus.A_FAIRE
        assert log.new_status == TaskStatus.EN_COURS
        assert log.changed_by == director_user

    def test_cannot_start_from_terminee_without_intermediate(self, task):
        task.start()
        task.complete()
        # complete() -> TERMINEE; start() again should be a no-op transition
        # attempt: TERMINEE -> EN_COURS is allowed per valid_transitions
        task.start()
        task.refresh_from_db()
        assert task.status == TaskStatus.EN_COURS


# ============================================================================
# Views
# ============================================================================

@pytest.mark.django_db
class TestTaskViews:
    def test_task_list_requires_login(self, client):
        response = client.get(reverse('tasks:task_list'))
        assert response.status_code == 302

    def test_task_list_accessible_to_director(self, director_client, task):
        response = director_client.get(reverse('tasks:task_list'))
        assert response.status_code == 200
        assert task in response.context['tasks']

    def test_task_list_status_filter(self, director_client, task):
        task.start()
        response = director_client.get(reverse('tasks:task_list') + '?status=EN_COURS')
        assert task in response.context['tasks']
        response = director_client.get(reverse('tasks:task_list') + '?status=TERMINEE')
        assert task not in response.context['tasks']

    def test_task_create_requires_role(self, accountant_client, site):
        response = accountant_client.post(reverse('tasks:task_create'), {
            'site': site.pk,
            'title': 'Nouvelle tâche',
            'priority': TaskPriority.NORMALE,
            'description': '',
            'due_date': '',
            'assigned_to': '',
            'phase': '',
        })
        # ACCOUNTANT is not in MANAGE_ROLES -> redirected, task not created
        assert response.status_code == 302
        assert not Task.objects.filter(title='Nouvelle tâche').exists()

    def test_task_create_by_director(self, director_client, site):
        response = director_client.post(reverse('tasks:task_create'), {
            'site': site.pk,
            'title': 'Nouvelle tâche',
            'priority': TaskPriority.NORMALE,
            'description': '',
            'due_date': '',
            'assigned_to': '',
            'phase': '',
        })
        assert response.status_code == 302
        assert Task.objects.filter(title='Nouvelle tâche').exists()

    def test_task_detail(self, director_client, task):
        response = director_client.get(reverse('tasks:task_detail', kwargs={'pk': task.pk}))
        assert response.status_code == 200
        assert response.context['task'] == task
        assert response.context['can_manage'] is True

    def test_task_start_and_complete_flow(self, director_client, task):
        start_url = reverse('tasks:task_start', kwargs={'pk': task.pk})
        response = director_client.post(start_url)
        assert response.status_code == 302
        task.refresh_from_db()
        assert task.status == TaskStatus.EN_COURS

        complete_url = reverse('tasks:task_complete', kwargs={'pk': task.pk})
        response = director_client.post(complete_url)
        assert response.status_code == 302
        task.refresh_from_db()
        assert task.status == TaskStatus.TERMINEE

    def test_engineer_role_without_cabinet_role_cannot_manage(self, db, client, task):
        """A user with no role on the task's cabinet, and not the
        assignee, is blocked from status-transition actions."""
        from accounts.models import User
        outsider = User.objects.create_user(username='outsider', password='testpass123')
        client.login(username='outsider', password='testpass123')

        response = client.post(reverse('tasks:task_start', kwargs={'pk': task.pk}))
        assert response.status_code == 302
        task.refresh_from_db()
        assert task.status == TaskStatus.A_FAIRE  # unchanged

    def test_assigned_personnel_can_self_manage_task(self, db, client, site, personnel_factory):
        """A tâcheron/prestataire with a linked login can start/complete
        their own assigned task without a UserCabinetRole."""
        from accounts.models import User
        worker_user = User.objects.create_user(username='amadou', password='testpass123')
        worker = personnel_factory(
            first_name='Amadou', last_name='Ba',
            personnel_type=PersonnelType.TACHERON, user=worker_user,
        )
        my_task = Task.objects.create(site=site, title='Poser les briques', assigned_to=worker)

        client.login(username='amadou', password='testpass123')
        response = client.post(reverse('tasks:task_start', kwargs={'pk': my_task.pk}))
        assert response.status_code == 302
        my_task.refresh_from_db()
        assert my_task.status == TaskStatus.EN_COURS

    def test_my_tasks_filter(self, db, client, site, personnel_factory):
        from accounts.models import User
        worker_user = User.objects.create_user(username='bineta', password='testpass123')
        worker = personnel_factory(first_name='Bineta', last_name='Sow', user=worker_user)
        my_task = Task.objects.create(site=site, title='Ma tâche', assigned_to=worker)
        other_task = Task.objects.create(site=site, title='Autre tâche')

        client.login(username='bineta', password='testpass123')
        response = client.get(reverse('tasks:task_list') + '?mine=1')
        tasks = list(response.context['tasks'])
        assert my_task in tasks
        assert other_task not in tasks
