"""Tests for the 2026-10-19 "Ingénieurs : affectation, historique,
profils" feature (meeting-note backlog):

- The Ingénieur en Chef's need (où est affecté le personnel, son
  historique, ses cotes liées à chaque étape) is already served by the
  existing Personnel detail page (assignments table with start/end
  dates — "Present" for an ongoing one — plus the cotation history
  added alongside this feature); nothing new was needed there.
- The DG's need is net-new: a free-form `experience_notes` field
  ("compétences et expérience" — the client left open whether this
  should be structured fields or free text already captured elsewhere;
  a single text field is the reasonable default, with the existing
  `skills` M2M covering the structured "compétences" side already), and
  a full-profile PDF export gated to DIRECTOR_ROLES and to an actual
  ingénieur (payroll_type), matching "chaque ingénieur" literally.
"""
from decimal import Decimal
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import UserCabinetRole
from personnel.models import SiteAssignment, PersonnelEvaluation
from chantiermobile.constants import UserRoles, ApprovalStatus, PersonnelPayrollType

User = get_user_model()


@pytest.fixture
def engineer_personnel(db, cabinet, personnel_factory):
    return personnel_factory(
        first_name='Jean', last_name='Ingenieur',
        payroll_type=PersonnelPayrollType.INGENIEUR,
        experience_notes='10 ans d\'expérience en structures béton armé.',
    )


@pytest.fixture
def other_cabinet_director_client(client, db):
    from accounts.models import Cabinet
    other_cabinet = Cabinet.objects.create(name='Autre Cabinet')
    user = User.objects.create_user(username='other_dir', password='testpass123')
    UserCabinetRole.objects.create(user=user, cabinet=other_cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
    client.login(username='other_dir', password='testpass123')
    return client


@pytest.mark.django_db
class TestPersonnelDetailShowsAffectationAndCotationHistory:
    """The Ingénieur en Chef's need — already covered by existing
    machinery plus the cotation history from the companion feature."""

    def test_assignment_history_shows_ongoing_and_past_periods(self, director_client, engineer_personnel, site, site_factory):
        past_site = site_factory(name='Ancien chantier')
        SiteAssignment.objects.create(
            personnel=engineer_personnel, site=past_site, role='Ingénieur',
            start_date=date(2025, 1, 1), end_date=date(2025, 6, 1), daily_rate=Decimal('50'),
        )
        SiteAssignment.objects.create(
            personnel=engineer_personnel, site=site, role='Ingénieur',
            start_date=date(2026, 1, 1), daily_rate=Decimal('50'),
        )
        response = director_client.get(reverse('personnel:personnel_detail', kwargs={'unique_id': engineer_personnel.unique_id}))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Ancien chantier' in content
        assert site.name in content
        assert 'Present' in content  # ongoing assignment has no end_date

    def test_cotation_history_shown_on_profile(self, director_client, engineer_personnel, site, phase_factory):
        phase = phase_factory(site)
        SiteAssignment.objects.create(personnel=engineer_personnel, site=site, role='Ingénieur', start_date=date(2026, 1, 1), daily_rate=Decimal('50'))
        PersonnelEvaluation.objects.create(personnel=engineer_personnel, phase=phase, observation='Supervision rigoureuse', note_chiffree=17)
        response = director_client.get(reverse('personnel:personnel_detail', kwargs={'unique_id': engineer_personnel.unique_id}))
        assert response.status_code == 200
        assert 'Supervision rigoureuse'.encode() in response.content


@pytest.mark.django_db
class TestEngineerProfilePdfExport:
    def test_director_tier_sees_pdf_button_for_an_engineer(self, director_client, engineer_personnel):
        response = director_client.get(reverse('personnel:personnel_detail', kwargs={'unique_id': engineer_personnel.unique_id}))
        assert response.status_code == 200
        assert 'Profil PDF'.encode() in response.content

    def test_pdf_button_hidden_for_a_non_engineer(self, director_client, personnel):
        # `personnel` fixture defaults to OUVRIER payroll_type.
        response = director_client.get(reverse('personnel:personnel_detail', kwargs={'unique_id': personnel.unique_id}))
        assert response.status_code == 200
        assert 'Profil PDF'.encode() not in response.content

    def test_director_can_download_the_pdf(self, director_client, engineer_personnel, site, phase_factory):
        phase = phase_factory(site)
        SiteAssignment.objects.create(personnel=engineer_personnel, site=site, role='Ingénieur', start_date=date(2026, 1, 1), daily_rate=Decimal('50'))
        PersonnelEvaluation.objects.create(personnel=engineer_personnel, phase=phase, observation='Bon', note_chiffree=15)
        response = director_client.get(reverse('personnel:personnel_profile_pdf', kwargs={'unique_id': engineer_personnel.unique_id}))
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'
        assert len(response.content) > 0

    def test_engineer_tier_user_cannot_download_the_pdf(self, engineer_client, engineer_personnel):
        response = engineer_client.get(reverse('personnel:personnel_profile_pdf', kwargs={'unique_id': engineer_personnel.unique_id}))
        assert response.status_code == 302
        assert response['Content-Type'] != 'application/pdf' if 'Content-Type' in response else True

    def test_director_from_another_cabinet_cannot_download_the_pdf(self, other_cabinet_director_client, engineer_personnel):
        response = other_cabinet_director_client.get(reverse('personnel:personnel_profile_pdf', kwargs={'unique_id': engineer_personnel.unique_id}))
        assert response.status_code == 302
