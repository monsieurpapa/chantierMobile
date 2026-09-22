"""
Tests for the superadmin User / UserCabinetRole CRUD surface added to
close the gaps found in the feature-vs-proposal audit: creating users
from the UI, resetting a user's password on their behalf, one-click
activate/deactivate, one-click approve/reject of a cabinet role request,
a system-wide role-assignments view, and guards against a superadmin
accidentally locking themselves out (self-demotion, self-deactivation).
"""
import re

import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

from accounts.models import UserCabinetRole, Cabinet
from chantiermobile.constants import UserRoles, ApprovalStatus

User = get_user_model()

TEMP_PASSWORD_RE = re.compile(r'(Cm-[A-Za-z0-9]{10}!)')


def _extract_temp_password(response):
    messages = [str(m) for m in response.context['messages']]
    for m in messages:
        match = TEMP_PASSWORD_RE.search(m)
        if match:
            return match.group(1)
    return None


@pytest.mark.django_db
class TestUserCreateAdmin:
    def test_superadmin_can_create_user(self, admin_client):
        url = reverse('accounts:admin_user_create')
        response = admin_client.post(url, {
            'username': 'brandnewuser',
            'first_name': 'Brand',
            'last_name': 'New',
            'email': 'brandnew@example.com',
            'phone_number': '',
            'is_active': 'on',
        }, follow=True)
        assert response.status_code == 200
        new_user = User.objects.get(username='brandnewuser')
        assert new_user.email == 'brandnew@example.com'
        assert new_user.is_active is True
        assert new_user.is_staff is False
        assert new_user.is_superuser is False
        # A real, usable random password was set (not blank/unusable).
        assert new_user.has_usable_password()
        assert new_user.must_change_password is True

    def test_created_password_is_shown_once_and_works(self, admin_client):
        url = reverse('accounts:admin_user_create')
        response = admin_client.post(url, {
            'username': 'pwdcheckuser',
            'first_name': '', 'last_name': '',
            'email': 'pwdcheck@example.com',
            'phone_number': '', 'is_active': 'on',
        }, follow=True)
        temp_password = _extract_temp_password(response)
        assert temp_password, "Temporary password was not shown in the success message"

        from django.test import Client
        fresh_client = Client()
        logged_in = fresh_client.login(username='pwdcheckuser', password=temp_password)
        assert logged_in is True

    def test_non_superadmin_cannot_create_user(self, director_client):
        url = reverse('accounts:admin_user_create')
        response = director_client.post(url, {
            'username': 'shouldnotexist',
            'email': 'nope@example.com',
        })
        assert response.status_code == 302
        assert not User.objects.filter(username='shouldnotexist').exists()

    def test_duplicate_username_rejected(self, admin_client, user):
        url = reverse('accounts:admin_user_create')
        response = admin_client.post(url, {
            'username': user.username,
            'email': 'dupe@example.com',
        })
        assert response.status_code == 200  # form re-rendered with error
        assert User.objects.filter(username=user.username).count() == 1


@pytest.mark.django_db
class TestUserResetPasswordAdmin:
    def test_superadmin_resets_another_users_password(self, admin_client, user):
        old_password_hash = user.password
        url = reverse('accounts:admin_user_reset_password', kwargs={'pk': user.pk})
        response = admin_client.post(url, follow=True)
        assert response.status_code == 200

        user.refresh_from_db()
        assert user.password != old_password_hash
        assert user.must_change_password is True

        temp_password = _extract_temp_password(response)
        assert temp_password
        from django.test import Client
        fresh_client = Client()
        assert fresh_client.login(username=user.username, password=temp_password) is True
        # The old password no longer works.
        assert fresh_client.login(username=user.username, password='testpass123') is False

    def test_self_reset_keeps_session_alive(self, admin_client, superuser):
        url = reverse('accounts:admin_user_reset_password', kwargs={'pk': superuser.pk})
        response = admin_client.post(url, follow=True)
        assert response.status_code == 200
        # Still authenticated (update_session_auth_hash prevented a forced
        # logout) — the next request is redirected to the forced
        # password-change page by ForcePasswordChangeMiddleware rather than
        # bounced all the way back to the login page.
        check = admin_client.get(reverse('accounts:admin_users_list'))
        assert check.status_code == 302
        assert check.url == reverse('account_change_password')

    def test_non_superadmin_cannot_reset_password(self, director_client, user):
        old_hash = user.password
        url = reverse('accounts:admin_user_reset_password', kwargs={'pk': user.pk})
        response = director_client.post(url)
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.password == old_hash


