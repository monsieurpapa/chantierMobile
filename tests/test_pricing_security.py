"""
Regression tests for the price_items_data_api tenant-isolation/auth fix
(see pricing/views.py and docs/modules/pricing.md's "Business rules &
gotchas" — the endpoint used to have no @login_required and no cabinet
filter at all, leaking every cabinet's price catalog to anyone).
"""
import pytest
from django.urls import reverse

from accounts.models import Cabinet, UserCabinetRole
from chantiermobile.constants import UserRoles, ApprovalStatus
from pricing.models import PriceLibraryItem


@pytest.mark.django_db
@pytest.mark.integration
@pytest.mark.critical
class TestPriceItemsDataApiSecurity:
    def _make_item(self, cabinet, code):
        return PriceLibraryItem.objects.create(
            cabinet=cabinet,
            code=code,
            designation=f"Item {code}",
            unit='m2',
            unit_price=100,
        )

    def test_anonymous_request_is_rejected(self, client, cabinet):
        self._make_item(cabinet, 'MO-001')
        response = client.get(reverse('pricing:price_items_data'))
        # login_required redirects an anonymous request to the login page
        # rather than returning the data directly.
        assert response.status_code == 302
        assert reverse('account_login') in response['Location']

    def test_authenticated_user_only_sees_their_own_cabinet(self, director_client, cabinet):
        own_item = self._make_item(cabinet, 'MO-001')
        other_cabinet = Cabinet.objects.create(name='Other Cabinet')
        other_item = self._make_item(other_cabinet, 'MO-999')

        response = director_client.get(reverse('pricing:price_items_data'))
        assert response.status_code == 200
        data = response.json()

        assert str(own_item.id) in data
        assert str(other_item.id) not in data

    def test_inactive_items_are_excluded(self, director_client, cabinet):
        active = self._make_item(cabinet, 'MO-001')
        inactive = self._make_item(cabinet, 'MO-002')
        inactive.is_active = False
        inactive.save()

        response = director_client.get(reverse('pricing:price_items_data'))
        data = response.json()

        assert str(active.id) in data
        assert str(inactive.id) not in data

    def test_superuser_without_active_cabinet_sees_every_cabinet(self, admin_client, cabinet):
        item_a = self._make_item(cabinet, 'MO-001')
        other_cabinet = Cabinet.objects.create(name='Other Cabinet')
        item_b = self._make_item(other_cabinet, 'MO-999')

        response = admin_client.get(reverse('pricing:price_items_data'))
        data = response.json()

        assert str(item_a.id) in data
        assert str(item_b.id) in data

    def test_user_with_no_cabinet_role_sees_nothing(self, client, django_user_model, cabinet):
        self._make_item(cabinet, 'MO-001')
        user = django_user_model.objects.create_user(username='nobody', password='testpass123')
        client.login(username='nobody', password='testpass123')

        response = client.get(reverse('pricing:price_items_data'))
        assert response.status_code == 200
        assert response.json() == {}
