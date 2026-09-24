"""
Tests for item 5 of the Directors/Engineers audit: BudgetListView and
BudgetDetailView used to exclude ENGINEER from allowed_roles entirely, so
a site's own engineer had no way to see that site's budget at all — only
DIRECTOR-tier, ACCOUNTANT and CHIEF_ENGINEER could. The fix adds ENGINEER
to the allowed roles but scopes their queryset to only the site(s) they
lead (Site.lead_engineer), so they can't browse every other site's
budget in the cabinet the way a full-access role can.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.urls import reverse

from accounts.models import UserCabinetRole
from finance.models import Budget
from chantiermobile.constants import UserRoles, ApprovalStatus


@pytest.fixture
def budget_factory(db):
    def create_budget(site, **kwargs):
        defaults = {
            'total_amount': Decimal('10000.00'),
            'start_date': date.today(),
            'end_date': date.today() + timedelta(days=90),
        }
        defaults.update(kwargs)
        return Budget.objects.create(site=site, **defaults)
    return create_budget


@pytest.mark.django_db
class TestEngineerBudgetVisibility:
    def test_engineer_leading_a_site_can_view_its_budget(self, engineer_client, engineer_user, site, budget_factory):
        site.lead_engineer = engineer_user
        site.save(update_fields=['lead_engineer'])
        budget = budget_factory(site)

        response = engineer_client.get(reverse('finance:budget_detail', kwargs={'pk': budget.pk}))
        assert response.status_code == 200

        list_response = engineer_client.get(reverse('finance:budget_list'))
        assert list_response.status_code == 200
        assert budget in list_response.context['budgets']

    def test_engineer_not_leading_the_site_cannot_view_its_budget(self, engineer_client, site, budget_factory):
        """site.lead_engineer is left unset (or set to someone else), so
        the engineer has no claim on this budget even though they belong
        to the same cabinet."""
        budget = budget_factory(site)

        response = engineer_client.get(reverse('finance:budget_detail', kwargs={'pk': budget.pk}))
        assert response.status_code == 404

        list_response = engineer_client.get(reverse('finance:budget_list'))
        assert list_response.status_code == 200
        assert budget not in list_response.context['budgets']

    def test_engineer_sees_only_own_led_site_in_a_multi_site_cabinet(self, engineer_client, engineer_user, cabinet, site_factory, budget_factory):
        own_site = site_factory(name='Site dirigé')
        own_site.lead_engineer = engineer_user
        own_site.save(update_fields=['lead_engineer'])
        other_site = site_factory(name='Autre site')

        own_budget = budget_factory(own_site)
        other_budget = budget_factory(other_site)

        response = engineer_client.get(reverse('finance:budget_list'))
        budgets = list(response.context['budgets'])
        assert own_budget in budgets
        assert other_budget not in budgets

    def test_director_still_sees_every_budget_in_the_cabinet(self, director_client, cabinet, site_factory, budget_factory):
        """Full-access roles are unaffected by the engineer scoping."""
        site_a = site_factory(name='Site A')
        site_b = site_factory(name='Site B')
        budget_a = budget_factory(site_a)
        budget_b = budget_factory(site_b)

        response = director_client.get(reverse('finance:budget_list'))
        budgets = list(response.context['budgets'])
        assert budget_a in budgets
        assert budget_b in budgets

    def test_worker_still_cannot_reach_budget_list(self, client, cabinet, django_user_model, site, budget_factory):
        """Regression guard: the fix only adds ENGINEER, not every role."""
        worker = django_user_model.objects.create_user(username='worker_budget', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        budget_factory(site)

        client.login(username='worker_budget', password='testpass123')
        response = client.get(reverse('finance:budget_list'))
        assert response.status_code == 302
