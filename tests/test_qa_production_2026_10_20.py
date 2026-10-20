"""Regression tests for the production QA pass of 2026-10-20 — see
docs/history/qa-report-production-2026-10-20.md (finding numbers below)."""
from decimal import Decimal

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestFinding4NoDollarNone:
    """A worker without a default daily rate showed "$None"."""

    def test_personnel_list(self, director_client, personnel_factory):
        personnel_factory(first_name='Sans', last_name='Tarif', default_daily_rate=None)
        response = director_client.get(reverse('personnel:personnel_list'))
        assert response.status_code == 200
        assert b'$None' not in response.content

    def test_personnel_detail(self, director_client, personnel_factory):
        person = personnel_factory(first_name='Sans', last_name='Tarif', default_daily_rate=None)
        response = director_client.get(reverse('personnel:personnel_detail', kwargs={'unique_id': person.unique_id}))
        assert response.status_code == 200
        assert b'$None' not in response.content

    def test_rate_is_formatted_when_set(self, director_client, personnel_factory):
        person = personnel_factory(first_name='Avec', last_name='Tarif', default_daily_rate=Decimal('1500'))
        response = director_client.get(reverse('personnel:personnel_detail', kwargs={'unique_id': person.unique_id}))
        assert '1\xa0500,00'.encode() in response.content or '1 500,00'.encode() in response.content
