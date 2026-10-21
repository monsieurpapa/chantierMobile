"""WhatsApp-ready phone numbers on users and personnel, and the Brave
Bakulu account (2026-10-21)."""
import importlib

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import Cabinet, UserCabinetRole
from core.phone import normalize_phone, whatsapp_url
from personnel.models import Personnel


@pytest.mark.parametrize('typed,stored', [
    ('0991 234 567', '+243991234567'),
    ('+243 991-234-567', '+243991234567'),
    ('00243991234567', '+243991234567'),
    ('991234567', '+243991234567'),
    ('243991234567', '+243991234567'),
    ('+250 788 123 456', '+250788123456'),
    ('(0)81.234.5678', '+243812345678'),
    ('', ''),
])
def test_normalize_phone(typed, stored):
    assert normalize_phone(typed) == stored


@pytest.mark.parametrize('bad', ['12', 'abc', '+243 99x 234 567', '+1234567890123456'])
def test_invalid_phone(bad):
    with pytest.raises(ValidationError):
        normalize_phone(bad)


def test_whatsapp_url():
    assert whatsapp_url('+243991234567') == 'https://wa.me/243991234567'
    assert whatsapp_url('') == ''


@pytest.mark.django_db
class TestModels:
    def test_saved_in_international_form(self, cabinet):
        person = Personnel.objects.create(cabinet=cabinet, first_name='Amani', last_name='K', phone_number='0991 234 567')
        person.refresh_from_db()
        assert person.phone_number == '+243991234567'
        assert person.whatsapp_url == 'https://wa.me/243991234567'

    def test_personnel_falls_back_to_login_number(self, cabinet):
        user = get_user_model().objects.create_user(username='amani_wa', password='x', phone_number='0812345678')
        person = Personnel.objects.create(cabinet=cabinet, first_name='Amani', last_name='K', user=user)
        assert person.contact_phone == '+243812345678'

    def test_invalid_number_rejected_by_full_clean(self, cabinet):
        person = Personnel(cabinet=cabinet, first_name='A', last_name='B', phone_number='12')
        with pytest.raises(ValidationError) as exc:
            person.full_clean()
        assert 'phone_number' in exc.value.message_dict


@pytest.mark.django_db
class TestForms:
    def test_profile_form_normalises_and_records_consent(self, authenticated_client, user):
        response = authenticated_client.post(reverse('accounts:profile_update'), {
            'first_name': 'T', 'last_name': 'U', 'email': user.email or 'tu@example.com',
            'phone_number': '0991 234 567', 'whatsapp_opt_in': 'on',
        })
        assert response.status_code in (200, 302)
        user.refresh_from_db()
        assert user.phone_number == '+243991234567'
        assert user.whatsapp_opt_in is True

    def test_profile_form_rejects_bad_number(self, authenticated_client, user):
        response = authenticated_client.post(reverse('accounts:profile_update'), {
            'first_name': 'T', 'last_name': 'U', 'email': 'tu@example.com', 'phone_number': 'abc',
        })
        assert response.status_code == 200
        assert 'invalide' in response.content.decode()

    def test_personnel_detail_shows_whatsapp(self, director_client, cabinet):
        person = Personnel.objects.create(cabinet=cabinet, first_name='Amani', last_name='WA', phone_number='+243991234567')
        response = director_client.get(reverse('personnel:personnel_detail', kwargs={'unique_id': person.unique_id}))
        assert b'https://wa.me/243991234567' in response.content


@pytest.mark.django_db
class TestBraveBakuluMigration:
    def _run(self):
        migration = importlib.import_module('accounts.migrations.0016_add_brave_bakulu_chief_engineer')
        migration.forwards(django_apps, None)

    def test_adds_chief_engineer_to_atgc(self):
        Cabinet.objects.all().update(name='Autre')  # keep the test independent of what is in the db
        atgc = Cabinet.objects.create(name='ATGC Congo')
        self._run()
        user = get_user_model().objects.get(email='bravebakuluirbtp@gmail.com')
        assert (user.first_name, user.last_name) == ('Brave', 'Bakulu')
        assert not user.has_usable_password()
        assert user.must_change_password
        role = UserCabinetRole.objects.get(user=user, cabinet=atgc)
        assert (role.role, role.status) == ('CHIEF_ENGINEER', 'APPROVED')
        self._run()  # idempotent
        assert get_user_model().objects.filter(email='bravebakuluirbtp@gmail.com').count() == 1
