"""Tests for the 2026-10-19 "Notifications et séparation des étapes"
feature (meeting-note backlog):

- Notifications: the technical team is now notified automatically when
  a rapport d'avancement (SiteProgress) is submitted — the client's own
  wording left "l'équipe technique" undefined, so TECHNICAL_TEAM_ROLES
  (projects/views.py) defaults to director-tier + ENGINEER/CHIEF_ENGINEER,
  the same membership already used for PLANNING_REVIEW_ROLES elsewhere
  in this module.
- Gros Œuvre / Finissage split: ProjectPhase gets an optional `category`
  tag (GROS_OEUVRE / FINISSAGE) — a deliberately simple default since the
  client's own note pointed to an undelivered reference file ("voir
  fichier Ir Brave") for the exact split wanted.
"""
from datetime import date

import pytest
from django.urls import reverse

from accounts.models import UserCabinetRole
from core.models import Notification
from projects.models import ProjectPhase
from chantiermobile.constants import UserRoles, ApprovalStatus, PhaseCategory


@pytest.fixture
def engineer_on_site(client, cabinet, django_user_model):
    """A second cabinet member (plain ENGINEER) distinct from
    `director_client`'s own user, so we can check they get notified of
    the director's rapport submission without notifying themselves."""
    user = django_user_model.objects.create_user(username='notif_engineer', password='testpass123')
    UserCabinetRole.objects.create(user=user, cabinet=cabinet, role=UserRoles.ENGINEER, status=ApprovalStatus.APPROVED)
    return user


@pytest.mark.django_db
class TestRapportSubmissionNotifiesTechnicalTeam:
    def test_submitting_a_progress_report_notifies_the_technical_team(self, director_client, user, phase, engineer_on_site):
        response = director_client.post(
            reverse('projects:progress_create', kwargs={'phase_id': phase.unique_id}),
            {'report_date': date.today(), 'percentage_complete': '40', 'description': 'Coulage des semelles terminé'},
        )
        assert response.status_code == 302

        notifications = Notification.objects.filter(recipient=engineer_on_site)
        assert notifications.exists()
        assert phase.name in notifications.first().message

        # The submitter doesn't notify themselves.
        assert not Notification.objects.filter(recipient=user).exists()


@pytest.mark.django_db
class TestProjectPhaseCategory:
    def test_phase_category_defaults_to_blank(self, site, phase_factory):
        phase = phase_factory(site, name='Fondation')
        assert phase.category == ''

    def test_phase_can_be_tagged_gros_oeuvre_or_finissage(self, site, phase_factory):
        gros_oeuvre = phase_factory(site, name='Fondation', category=PhaseCategory.GROS_OEUVRE)
        finissage = phase_factory(site, name='Peinture', category=PhaseCategory.FINISSAGE)
        assert gros_oeuvre.category == PhaseCategory.GROS_OEUVRE
        assert finissage.category == PhaseCategory.FINISSAGE

    def test_category_badge_shown_on_site_detail_page(self, director_client, site, phase_factory):
        phase_factory(site, name='Fondation', category=PhaseCategory.GROS_OEUVRE)
        phase_factory(site, name='Peinture murs', category=PhaseCategory.FINISSAGE)
        response = director_client.get(reverse('projects:site_detail', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Gros œuvre' in content
        assert 'Finissage' in content

    def test_phase_create_form_accepts_category(self, director_client, site):
        response = director_client.post(
            reverse('projects:phase_create', kwargs={'site_id': site.unique_id}),
            {'name': 'Carrelage', 'category': PhaseCategory.FINISSAGE, 'start_date': date.today()},
        )
        assert response.status_code == 302
        assert ProjectPhase.objects.get(name='Carrelage').category == PhaseCategory.FINISSAGE
