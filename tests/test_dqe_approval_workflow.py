"""Tests for the 2026-10-19 "devis global" approval workflow (meeting-
note backlog, ACGT Congo — section "Devis global du chantier"):

- The client's "devis global" maps onto the existing DQE structure
  (étape-organized lines with per-étape subtotals — see
  tests/test_devis_phase_structure.py for the equivalent now built onto
  Devis itself) plus a richer, dedicated approval workflow:
  Brouillon → En attente d'approbation → Approuvé | Rejeté — replacing
  DQEStatus's previous complete lack of a model-level transition check
  (DQEUpdateView could set any value freely before this).
- Who approves: the client said "probablement DG ou Directeur
  Technique, à confirmer" — implemented as DQE_APPROVAL_ROLES
  (DIRECTOR/DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL), narrower than who
  may edit/submit a DQE (PRICING_ADMIN_ROLES, which also includes
  CHIEF_ENGINEER).
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from pricing.models import DQE
from chantiermobile.constants import DQEStatus, UserRoles, ApprovalStatus


@pytest.fixture
def dqe(db, cabinet, site):
    return DQE.objects.create(cabinet=cabinet, site=site, reference='DQE-APPR-001', title='Devis global test', status=DQEStatus.DRAFT)


@pytest.fixture
def chief_engineer_user(db, cabinet):
    from django.contrib.auth import get_user_model
    from accounts.models import UserCabinetRole
    User = get_user_model()
    user = User.objects.create_user(username='chief_eng', email='chief_eng@example.com', password='testpass123')
    UserCabinetRole.objects.create(user=user, cabinet=cabinet, role=UserRoles.CHIEF_ENGINEER, status=ApprovalStatus.APPROVED)
    return user


@pytest.fixture
def chief_engineer_client(client, chief_engineer_user):
    client.login(username='chief_eng', password='testpass123')
    return client


@pytest.mark.django_db
class TestDQEStatusTransitions:
    """Model-level clean() transition table."""

    def test_draft_can_move_to_en_attente_approbation(self, dqe):
        dqe.status = DQEStatus.EN_ATTENTE_APPROBATION
        dqe.full_clean()  # does not raise

    def test_draft_can_still_move_directly_to_legacy_validated(self, dqe):
        """Backward compatibility: flows that don't use the approval
        workflow at all keep working."""
        dqe.status = DQEStatus.VALIDATED
        dqe.full_clean()  # does not raise

    def test_en_attente_approbation_cannot_jump_to_validated(self, dqe):
        dqe.status = DQEStatus.EN_ATTENTE_APPROBATION
        dqe.full_clean()
        dqe.save()
        dqe.status = DQEStatus.VALIDATED
        with pytest.raises(ValidationError):
            dqe.full_clean()

    def test_approuve_is_terminal_except_for_archiving(self, dqe):
        dqe.status = DQEStatus.EN_ATTENTE_APPROBATION
        dqe.full_clean()
        dqe.save()
        dqe.status = DQEStatus.APPROUVE
        dqe.full_clean()
        dqe.save()
        dqe.status = DQEStatus.EN_ATTENTE_APPROBATION
        with pytest.raises(ValidationError):
            dqe.full_clean()

    def test_rejete_can_go_back_to_draft_for_resubmission(self, dqe):
        dqe.status = DQEStatus.EN_ATTENTE_APPROBATION
        dqe.full_clean()
        dqe.save()
        dqe.status = DQEStatus.REJETE
        dqe.full_clean()
        dqe.save()
        dqe.status = DQEStatus.DRAFT
        dqe.full_clean()  # does not raise


@pytest.mark.django_db
class TestDQEWorkflowMethods:
    def test_submit_for_approval_from_draft(self, dqe, user):
        dqe.submit_for_approval(changed_by=user)
        assert dqe.status == DQEStatus.EN_ATTENTE_APPROBATION

    def test_submit_for_approval_rejects_wrong_status(self, dqe, user):
        dqe.status = DQEStatus.APPROUVE
        dqe.save()
        with pytest.raises(ValidationError):
            dqe.submit_for_approval(changed_by=user)

    def test_approve_from_en_attente(self, dqe, user):
        dqe.submit_for_approval(changed_by=user)
        dqe.approve(changed_by=user)
        assert dqe.status == DQEStatus.APPROUVE

    def test_approve_rejects_wrong_status(self, dqe, user):
        with pytest.raises(ValidationError):
            dqe.approve(changed_by=user)

    def test_reject_records_reason(self, dqe, user):
        dqe.submit_for_approval(changed_by=user)
        dqe.reject(changed_by=user, reason='Prix non à jour.')
        assert dqe.status == DQEStatus.REJETE
        assert dqe.rejection_reason == 'Prix non à jour.'

    def test_rejection_reason_cleared_on_eventual_approval(self, dqe, user):
        """A resubmit-then-approve cycle shouldn't leave a stale
        rejection reason from the earlier rejection sitting around."""
        dqe.submit_for_approval(changed_by=user)
        dqe.reject(changed_by=user, reason='Corriger les quantités.')
        dqe.submit_for_approval(changed_by=user)
        dqe.approve(changed_by=user)
        assert dqe.rejection_reason == ''


@pytest.mark.django_db
class TestDQEApprovalViews:
    def test_director_can_submit_for_approval(self, director_client, dqe):
        response = director_client.post(reverse('pricing:dqe_submit_for_approval', kwargs={'pk': dqe.pk}))
        assert response.status_code == 302
        dqe.refresh_from_db()
        assert dqe.status == DQEStatus.EN_ATTENTE_APPROBATION

    def test_accountant_cannot_submit_for_approval(self, accountant_client, dqe):
        response = accountant_client.post(reverse('pricing:dqe_submit_for_approval', kwargs={'pk': dqe.pk}))
        assert response.status_code == 302
        dqe.refresh_from_db()
        assert dqe.status == DQEStatus.DRAFT

    def test_director_can_approve(self, director_client, dqe, user):
        dqe.submit_for_approval(changed_by=user)
        response = director_client.post(reverse('pricing:dqe_approve', kwargs={'pk': dqe.pk}))
        assert response.status_code == 302
        dqe.refresh_from_db()
        assert dqe.status == DQEStatus.APPROUVE

    def test_chief_engineer_can_submit_but_cannot_approve(self, chief_engineer_client, dqe, user):
        """CHIEF_ENGINEER is in PRICING_ADMIN_ROLES (can edit/submit a
        DQE) but not in DQE_APPROVAL_ROLES (cannot sign off on it) —
        the approval step is reserved for DG/Directeur Technique."""
        submit_response = chief_engineer_client.post(reverse('pricing:dqe_submit_for_approval', kwargs={'pk': dqe.pk}))
        assert submit_response.status_code == 302
        dqe.refresh_from_db()
        assert dqe.status == DQEStatus.EN_ATTENTE_APPROBATION

        approve_response = chief_engineer_client.post(reverse('pricing:dqe_approve', kwargs={'pk': dqe.pk}))
        assert approve_response.status_code == 302
        dqe.refresh_from_db()
        assert dqe.status == DQEStatus.EN_ATTENTE_APPROBATION  # unchanged

    def test_director_can_reject_with_a_reason(self, director_client, dqe, user):
        dqe.submit_for_approval(changed_by=user)
        response = director_client.post(
            reverse('pricing:dqe_reject', kwargs={'pk': dqe.pk}), {'reason': 'Montants à revoir.'},
        )
        assert response.status_code == 302
        dqe.refresh_from_db()
        assert dqe.status == DQEStatus.REJETE
        assert dqe.rejection_reason == 'Montants à revoir.'
