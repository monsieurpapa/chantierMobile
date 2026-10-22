"""Caissier and Comptable have the same access (2026-10-22): one person does
both jobs for now, so settings.ROLE_EQUIVALENCES makes CASHIER and
ACCOUNTANT interchangeable in every role check."""
import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

from accounts.models import UserCabinetRole, equivalent_roles
from chantiermobile.constants import ApprovalStatus, UserRoles
from core.mixins import can_act_for_cabinet


def _user(cabinet, role, username):
    user = get_user_model().objects.create_user(username=username, password='pw-12345')
    UserCabinetRole.objects.create(user=user, cabinet=cabinet, role=role, status=ApprovalStatus.APPROVED)
    return user


class _Req:
    def __init__(self, user):
        self.user = user
        self.session = {}


def test_equivalent_roles():
    assert equivalent_roles(['CASHIER']) == ['CASHIER', 'ACCOUNTANT']
    assert equivalent_roles(['ACCOUNTANT', 'DIRECTOR']) == ['ACCOUNTANT', 'CASHIER', 'DIRECTOR']
    assert equivalent_roles(['ENGINEER']) == ['ENGINEER']


@pytest.mark.django_db
class TestSameAccess:
    def test_cashier_passes_an_accountant_only_check(self, cabinet):
        cashier = _user(cabinet, UserRoles.CASHIER, 'caisse_eq')
        assert can_act_for_cabinet(_Req(cashier), cabinet, ['ACCOUNTANT'])

    def test_accountant_passes_a_cashier_only_check(self, cabinet):
        accountant = _user(cabinet, UserRoles.ACCOUNTANT, 'compta_eq')
        assert can_act_for_cabinet(_Req(accountant), cabinet, ['CASHIER'])

    def test_other_roles_unchanged(self, cabinet):
        cashier = _user(cabinet, UserRoles.CASHIER, 'caisse_eq2')
        assert not can_act_for_cabinet(_Req(cashier), cabinet, ['DIRECTOR'])

    def test_role_required_view_and_template_filter(self, client, cabinet):
        # The Achats report is open to ACCOUNTANT and CASHIER already; the
        # purchase-order creation page to ACCOUNTANT only (not CASHIER).
        cashier = _user(cabinet, UserRoles.CASHIER, 'caisse_eq3')
        client.force_login(cashier)
        response = client.get(reverse('procurement:purchase_order_create'))
        assert response.status_code == 200
        from core.templatetags.rbac_tags import has_role
        assert has_role(cashier, 'ACCOUNTANT')

    @override_settings(ROLE_EQUIVALENCES=[])
    def test_switch_off_when_jobs_split(self, cabinet):
        cashier = _user(cabinet, UserRoles.CASHIER, 'caisse_eq4')
        assert not can_act_for_cabinet(_Req(cashier), cabinet, ['ACCOUNTANT'])