@pytest.mark.django_db
class TestUserToggleActiveAdmin:
    def test_superadmin_can_deactivate_and_reactivate(self, admin_client, user):
        assert user.is_active is True
        url = reverse('accounts:admin_user_toggle_active', kwargs={'pk': user.pk})

        response = admin_client.post(url, follow=True)
        user.refresh_from_db()
        assert user.is_active is False

        response = admin_client.post(url, follow=True)
        user.refresh_from_db()
        assert user.is_active is True

    def test_superadmin_cannot_deactivate_self(self, admin_client, superuser):
        url = reverse('accounts:admin_user_toggle_active', kwargs={'pk': superuser.pk})
        response = admin_client.post(url, follow=True)
        superuser.refresh_from_db()
        assert superuser.is_active is True
        messages = [str(m) for m in response.context['messages']]
        assert any('cannot deactivate your own account' in m.lower() for m in messages)

    def test_non_superadmin_cannot_toggle(self, director_client, user):
        url = reverse('accounts:admin_user_toggle_active', kwargs={'pk': user.pk})
        response = director_client.post(url)
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.is_active is True


@pytest.mark.django_db
class TestUserEditSelfDemotionGuard:
    def test_superadmin_cannot_revoke_own_access_via_edit_form(self, admin_client, superuser):
        url = reverse('accounts:admin_user_edit', kwargs={'pk': superuser.pk})
        response = admin_client.post(url, {
            'first_name': 'Changed',
            'last_name': superuser.last_name,
            'email': superuser.email,
            'phone_number': '',
            # Deliberately omit is_active/is_staff/is_superuser -> unchecked
        }, follow=True)
        assert response.status_code == 200
        superuser.refresh_from_db()
        # Profile field change still applied...
        assert superuser.first_name == 'Changed'
        # ...but the self-demotion was blocked.
        assert superuser.is_active is True
        assert superuser.is_staff is True
        assert superuser.is_superuser is True
        messages = [str(m) for m in response.context['messages']]
        assert any('cannot' in m.lower() for m in messages)

    def test_superadmin_can_demote_a_different_superadmin(self, admin_client, superuser):
        other_admin = User.objects.create_superuser(
            username='otheradmin', email='other@example.com', password='testpass123'
        )
        url = reverse('accounts:admin_user_edit', kwargs={'pk': other_admin.pk})
        response = admin_client.post(url, {
            'first_name': '', 'last_name': '', 'email': other_admin.email,
            'phone_number': '',
            # is_active/is_staff/is_superuser omitted -> False
        }, follow=True)
        assert response.status_code == 200
        other_admin.refresh_from_db()
        assert other_admin.is_superuser is False
        assert other_admin.is_staff is False
        assert other_admin.is_active is False


