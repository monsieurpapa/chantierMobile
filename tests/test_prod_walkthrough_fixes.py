"""Bugs found while testing production by hand (2026-11-16).

1. New dépense never saved: the form requires `expense_date` but the page
   did not show that field, so every submission came back with no visible
   error. The field is now on the page (defaults to today) and any error,
   including on a field the page doesn't show, is listed at the top.
2. A chantier's (or étape's / personnel's) delete page crashed with a 500
   when the browser sent no Referer (link opened directly, privacy
   settings): the Cancel link used it as a filter argument.
"""
import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from chantiermobile.constants import SiteStatus
from finance.models import Expense, ExpenseCategory


def _rendered_fields(html):
    """Names of the inputs/selects/textareas the page actually shows."""
    return set(re.findall(r'<(?:input|select|textarea)[^>]*\sname="([^"]+)"', html))


@pytest.mark.django_db
class TestExpenseForm:
    def test_page_shows_the_date_field_with_today(self, director_client):
        html = director_client.get(reverse('finance:expense_create')).content.decode()
        assert 'expense_date' in _rendered_fields(html)
        assert f'value="{date.today().isoformat()}"' in html

    def test_submitting_only_what_the_page_shows_saves_the_expense(self, director_client, site_factory):
        site = site_factory(name='Dépense visible', status=SiteStatus.ACTIVE)
        category = ExpenseCategory.objects.first() or ExpenseCategory.objects.create(name='Matériaux')
        html = director_client.get(reverse('finance:expense_create')).content.decode()
        shown = _rendered_fields(html)
        data = {'site': site.pk, 'category': category.pk, 'amount': '250', 'expense_date': date.today().isoformat(),
                'description': 'Tuyaux PVC', 'nature': 'MATERIEL'}
        data = {k: v for k, v in data.items() if k in shown}  # what a browser would send
        response = director_client.post(reverse('finance:expense_create'), data)
        assert response.status_code == 302, response.content.decode()[:500]
        assert Expense.objects.filter(site=site, amount=Decimal('250')).exists()

    def test_errors_are_listed_at_the_top(self, director_client):
        response = director_client.post(reverse('finance:expense_create'), {'amount': '10'})
        content = response.content.decode()
        assert response.status_code == 200
        assert "La dépense n&#x27;a pas été enregistrée" in content or "La dépense n'a pas été enregistrée" in content


@pytest.mark.django_db
class TestDeletePageWithoutReferer:
    def test_site_delete_page_renders_without_referer(self, director_client, site_factory):
        site = site_factory(name='À supprimer', status=SiteStatus.PLANNING)
        response = director_client.get(reverse('projects:site_delete', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 200

    def test_cancel_goes_back_to_the_referring_page(self, director_client, site_factory):
        site = site_factory(name='À supprimer 2', status=SiteStatus.PLANNING)
        response = director_client.get(reverse('projects:site_delete', kwargs={'unique_id': site.unique_id}),
                                       HTTP_REFERER='/projects/sites/')
        assert 'href="/projects/sites/"' in response.content.decode()

    def test_superadmin_too(self, admin_client, site_factory):
        site = site_factory(name='À supprimer 3', status=SiteStatus.PLANNING)
        assert admin_client.get(reverse('projects:site_delete', kwargs={'unique_id': site.unique_id})).status_code == 200
