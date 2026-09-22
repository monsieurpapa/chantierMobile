"""
Tests for the Gestion des stocks gaps closed in this phase: stock
transfers between sites (with motif/étape), and the two-stage
état-de-besoin approval (magasinier validates, then a Directeur
Technique/Général authorizes).
"""
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse
from django.core.exceptions import ValidationError

from procurement.models import StockItem, StockMovement
from projects.models import ProjectPhase
from materials.models import MaterialRequest, MaterialRequestItem, Material
from chantiermobile.constants import StockMovementType, MaterialRequestStatus


@pytest.fixture
def other_site(db, site_factory):
    return site_factory(name='Autre chantier')


@pytest.fixture
def stock_item(db, site):
    return StockItem.objects.create(site=site, name='Ciment 50kg', unit='sac', quantity_on_hand=Decimal('100.00'))


@pytest.fixture
def magasinier_user(db, cabinet):
    from django.contrib.auth import get_user_model
    from accounts.models import UserCabinetRole
    from chantiermobile.constants import UserRoles, ApprovalStatus
    user = get_user_model().objects.create_user(username='magasinier_stk', password='testpass123')
    UserCabinetRole.objects.create(user=user, cabinet=cabinet, role=UserRoles.MAGASINIER, status=ApprovalStatus.APPROVED)
    return user


@pytest.fixture
def magasinier_client(client, magasinier_user):
    client.login(username='magasinier_stk', password='testpass123')
    return client


@pytest.fixture
def dt_user(db, cabinet):
    from django.contrib.auth import get_user_model
    from accounts.models import UserCabinetRole
    from chantiermobile.constants import UserRoles, ApprovalStatus
    user = get_user_model().objects.create_user(username='dt_stk', password='testpass123')
    UserCabinetRole.objects.create(user=user, cabinet=cabinet, role=UserRoles.DIRECTEUR_TECHNIQUE, status=ApprovalStatus.APPROVED)
    return user


@pytest.fixture
def dt_client(client, dt_user):
    client.login(username='dt_stk', password='testpass123')
    return client


