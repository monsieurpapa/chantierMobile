"""
Tests for item 16 of the Directors/Engineers audit: the dashboard's
"Accès rapide" (Quick access) cards only ever linked to a module's list
page, never straight to the form that creates something in it — despite
the section being framed as a shortcut. Each card now also carries a
small role-gated "+" quick-create button in its corner, linking directly
to that module's create view, without disturbing the existing
click-anywhere-on-the-card-to-open-the-list behavior (stretched-link).
"""
import pytest
from django.urls import reverse

from accounts.models import UserCabinetRole
from chantiermobile.constants import UserRoles, ApprovalStatus


@pytest.mark.django_db
class TestDashboardQuickCreateLinks:
    def test_director_sees_all_quick_create_links(self, director_client):
        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        content = response.content.decode()
        assert reverse('projects:site_create') in content
        assert reverse('personnel:personnel_create') in content
        assert reverse('finance:expense_create') in content
        assert reverse('materials:request_create') in content
        assert reverse('revenue:contract_create') in content

    def test_engineer_sees_only_the_open_create_links(self, engineer_client):
        """ENGINEER can't create a site, personnel record, or contract
        (those stay DIRECTOR-tier / CHIEF_ENGINEER / ACCOUNTANT), but
        expense and material-request creation are open to any
        authenticated cabinet member, so those two quick-create links
        should still appear."""
        response = engineer_client.get(reverse('home'))
        assert response.status_code == 200
        content = response.content.decode()
        assert reverse('projects:site_create') not in content
        assert reverse('personnel:personnel_create') not in content
        assert reverse('revenue:contract_create') not in content
        assert reverse('finance:expense_create') in content
        assert reverse('materials:request_create') in content

    def test_worker_sees_no_admin_quick_create_links(self, client, cabinet, django_user_model):
        worker = django_user_model.objects.create_user(username='worker_dash', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        client.login(username='worker_dash', password='testpass123')

        response = client.get(reverse('home'))
        assert response.status_code == 200
        content = response.content.decode()
        assert reverse('projects:site_create') not in content
        assert reverse('personnel:personnel_create') not in content
        assert reverse('revenue:contract_create') not in content
        # Still open to everyone, same as the expense/material-request views themselves.
        assert reverse('finance:expense_create') in content
        assert reverse('materials:request_create') in content
