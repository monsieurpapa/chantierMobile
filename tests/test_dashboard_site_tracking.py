"""Dashboard "Suivi des chantiers" + calendar day pop-up (2026-10-22).

- Per chantier: étape en cours, avancement, budget (DQE, else Budget),
  dépensé, % consommé, reste, encaissé, santé — and the same per étape.
- Money only for roles that see financials; never for a Magasinier.
- The calendar counts progress reports per day; a day's body is served
  alone (?partial=1) for the pop-up and lists the reports with their author.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import UserCabinetRole
from chantiermobile.constants import (
    ApprovalStatus, DQEStatus, ExpenseStatus, PhaseStatus, PriceItemType, SiteStatus, UserRoles,
)
from core.site_tracking import build_site_tracking, portfolio_totals
from finance.models import Budget, Expense, ExpenseCategory
from pricing.models import DQE, DQELine, PriceLibraryItem
from projects.models import ProjectPhase, Site, SiteProgress

TODAY = date.today()


@pytest.fixture
def chantier(cabinet, site_factory):
    site = site_factory(name='Suivi Kivu', status=SiteStatus.ACTIVE)
    fond = ProjectPhase.objects.create(site=site, name='Fondations', start_date=TODAY - timedelta(days=30),
                                       end_date=TODAY - timedelta(days=5), status=PhaseStatus.CLOTUREE)
    elev = ProjectPhase.objects.create(site=site, name='Élévation', start_date=TODAY - timedelta(days=5),
                                       end_date=TODAY + timedelta(days=25))
    dalle = ProjectPhase.objects.create(site=site, name='Dalle niveau 1', parent_phase=elev,
                                        start_date=TODAY, end_date=TODAY + timedelta(days=10))
    return site, fond, elev, dalle


def _expense(site, phase, amount, status=ExpenseStatus.APPROVED):
    cat = ExpenseCategory.objects.first() or ExpenseCategory.objects.create(name='Matériaux')
    return Expense.objects.create(site=site, phase=phase, category=cat, amount=Decimal(amount),
                                  expense_date=TODAY, description='suivi', status=status)


def _rows(site, money=True):
    return build_site_tracking(Site.objects.filter(pk=site.pk), money)


@pytest.mark.django_db
class TestSiteTracking:
    def test_progress_and_current_etape(self, chantier, user):
        site, fond, elev, dalle = chantier
        SiteProgress.objects.create(phase=dalle, report_date=TODAY, percentage_complete=40, description='x', created_by=user)
        row = _rows(site, money=False)[0]
        assert row['current_etape']['name'] == 'Élévation'
        assert [e['progress'] for e in row['etapes']] == [100, 40]  # closed = 100; sous-étape report rolls up
        assert row['progress'] == 70 and (row['closed_count'], row['etape_count']) == (1, 2)
        assert 'budget' not in row and 'spent' not in row

    def test_budget_fallback_and_spend(self, chantier):
        site, fond, elev, _ = chantier
        Budget.objects.create(site=site, total_amount=Decimal('1000'), start_date=TODAY, end_date=TODAY + timedelta(days=90))
        _expense(site, fond, 300)
        _expense(site, elev, 200, ExpenseStatus.PAID)
        _expense(site, elev, 999, ExpenseStatus.PENDING)  # not counted
        row = _rows(site)[0]
        assert (row['budget'], row['budget_source'], row['spent'], row['remaining']) == (Decimal('1000'), 'Budget', Decimal('500'), Decimal('500'))
        assert round(row['consumed']) == 50
        # avancement 50 % (100 + 0) / 2, consumed 50 % → on track
        assert row['health']['key'] == 'ok'

    def test_dqe_budget_per_etape_and_health(self, chantier, cabinet):
        site, fond, elev, dalle = chantier
        dqe = DQE.objects.create(cabinet=cabinet, site=site, reference='DQE-SUIVI', title='t', status=DQEStatus.APPROUVE)
        item = PriceLibraryItem.objects.create(cabinet=cabinet, code='SV-1', designation='o', item_type=PriceItemType.WORK_ITEM,
                                               unit='m3', unit_price=Decimal('10'))
        DQELine.objects.create(dqe=dqe, price_item=item, phase=fond, quantity=10, unit_price=Decimal('10'))   # 100
        DQELine.objects.create(dqe=dqe, price_item=item, phase=dalle, quantity=30, unit_price=Decimal('10'))  # 300 → Élévation
        _expense(site, dalle, 150)
        row = _rows(site)[0]
        assert row['budget'] == Decimal('400') and row['budget_source'] == 'DQE DQE-SUIVI'
        fond_e, elev_e = row['etapes']
        assert (fond_e['budget'], elev_e['budget'], elev_e['spent']) == (Decimal('100'), Decimal('300'), Decimal('150'))
        assert round(elev_e['consumed']) == 50
        assert elev_e['health']['key'] == 'watch'  # 50 % spent, 0 % done

    def test_overrun(self, chantier):
        site, fond, *_ = chantier
        Budget.objects.create(site=site, total_amount=Decimal('100'), start_date=TODAY, end_date=TODAY + timedelta(days=9))
        _expense(site, fond, 130)
        row = _rows(site)[0]
        assert row['health']['key'] == 'over' and row['overrun'] == Decimal('30')
        totals = portfolio_totals([row])
        assert totals['overrun'] == Decimal('30') and totals['watch'] == 1

    def test_portfolio_skips_finished_and_counts_unbudgeted(self, chantier, site_factory):
        site, fond, *_ = chantier
        Budget.objects.create(site=site, total_amount=Decimal('1000'), start_date=TODAY, end_date=TODAY + timedelta(days=9))
        _expense(site, fond, 250)
        done = site_factory(name='Fini', status=SiteStatus.COMPLETED)
        Budget.objects.create(site=done, total_amount=Decimal('5000'), start_date=TODAY, end_date=TODAY + timedelta(days=9))
        bare = site_factory(name='Sans budget', status=SiteStatus.ACTIVE)
        rows = build_site_tracking(Site.objects.filter(pk__in=[site.pk, done.pk, bare.pk]), True)
        assert [r['name'] for r in rows][-1] == 'Fini'  # active first
        totals = portfolio_totals(rows)
        assert (totals['sites'], totals['budget'], totals['spent'], totals['unbudgeted']) == (2, Decimal('1000'), Decimal('250'), 1)
        assert round(totals['consumed']) == 25


@pytest.mark.django_db
class TestDashboardView:
    def test_director_sees_money(self, director_client, chantier):
        site, fond, *_ = chantier
        Budget.objects.create(site=site, total_amount=Decimal('1000'), start_date=TODAY, end_date=TODAY + timedelta(days=9))
        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        assert response.context['portfolio'] is not None
        assert any(r['name'] == 'Suivi Kivu' and r['budget'] == Decimal('1000') for r in response.context['site_tracking'])
        content = response.content.decode()
        assert 'Suivi des chantiers' in content and 'Budget en cours' in content and 'cm-day-modal' in content

    def test_superadmin_sees_money(self, admin_client, chantier):
        response = admin_client.get(reverse('home'))
        assert response.status_code == 200 and response.context['portfolio'] is not None
        assert any(r['name'] == 'Suivi Kivu' for r in response.context['site_tracking'])

    def test_engineer_sees_progress_without_money(self, client, cabinet, chantier):
        eng = get_user_model().objects.create_user(username='suivi_eng', password='pw-12345')
        UserCabinetRole.objects.create(user=eng, cabinet=cabinet, role=UserRoles.ENGINEER, status=ApprovalStatus.APPROVED)
        client.force_login(eng)
        response = client.get(reverse('home'))
        if response.context.get('can_view_financials'):
            pytest.skip('engineers see financials in this configuration')
        assert response.context['portfolio'] is None
        rows = response.context['site_tracking']
        assert rows and all('budget' not in r for r in rows)
        assert 'Budget en cours' not in response.content.decode()

    def test_calendar_counts_reports(self, director_client, chantier, user):
        site, fond, elev, dalle = chantier
        SiteProgress.objects.create(phase=dalle, report_date=TODAY, percentage_complete=10, description='a', created_by=user)
        SiteProgress.objects.create(phase=elev, report_date=TODAY, percentage_complete=12, description='b', created_by=user)
        response = director_client.get(reverse('home'))
        days = [d for week in response.context['calendar_weeks'] for d in week if d['date'] == TODAY]
        assert days and days[0]['report_count'] == 2


@pytest.mark.django_db
class TestDayPopup:
    def url(self, partial=True):
        return reverse('home_day_detail', kwargs={'day': TODAY.isoformat()}) + ('?partial=1' if partial else '')

    def test_partial_lists_reports_with_author(self, director_client, chantier, user):
        site, fond, elev, dalle = chantier
        user.first_name, user.last_name = 'Brave', 'Bakulu'
        user.save()
        SiteProgress.objects.create(phase=dalle, report_date=TODAY, percentage_complete=35,
                                    description='Ferraillage de la dalle en cours', created_by=user)
        response = director_client.get(self.url())
        content = response.content.decode()
        assert response.status_code == 200
        assert '<html' not in content and 'navbar' not in content  # body only
        assert 'Ferraillage de la dalle en cours' in content and 'Brave Bakulu' in content
        assert 'Élévation › Dalle niveau 1' in content and '35 %' in content

    def test_full_page_uses_the_same_body(self, director_client, chantier, user):
        site, fond, *_ = chantier
        SiteProgress.objects.create(phase=fond, report_date=TODAY, percentage_complete=90, description='Semelles OK', created_by=user)
        content = director_client.get(self.url(partial=False)).content.decode()
        assert 'Semelles OK' in content and '<html' in content

    def test_empty_day(self, director_client):
        content = director_client.get(reverse('home_day_detail', kwargs={'day': '2001-01-01'}) + '?partial=1').content.decode()
        assert "Rien d'enregistré" in content or 'Rien d&#x27;enregistré' in content

    def test_expenses_only_for_financial_roles(self, client, director_client, cabinet, chantier):
        site, fond, *_ = chantier
        _expense(site, fond, 4321)
        assert '4' in director_client.get(self.url()).content.decode() and 'Argent' in director_client.get(self.url()).content.decode()
        eng = get_user_model().objects.create_user(username='suivi_eng2', password='pw-12345')
        UserCabinetRole.objects.create(user=eng, cabinet=cabinet, role=UserRoles.ENGINEER, status=ApprovalStatus.APPROVED)
        client.force_login(eng)
        response = client.get(self.url())
        if response.context.get('can_view_financials'):
            pytest.skip('engineers see financials in this configuration')
        assert 'Argent' not in response.content.decode()

    def test_superadmin_sees_the_day(self, admin_client, chantier, user):
        site, fond, *_ = chantier
        SiteProgress.objects.create(phase=fond, report_date=TODAY, percentage_complete=5, description='Visible admin', created_by=user)
        assert 'Visible admin' in admin_client.get(self.url()).content.decode()
