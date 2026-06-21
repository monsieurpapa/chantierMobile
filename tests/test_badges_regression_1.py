"""
Regression: ISSUE-003 — status/skill badges rendered with badge-soft-* classes
that don't exist in the compiled Falcon theme CSS (only badge-subtle-* does),
making every status pill render as invisible white-on-white text.
Found by /qa on 2026-06-21
Report: .gstack/qa-reports/qa-report-localhost-2026-06-21.md
"""

import pytest
from django.urls import reverse

from chantiermobile.constants import SiteStatus


@pytest.mark.django_db
class TestBadgeClasses:
    """Status badges must use badge-subtle-* (the only variant this theme ships)."""

    def test_site_list_badge_uses_subtle_class(self, director_client, site):
        site.status = SiteStatus.ACTIVE
        site.save()

        response = director_client.get(reverse('projects:site_list'))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'badge-subtle-success' in content
        assert 'badge-soft-success' not in content

    def test_site_list_badge_for_planning_status(self, director_client, site):
        site.status = SiteStatus.PLANNING
        site.save()

        response = director_client.get(reverse('projects:site_list'))

        content = response.content.decode()
        assert 'badge-subtle-primary' in content
        assert 'badge-soft-primary' not in content
