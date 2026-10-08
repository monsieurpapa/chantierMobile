"""
Tests for the material-request edit guard added to
MaterialRequestUpdateView: until now the view had no status check and no
ownership check at all, so any authenticated staff member of the cabinet
could rewrite someone else's "état de besoin" at any point in its
approval lifecycle just by guessing/typing the edit URL. The templates
already hid the "Modifier" link once a request left PENDING, but that's
only a UI nicety — nothing stopped a direct POST to the view.
"""
import pytest
from decimal import Decimal
from django.urls import reverse

from accounts.models import UserCabinetRole
from materials.models import Material, MaterialRequest, MaterialRequestItem
from chantiermobile.constants import UserRoles, ApprovalStatus, MaterialRequestStatus


@pytest.fixture
def catalog_material(db):
    return Material.objects.create(name='Ciment', unit='sac', estimated_cost_per_unit=Decimal('25.00'))


@pytest.fixture
def pending_request(db, site, engineer_user, catalog_material):
    """A PENDING request filed by the engineer, matching how
    MaterialRequestCreateView.form_valid() sets requested_by."""
    req = MaterialRequest.objects.create(site=site, requested_by=engineer_user, status=MaterialRequestStatus.PENDING)
    MaterialRequestItem.objects.create(request=req, material=catalog_material, quantity=Decimal('5.00'))
    return req


def _formset_payload(item, material, **overrides):
    # MaterialRequestItemFormSet's default prefix is 'items', derived from
    # MaterialRequestItem.request's related_name — not the formset library's
    # usual 'form' default.
    data = {
        'items-TOTAL_FORMS': '1',
        'items-INITIAL_FORMS': '1',
        'items-MIN_NUM_FORMS': '0',
        'items-MAX_NUM_FORMS': '1000',
        'items-0-id': str(item.pk),
        'items-0-material': str(material.pk),
        'items-0-material_name': '',
        'items-0-quantity': '9.00',
        'items-0-notes': '',
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestMaterialRequestEditGuard:
    def test_requester_can_edit_own_pending_request(self, engineer_client, pending_request, catalog_material):
        item = pending_request.items.first()
        url = reverse('materials:request_update', kwargs={'pk': pending_request.pk})
        assert engineer_client.get(url).status_code == 200

        data = {'site': str(pending_request.site.pk), 'notes': 'Mise à jour par le demandeur'}
        data.update(_formset_payload(item, catalog_material))
        response = engineer_client.post(url, data)
        assert response.status_code == 302
        pending_request.refresh_from_db()
        assert pending_request.notes == 'Mise à jour par le demandeur'

    def test_director_can_edit_someone_elses_pending_request(self, director_client, pending_request, catalog_material):
        """DIRECTOR is an admin-tier override role, even though the
        director isn't the original requester (the engineer is)."""
        item = pending_request.items.first()
        url = reverse('materials:request_update', kwargs={'pk': pending_request.pk})
        assert director_client.get(url).status_code == 200

        data = {'site': str(pending_request.site.pk), 'notes': 'Corrigé par le directeur'}
        data.update(_formset_payload(item, catalog_material))
        response = director_client.post(url, data)
        assert response.status_code == 302
        pending_request.refresh_from_db()
        assert pending_request.notes == 'Corrigé par le directeur'

    def test_unrelated_user_cannot_edit_pending_request(self, client, cabinet, pending_request, catalog_material, django_user_model):
        """A second engineer in the same cabinet, who neither filed the
        request nor holds an admin-tier role, must be bounced back to the
        detail page with the request left untouched — GET and POST alike."""
        other = django_user_model.objects.create_user(username='other_engineer', password='testpass123')
        UserCabinetRole.objects.create(user=other, cabinet=cabinet, role=UserRoles.ENGINEER, status=ApprovalStatus.APPROVED)
        client.login(username='other_engineer', password='testpass123')

        item = pending_request.items.first()
        url = reverse('materials:request_update', kwargs={'pk': pending_request.pk})

        get_response = client.get(url)
        assert get_response.status_code == 302
        assert get_response.url == reverse('materials:request_detail', kwargs={'pk': pending_request.pk})

        data = {'site': str(pending_request.site.pk), 'notes': 'Tentative non autorisée'}
        data.update(_formset_payload(item, catalog_material))
        post_response = client.post(url, data)
        assert post_response.status_code == 302
        pending_request.refresh_from_db()
        assert pending_request.notes != 'Tentative non autorisée'

    def test_cannot_edit_once_no_longer_pending(self, engineer_client, pending_request):
        """Even the original requester loses edit rights the moment the
        request advances past PENDING (matching what the templates already
        implied by hiding the Edit link at that point)."""
        pending_request.status = MaterialRequestStatus.APPROVED
        pending_request.save(update_fields=['status'])

        url = reverse('materials:request_update', kwargs={'pk': pending_request.pk})
        response = engineer_client.get(url)
        assert response.status_code == 302
        assert response.url == reverse('materials:request_detail', kwargs={'pk': pending_request.pk})
