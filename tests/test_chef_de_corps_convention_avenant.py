"""Tests for the 2026-10-07 "Chef de Corps / avenants de convention"
feature set:

- Personnel.is_chef_de_corps flags a subcontracting trade lead, who gets
  his own "Chefs de Corps" screen (ChefDeCorpsListView) built on the same
  Personnel/SiteAssignment data as regular personnel/conventions.
- ConventionAvenant.record() logs each renegotiation of a convention's
  amount (date/previous/new/reason/recorded_by) and keeps
  SiteAssignment.convention_amount (the live cap) in sync, backfilling
  initial_convention_amount the first time it runs.
- PayrollListItem.clean() allows a Chef de Corps's payment to exceed the
  current cap provided an overage_note is given (soft rule) — everyone
  else keeps the pre-existing hard block.
- ConventionOverageListView surfaces every such overage to the DG/bureau
  technique.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from chantiermobile.constants import UserRoles, ApprovalStatus, PersonnelPayrollType
from personnel.models import SiteAssignment, ConventionAvenant
from finance.models import PayrollList, PayrollListItem


@pytest.fixture
def cashier_user(db, cabinet):
    from django.contrib.auth import get_user_model
    from accounts.models import UserCabinetRole
    User = get_user_model()
    u = User.objects.create_user(username='cashier_cdc', email='cashier_cdc@example.com', password='testpass123')
    UserCabinetRole.objects.create(user=u, cabinet=cabinet, role=UserRoles.CASHIER, status=ApprovalStatus.APPROVED)
    return u


@pytest.fixture
def cashier_client(client, cashier_user):
    client.login(username='cashier_cdc', password='testpass123')
    return client


@pytest.fixture
def chef_de_corps(db, personnel_factory):
    return personnel_factory(
        first_name='Jean', last_name='Ferraille', is_chef_de_corps=True,
        trade='FERRAILLEUR', payroll_type=PersonnelPayrollType.OUVRIER,
    )


@pytest.fixture
def assignment_factory(db, site):
    def create(personnel, **kwargs):
        defaults = {'site': site, 'role': 'Chef de corps', 'start_date': None}
        defaults.update(kwargs)
        return SiteAssignment.objects.create(personnel=personnel, **defaults)
    return create


@pytest.mark.django_db
class TestTradeChoicesExtended:
    def test_charpentier_and_soudeur_are_valid_choices(self):
        from chantiermobile.constants import Trade
        assert 'CHARPENTIER' in Trade.values
        assert 'SOUDEUR' in Trade.values


@pytest.mark.django_db
class TestChefDeCorpsListView:
    def test_lists_only_chef_de_corps_personnel(self, director_client, chef_de_corps, personnel):
        response = director_client.get(reverse('personnel:chef_de_corps_list'))
        assert response.status_code == 200
        names = [p.pk for p in response.context['chefs_de_corps']]
        assert chef_de_corps.pk in names
        assert personnel.pk not in names

    def test_open_to_any_cabinet_member(self, engineer_client):
        response = engineer_client.get(reverse('personnel:chef_de_corps_list'))
        assert response.status_code == 200


@pytest.mark.django_db
class TestConventionAvenantRecord:
    def test_record_sets_initial_amount_on_first_avenant(self, chef_de_corps, assignment_factory, cashier_user):
        assignment = assignment_factory(chef_de_corps, convention_amount=Decimal('1000.00'))
        assert assignment.initial_convention_amount is None

        avenant = ConventionAvenant.record(
            assignment, new_amount=Decimal('1500.00'), reason='Surplus de travail', user=cashier_user,
        )
        assignment.refresh_from_db()
        assert avenant.previous_amount == Decimal('1000.00')
        assert avenant.new_amount == Decimal('1500.00')
        assert assignment.convention_amount == Decimal('1500.00')
        assert assignment.initial_convention_amount == Decimal('1000.00')
        assert assignment.effective_initial_amount == Decimal('1000.00')

    def test_second_avenant_keeps_original_initial_amount(self, chef_de_corps, assignment_factory, cashier_user):
        assignment = assignment_factory(chef_de_corps, convention_amount=Decimal('1000.00'))
        ConventionAvenant.record(assignment, new_amount=Decimal('1500.00'), reason='R1', user=cashier_user)
        assignment.refresh_from_db()
        ConventionAvenant.record(assignment, new_amount=Decimal('1800.00'), reason='R2', user=cashier_user)
        assignment.refresh_from_db()

        assert assignment.convention_amount == Decimal('1800.00')
        assert assignment.initial_convention_amount == Decimal('1000.00')
        assert assignment.avenants.count() == 2

    def test_negative_new_amount_rejected(self, chef_de_corps, assignment_factory):
        assignment = assignment_factory(chef_de_corps, convention_amount=Decimal('1000.00'))
        avenant = ConventionAvenant(assignment=assignment, date='2026-10-07', previous_amount=1000, new_amount=-5, reason='x')
        with pytest.raises(ValidationError):
            avenant.full_clean()


@pytest.mark.django_db
class TestConventionAvenantView:
    def test_cashier_can_record_avenant(self, cashier_client, chef_de_corps, assignment_factory):
        assignment = assignment_factory(chef_de_corps, convention_amount=Decimal('1000.00'))
        response = cashier_client.post(
            reverse('personnel:convention_avenant_create', kwargs={'pk': assignment.pk}),
            {'date': '2026-10-07', 'new_amount': '1600.00', 'reason': 'Surplus annoncé par le chef technique'},
        )
        assert response.status_code == 302
        assignment.refresh_from_db()
        assert assignment.convention_amount == Decimal('1600.00')
        assert assignment.avenants.count() == 1

    def test_engineer_cannot_record_avenant(self, engineer_client, chef_de_corps, assignment_factory):
        assignment = assignment_factory(chef_de_corps, convention_amount=Decimal('1000.00'))
        response = engineer_client.post(
            reverse('personnel:convention_avenant_create', kwargs={'pk': assignment.pk}),
            {'date': '2026-10-07', 'new_amount': '1600.00', 'reason': 'x'},
        )
        assignment.refresh_from_db()
        assert assignment.convention_amount == Decimal('1000.00')
        assert assignment.avenants.count() == 0


@pytest.fixture
def payroll_list(db, site, user):
    pl = PayrollList.objects.create(site=site, prepared_by=user)
    return pl


@pytest.mark.django_db
class TestPayrollItemSoftOverageForChefDeCorps:
    def test_chef_de_corps_overage_requires_note(self, chef_de_corps, assignment_factory, payroll_list):
        assignment = assignment_factory(chef_de_corps, convention_amount=Decimal('100.00'))
        item = PayrollListItem(payroll_list=payroll_list, personnel=chef_de_corps, assignment=assignment, amount=Decimal('150.00'))
        with pytest.raises(ValidationError) as exc:
            item.full_clean()
        assert 'overage_note' in exc.value.message_dict

    def test_chef_de_corps_overage_allowed_with_note(self, chef_de_corps, assignment_factory, payroll_list):
        assignment = assignment_factory(chef_de_corps, convention_amount=Decimal('100.00'))
        item = PayrollListItem(
            payroll_list=payroll_list, personnel=chef_de_corps, assignment=assignment,
            amount=Decimal('150.00'), overage_note='Surplus de travail confirmé par le chef technique.',
        )
        item.full_clean()
        item.save()
        assert item.pk is not None

    def test_regular_ouvrier_overage_still_hard_blocked(self, personnel_factory, assignment_factory, payroll_list, site):
        ouvrier = personnel_factory(first_name='Paul', last_name='Ouvrier', payroll_type=PersonnelPayrollType.OUVRIER)
        assignment = SiteAssignment.objects.create(personnel=ouvrier, site=site, convention_amount=Decimal('100.00'))
        item = PayrollListItem(
            payroll_list=payroll_list, personnel=ouvrier, assignment=assignment,
            amount=Decimal('150.00'), overage_note='Peu importe la note',
        )
        with pytest.raises(ValidationError) as exc:
            item.full_clean()
        assert 'amount' in exc.value.message_dict


@pytest.mark.django_db
class TestConventionOverageListView:
    def test_overage_items_visible_to_director(self, director_client, chef_de_corps, assignment_factory, payroll_list):
        assignment = assignment_factory(chef_de_corps, convention_amount=Decimal('100.00'))
        PayrollListItem.objects.create(
            payroll_list=payroll_list, personnel=chef_de_corps, assignment=assignment,
            amount=Decimal('150.00'), overage_note='Surplus confirmé.',
        )
        response = director_client.get(reverse('finance:convention_overage_list'))
        assert response.status_code == 200
        assert 'Surplus confirmé.' in response.content.decode()

    def test_items_without_overage_note_not_listed(self, director_client, chef_de_corps, assignment_factory, payroll_list):
        assignment = assignment_factory(chef_de_corps, convention_amount=None)
        PayrollListItem.objects.create(
            payroll_list=payroll_list, personnel=chef_de_corps, assignment=assignment, amount=Decimal('50.00'),
        )
        response = director_client.get(reverse('finance:convention_overage_list'))
        assert response.status_code == 200
        assert list(response.context['overage_items']) == []

    def test_engineer_cannot_view_overage_report(self, engineer_client):
        response = engineer_client.get(reverse('finance:convention_overage_list'))
        assert response.status_code == 302