@pytest.mark.django_db
class TestCabinetUserRoleQuickStatus:
    def test_one_click_approve(self, admin_client, user, cabinet):
        role = UserCabinetRole.objects.create(
            user=user, cabinet=cabinet, role=UserRoles.ENGINEER, status=ApprovalStatus.PENDING
        )
        url = reverse('accounts:admin_cabinet_user_role_status', kwargs={'pk': role.pk})
        response = admin_client.post(url, {'status': 'APPROVED'}, follow=True)
        assert response.status_code == 200
        role.refresh_from_db()
        assert role.status == ApprovalStatus.APPROVED

    def test_one_click_reject(self, admin_client, user, cabinet):
        role = UserCabinetRole.objects.create(
            user=user, cabinet=cabinet, role=UserRoles.ENGINEER, status=ApprovalStatus.PENDING
        )
        url = reverse('accounts:admin_cabinet_user_role_status', kwargs={'pk': role.pk})
        response = admin_client.post(url, {'status': 'REJECTED'}, follow=True)
        role.refresh_from_db()
        assert role.status == ApprovalStatus.REJECTED

    def test_invalid_status_rejected(self, admin_client, user, cabinet):
        role = UserCabinetRole.objects.create(
            user=user, cabinet=cabinet, role=UserRoles.ENGINEER, status=ApprovalStatus.PENDING
        )
        url = reverse('accounts:admin_cabinet_user_role_status', kwargs={'pk': role.pk})
        response = admin_client.post(url, {'status': 'NOT_A_REAL_STATUS'}, follow=True)
        role.refresh_from_db()
        assert role.status == ApprovalStatus.PENDING

    def test_non_superadmin_cannot_change_status(self, director_client, user, cabinet):
        other_user = User.objects.create_user(username='someoneelse', password='testpass123')
        role = UserCabinetRole.objects.create(
            user=other_user, cabinet=cabinet, role=UserRoles.ENGINEER, status=ApprovalStatus.PENDING
        )
        url = reverse('accounts:admin_cabinet_user_role_status', kwargs={'pk': role.pk})
        response = director_client.post(url, {'status': 'APPROVED'})
        assert response.status_code == 302
        role.refresh_from_db()
        assert role.status == ApprovalStatus.PENDING


@pytest.mark.django_db
class TestRoleAssignmentListAdmin:
    def test_lists_roles_across_all_cabinets(self, admin_client, cabinet, user):
        other_cabinet = Cabinet.objects.create(name='Second Cabinet')
        other_user = User.objects.create_user(username='seconduser', password='testpass123')
        UserCabinetRole.objects.create(user=user, cabinet=cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
        UserCabinetRole.objects.create(user=other_user, cabinet=other_cabinet, role=UserRoles.CASHIER, status=ApprovalStatus.PENDING)

        url = reverse('accounts:admin_role_assignments_list')
        response = admin_client.get(url)
        assert response.status_code == 200
        roles = list(response.context['roles'])
        assert len(roles) == 2

    def test_filters_by_status(self, admin_client, cabinet, user):
        UserCabinetRole.objects.create(user=user, cabinet=cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
        other_user = User.objects.create_user(username='pendinguser', password='testpass123')
        UserCabinetRole.objects.create(user=other_user, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.PENDING)

        url = reverse('accounts:admin_role_assignments_list')
        response = admin_client.get(url, {'status': 'PENDING'})
        roles = list(response.context['roles'])
        assert len(roles) == 1
        assert roles[0].user == other_user

    def test_filters_by_search(self, admin_client, cabinet, user):
        UserCabinetRole.objects.create(user=user, cabinet=cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
        url = reverse('accounts:admin_role_assignments_list')
        response = admin_client.get(url, {'search': user.username})
        roles = list(response.context['roles'])
        assert len(roles) == 1

    def test_non_superadmin_cannot_access(self, director_client):
        url = reverse('accounts:admin_role_assignments_list')
        response = director_client.get(url)
        assert response.status_code == 302


@pytest.mark.django_db
class TestAdminTemplatesRender:
    def test_create_user_form_renders(self, admin_client):
        response = admin_client.get(reverse('accounts:admin_user_create'))
        assert response.status_code == 200
        assert b'id_username' in response.content

    def test_cabinet_detail_pending_approve_reject_buttons_render(self, admin_client, cabinet, user):
        UserCabinetRole.objects.create(
            user=user, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.PENDING
        )
        response = admin_client.get(reverse('accounts:admin_cabinet_detail', kwargs={'pk': cabinet.pk}))
        assert response.status_code == 200
        assert b'admin_cabinet_user_role_status' not in response.content  # URL names aren't leaked raw
        assert reverse('accounts:admin_cabinet_user_role_status', kwargs={'pk': UserCabinetRole.objects.first().pk}).encode() in response.content

    def test_user_detail_edit_link_uses_app_view_not_django_admin(self, admin_client, cabinet, user):
        UserCabinetRole.objects.create(
            user=user, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED
        )
        response = admin_client.get(reverse('accounts:admin_user_detail', kwargs={'pk': user.pk}))
        assert response.status_code == 200
        assert b'admin:accounts_usercabinetrole_change' not in response.content