@pytest.mark.django_db
class TestStockTransfer:
    def test_transfer_to_creates_paired_movements(self, stock_item, other_site, user):
        destination = StockItem.objects.create(site=other_site, name='Ciment 50kg', unit='sac')
        out_movement, in_movement = stock_item.transfer_to(destination, Decimal('20.00'), user, motif='Besoin urgent')

        stock_item.refresh_from_db()
        destination.refresh_from_db()
        assert stock_item.quantity_on_hand == Decimal('80.00')
        assert destination.quantity_on_hand == Decimal('20.00')
        assert out_movement.is_transfer_source is True
        assert in_movement.is_transfer_source is False
        assert out_movement.transfer_pair == in_movement
        assert in_movement.transfer_pair == out_movement
        assert out_movement.motif == 'Besoin urgent'

    def test_transfer_with_phase(self, stock_item, other_site, user, site):
        phase = ProjectPhase.objects.create(site=site, name='Gros œuvre')
        destination = StockItem.objects.create(site=other_site, name='Ciment 50kg', unit='sac')
        out_movement, _ = stock_item.transfer_to(destination, Decimal('5.00'), user, phase=phase)
        assert out_movement.phase == phase

    def test_cannot_transfer_to_self(self, stock_item, user):
        with pytest.raises(ValidationError):
            stock_item.transfer_to(stock_item, Decimal('5.00'), user)

    def test_cannot_transfer_more_than_available(self, stock_item, other_site, user):
        destination = StockItem.objects.create(site=other_site, name='Ciment 50kg', unit='sac')
        with pytest.raises(ValidationError):
            stock_item.transfer_to(destination, Decimal('200.00'), user)

    def test_transfer_view_creates_destination_item(self, magasinier_client, stock_item, other_site):
        response = magasinier_client.post(reverse('procurement:stock_transfer_create', kwargs={'pk': stock_item.pk}), {
            'destination_site': other_site.pk, 'quantity': '10.00', 'motif': 'Réaffectation',
        })
        assert response.status_code == 302
        stock_item.refresh_from_db()
        assert stock_item.quantity_on_hand == Decimal('90.00')
        destination = StockItem.objects.get(site=other_site, name=stock_item.name)
        assert destination.quantity_on_hand == Decimal('10.00')

    def test_worker_cannot_transfer(self, client, cabinet, stock_item, other_site, django_user_model):
        from accounts.models import UserCabinetRole
        from chantiermobile.constants import UserRoles, ApprovalStatus
        worker = django_user_model.objects.create_user(username='worker_stk', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        client.login(username='worker_stk', password='testpass123')
        response = client.post(reverse('procurement:stock_transfer_create', kwargs={'pk': stock_item.pk}), {
            'destination_site': other_site.pk, 'quantity': '10.00',
        })
        stock_item.refresh_from_db()
        assert stock_item.quantity_on_hand == Decimal('100.00')


@pytest.mark.django_db
class TestStockMovementMotifAndPhase:
    def test_manual_movement_with_motif_and_phase(self, stock_item, site, user):
        phase = ProjectPhase.objects.create(site=site, name='Fondations')
        movement = StockMovement.objects.create(
            stock_item=stock_item, movement_type=StockMovementType.OUT, quantity=Decimal('3.00'),
            movement_date=date.today(), motif='Consommation chantier', phase=phase, moved_by=user,
        )
        assert movement.motif == 'Consommation chantier'
        assert movement.phase == phase

    def test_phase_must_belong_to_same_site(self, stock_item, other_site, user):
        foreign_phase = ProjectPhase.objects.create(site=other_site, name='Toiture')
        movement = StockMovement(
            stock_item=stock_item, movement_type=StockMovementType.OUT, quantity=Decimal('1.00'),
            movement_date=date.today(), phase=foreign_phase, moved_by=user,
        )
        with pytest.raises(ValidationError):
            movement.full_clean()

    def test_movement_create_view_accepts_motif(self, magasinier_client, stock_item):
        response = magasinier_client.post(reverse('procurement:stock_movement_create', kwargs={'pk': stock_item.pk}), {
            'movement_type': StockMovementType.OUT, 'quantity': '2.00',
            'movement_date': date.today().isoformat(), 'motif': 'Perte', 'notes': '',
        })
        assert response.status_code == 302
        movement = stock_item.movements.first()
        assert movement.motif == 'Perte'


@pytest.mark.django_db
class TestStockReportView:
    def test_magasinier_can_view_report(self, magasinier_client, stock_item):
        response = magasinier_client.get(reverse('procurement:stock_report'))
        assert response.status_code == 200
        assert stock_item in response.context['stock_levels']

    def test_worker_cannot_view_report(self, client, cabinet, django_user_model):
        from accounts.models import UserCabinetRole
        from chantiermobile.constants import UserRoles, ApprovalStatus
        worker = django_user_model.objects.create_user(username='worker_rep', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        client.login(username='worker_rep', password='testpass123')
        response = client.get(reverse('procurement:stock_report'))
        assert response.status_code == 302

    def test_report_pdf(self, magasinier_client, stock_item, user):
        StockMovement.objects.create(
            stock_item=stock_item, movement_type=StockMovementType.OUT, quantity=Decimal('1.00'),
            movement_date=date.today(), moved_by=user,
        )
        response = magasinier_client.get(reverse('procurement:stock_report_pdf'))
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'


@pytest.fixture
def material_request(db, site, user):
    return MaterialRequest.objects.create(site=site, requested_by=user, status=MaterialRequestStatus.PENDING)


@pytest.fixture
def with_item(material_request):
    material = Material.objects.create(name='Sable', unit='m3')
    MaterialRequestItem.objects.create(request=material_request, material=material, quantity=Decimal('5.00'))
    return material_request


@pytest.mark.django_db
class TestMaterialRequestTwoStageApproval:
    def test_magasinier_validate_then_dt_authorize(self, with_item, magasinier_user, dt_user):
        req = with_item
        req.magasinier_validate(magasinier_user)
        req.refresh_from_db()
        assert req.status == MaterialRequestStatus.VALIDATED

        req.authorize(dt_user)
        req.refresh_from_db()
        assert req.status == MaterialRequestStatus.APPROVED

    def test_cannot_authorize_before_validation(self, with_item, dt_user):
        with pytest.raises(ValidationError):
            with_item.authorize(dt_user)

    def test_reject_from_pending(self, with_item, magasinier_user):
        with_item.reject(magasinier_user)
        with_item.refresh_from_db()
        assert with_item.status == MaterialRequestStatus.REJECTED

    def test_reject_from_validated(self, with_item, magasinier_user, dt_user):
        with_item.magasinier_validate(magasinier_user)
        with_item.reject(dt_user)
        with_item.refresh_from_db()
        assert with_item.status == MaterialRequestStatus.REJECTED

    def test_magasinier_can_validate_via_view(self, magasinier_client, with_item):
        response = magasinier_client.post(reverse('materials:request_validate', kwargs={'pk': with_item.pk}), {
            'action': 'validate',
        })
        assert response.status_code == 302
        with_item.refresh_from_db()
        assert with_item.status == MaterialRequestStatus.VALIDATED

    def test_engineer_cannot_validate_via_view(self, engineer_client, with_item):
        response = engineer_client.post(reverse('materials:request_validate', kwargs={'pk': with_item.pk}), {
            'action': 'validate',
        })
        with_item.refresh_from_db()
        assert with_item.status == MaterialRequestStatus.PENDING

    def test_dt_can_authorize_via_view(self, dt_client, with_item, magasinier_user):
        with_item.magasinier_validate(magasinier_user)
        response = dt_client.post(reverse('materials:request_approve', kwargs={'pk': with_item.pk}), {
            'action': 'approve',
        })
        assert response.status_code == 302
        with_item.refresh_from_db()
        assert with_item.status == MaterialRequestStatus.APPROVED

    def test_magasinier_cannot_authorize_via_view(self, magasinier_client, with_item, magasinier_user):
        with_item.magasinier_validate(magasinier_user)
        response = magasinier_client.post(reverse('materials:request_approve', kwargs={'pk': with_item.pk}), {
            'action': 'approve',
        })
        with_item.refresh_from_db()
        assert with_item.status == MaterialRequestStatus.VALIDATED

    def test_director_can_do_both_stages(self, director_client, with_item):
        response = director_client.post(reverse('materials:request_validate', kwargs={'pk': with_item.pk}), {
            'action': 'validate',
        })
        assert response.status_code == 302
        with_item.refresh_from_db()
        assert with_item.status == MaterialRequestStatus.VALIDATED

        response = director_client.post(reverse('materials:request_approve', kwargs={'pk': with_item.pk}), {
            'action': 'approve',
        })
        assert response.status_code == 302
        with_item.refresh_from_db()
        assert with_item.status == MaterialRequestStatus.APPROVED
