"""
Regression: ISSUE-007 — personnel detail/edit pages crashed with
AttributeError because Personnel has no get_full_name/username/job_title
attributes (it is a plain BaseModel, not a User subclass).
Found by /qa on 2026-06-21
Report: .gstack/qa-reports/qa-report-localhost-2026-06-21.md
"""

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestPersonnelGetFullName:

    def test_get_full_name_returns_first_and_last_name(self, personnel):
        personnel.first_name = "Jean"
        personnel.last_name = "Diallo"
        personnel.save()

        assert personnel.get_full_name() == "Jean Diallo"

    def test_personnel_detail_view_does_not_crash(self, director_client, personnel):
        response = director_client.get(
            reverse('personnel:personnel_detail', kwargs={'unique_id': personnel.unique_id})
        )

        assert response.status_code == 200
        assert personnel.get_full_name() in response.content.decode()

    def test_personnel_update_view_does_not_crash(self, director_client, personnel):
        response = director_client.get(
            reverse('personnel:personnel_update', kwargs={'unique_id': personnel.unique_id})
        )

        assert response.status_code == 200
