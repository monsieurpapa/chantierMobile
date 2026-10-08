"""
Tests for item 13 of the Directors/Engineers audit: there were no in-app
notifications at all — only one email trigger (revenue/notifications.py's
notify_directors_of_payment) and the pending-approvals inbox (item 12),
which only shows what's still outstanding, not what changed. Every
workflow that already has a role-gated approval step now also drops a
core.models.Notification row on both sides of the decision: to the role
holders who can act, when something new needs a decision, and back to
the requester once it's decided. This file checks a representative slice
(Expense and MaterialRequest, both directions) plus the notification
inbox UI itself (list, open-and-mark-read, mark-all-read, unread badge).
"""
import pytest
from datetime import date
from decimal import Decimal
from django.urls import reverse

from accounts.models import UserCabinetRole
from chantiermobile.constants import UserRoles, ApprovalStatus, ExpenseStatus, MaterialRequestStatus
from core.models import Notification
from finance.models import Expense
from materials.models import Material, MaterialRequest, MaterialRequestItem


@pytest.fixture
def accountant_client_same_cabinet(client, cabinet, django_user_model):
    """A second cabinet member (accountant) distinct from `director_client`'s
    `user`, so we can check the accountant gets notified of the director's
    submission without receiving their own notification back."""
    accountant = django_user_model.objects.create_user(username='notif_accountant', password='testpass123')
    UserCabinetRole.objects.create(user=accountant, cabinet=cabinet, role=UserRoles.ACCOUNTANT, status=ApprovalStatus.APPROVED)
    return accountant


@pytest.mark.django_db
class TestExpenseNotifications:
    def test_submitting_expense_notifies_approval_roles(self, director_client, user, site, expense_category, accountant_client_same_cabinet):
        response = director_client.post(reverse('finance:expense_create'), {
            'site': site.pk,
            'category': expense_category.pk,
            'amount': '1500.75',
            'expense_date': date.today(),
            'description': 'Ciment et sable',
        }, follow=True)
        assert response.status_code == 200

        notifications = Notification.objects.filter(recipient=accountant_client_same_cabinet)
        assert notifications.exists()
        assert 'Ciment et sable' in notifications.first().message

        # The submitter doesn't notify themselves.
        assert not Notification.objects.filter(recipient=user).exists()

    def test_approving_expense_notifies_requester(self, director_client, accountant_client_same_cabinet, site, expense_category):
        # requester must differ from the approving director — Expense.approve()
        # blocks approving your own request, so a same-user test would never
        # reach the notify_user() call.
        expense = Expense.objects.create(
            site=site, requester=accountant_client_same_cabinet, category=expense_category,
            amount=Decimal('500.00'), expense_date=date.today(),
            description='Peinture', status=ExpenseStatus.PENDING,
        )
        response = director_client.post(reverse('finance:expense_approve', kwargs={'pk': expense.pk}))
        assert response.status_code == 302

        notification = Notification.objects.get(recipient=accountant_client_same_cabinet)
        assert 'approuvée' in notification.message
        assert not notification.is_read

    def test_rejecting_expense_notifies_requester(self, director_client, site, user, expense_category):
        expense = Expense.objects.create(
            site=site, requester=user, category=expense_category,
            amount=Decimal('500.00'), expense_date=date.today(),
            description='Peinture', status=ExpenseStatus.PENDING,
        )
        director_client.post(reverse('finance:expense_reject', kwargs={'pk': expense.pk}))

        notification = Notification.objects.get(recipient=user)
        assert 'rejetée' in notification.message


@pytest.mark.django_db
class TestMaterialRequestNotifications:
    def test_submitting_request_notifies_final_authorizers(self, engineer_client, engineer_user, site, cabinet, django_user_model):
        """Submission is single-stage (changed 2026-10-08): the site's own
        lead_engineer submits, and the notification goes straight to
        FINAL_AUTHORIZATION_ROLES — there is no magasinier validation
        step to notify first."""
        director = django_user_model.objects.create_user(username='notif_director', password='testpass123')
        UserCabinetRole.objects.create(user=director, cabinet=cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
        site.lead_engineer = engineer_user
        site.save(update_fields=['lead_engineer'])
        material = Material.objects.create(name='Ciment', unit='sac')

        response = engineer_client.post(reverse('materials:request_create'), {
            'site': site.pk,
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-material': material.pk,
            'items-0-quantity': '5',
        }, follow=True)
        assert response.status_code == 200

        assert Notification.objects.filter(recipient=director).exists()
        assert not Notification.objects.filter(recipient=engineer_user).exists()

    def test_authorizing_request_notifies_requester(self, director_client, site, engineer_user):
        material = Material.objects.create(name='Sable', unit='m3')
        mat_request = MaterialRequest.objects.create(site=site, status=MaterialRequestStatus.PENDING, requested_by=engineer_user)
        MaterialRequestItem.objects.create(request=mat_request, material=material, quantity=Decimal('2.00'))

        director_client.post(reverse('materials:request_approve', kwargs={'pk': mat_request.pk}), {'action': 'authorize'})

        notification = Notification.objects.get(recipient=engineer_user)
        assert 'autorisée' in notification.message


@pytest.mark.django_db
class TestNotificationInbox:
    def test_list_view_shows_own_notifications_only(self, director_client, user, django_user_model):
        Notification.objects.create(recipient=user, message='Pour moi', url='/x/')
        other = django_user_model.objects.create_user(username='someone_else', password='testpass123')
        Notification.objects.create(recipient=other, message='Pas pour moi', url='/y/')

        response = director_client.get(reverse('notifications_list'))
        assert response.status_code == 200
        messages_shown = [n.message for n in response.context['notifications']]
        assert 'Pour moi' in messages_shown
        assert 'Pas pour moi' not in messages_shown

    def test_opening_notification_marks_it_read_and_redirects(self, director_client, user):
        notification = Notification.objects.create(recipient=user, message='Test', url='/finance/expenses/')
        response = director_client.get(reverse('notification_open', kwargs={'pk': notification.pk}))
        assert response.status_code == 302
        assert response['Location'] == '/finance/expenses/'
        notification.refresh_from_db()
        assert notification.is_read

    def test_cannot_open_someone_elses_notification(self, director_client, django_user_model):
        other = django_user_model.objects.create_user(username='not_me', password='testpass123')
        notification = Notification.objects.create(recipient=other, message='Test', url='/x/')
        response = director_client.get(reverse('notification_open', kwargs={'pk': notification.pk}))
        assert response.status_code == 404

    def test_mark_all_read(self, director_client, user):
        Notification.objects.create(recipient=user, message='A', url='/a/')
        Notification.objects.create(recipient=user, message='B', url='/b/')
        director_client.post(reverse('notifications_mark_all_read'))
        assert not Notification.objects.filter(recipient=user, is_read=False).exists()

    def test_unread_badge_count_in_navbar(self, director_client, user):
        Notification.objects.create(recipient=user, message='A', url='/a/')
        Notification.objects.create(recipient=user, message='B', url='/b/')
        response = director_client.get(reverse('home'))
        assert response.context['unread_notifications_count'] == 2

    def test_read_notification_does_not_count_toward_badge(self, director_client, user):
        Notification.objects.create(recipient=user, message='A', url='/a/', is_read=True)
        response = director_client.get(reverse('home'))
        assert response.context['unread_notifications_count'] == 0
