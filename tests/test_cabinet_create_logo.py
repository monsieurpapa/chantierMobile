"""Superadmin creates a cabinet with every field filled in, logo included."""
import pytest
from django.urls import reverse

from accounts.models import Cabinet


FORM_DATA = {
    'name': 'Cabinet Logo Test',
    'address': 'Av. du Lac 12, Goma',
    'tax_id': 'A1234567B',
    'legal_name': 'Assistance Technique en Génie Civil',
    'short_name': 'A.T.G.C.',
    'legal_mentions': "N° d'agrément 123\nRCCM CD/GOM/RCCM/24-B-001",
    'phone': '(+243) 991 234 567',
    'email': 'contact@example.com',
    'city': 'Goma',
}


@pytest.mark.django_db
def test_superadmin_creates_cabinet_with_logo_local_storage(client, superuser, mock_file_upload, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client.force_login(superuser)
    response = client.post(
        reverse('accounts:admin_cabinet_create'),
        {**FORM_DATA, 'logo': mock_file_upload},
    )
    assert response.status_code == 302, getattr(response, 'context', None) and response.context['form'].errors
    cabinet = Cabinet.objects.get(name='Cabinet Logo Test')
    assert cabinet.logo.name.startswith('cabinets/logos/')
