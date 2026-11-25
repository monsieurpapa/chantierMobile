"""Superadmin audit journal ("Journal d'audit"): automatic capture
(core/audit.py) and the superuser-only screens (core/audit_views.py)."""
import pytest
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from accounts.models import CabinetContextLog
from chantiermobile.constants import AuditAction, SiteStatus
from core.audit import AuditContextMiddleware, SECRET_PLACEHOLDER
from core.models import AuditLogEntry


def entries_for(obj):
    return AuditLogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(type(obj)), object_id=str(obj.pk),
    ).order_by('timestamp', 'id')


def run_in_request(user, fn, ip='10.1.2.3'):
    """Run fn() as if inside a web request made by `user`."""
    request = RequestFactory().post('/projects/x/', HTTP_X_FORWARDED_FOR=f'{ip}, 172.16.0.1',
                                    HTTP_USER_AGENT='pytest-agent')
    request.user = user
    result = {}

    def view(req):
        result['value'] = fn()
        return HttpResponse('ok')

    AuditContextMiddleware(view)(request)
    return result['value']


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCapture:
    def test_create_is_journaled_with_actor_request_and_cabinet(self, user, cabinet, site_factory):
        site = run_in_request(user, lambda: site_factory(name='Chantier Himbi'))

        entry = entries_for(site).get()
        assert entry.action == AuditAction.CREATE
        assert entry.actor == user
        assert 'testuser' in entry.actor_label
        assert entry.cabinet_id == cabinet.pk
        assert entry.ip_address == '10.1.2.3'
        assert entry.request_method == 'POST'
        assert entry.user_agent == 'pytest-agent'
        assert entry.changes['name']['new'] == 'Chantier Himbi'
        assert entry.object_repr

    def test_update_records_field_diff_with_choice_labels(self, user, site):
        site.status = SiteStatus.ACTIVE
        run_in_request(user, site.save)

        entry = entries_for(site).filter(action=AuditAction.UPDATE).get()
        assert set(entry.changes) == {'status'}
        assert entry.changes['status']['old'] == str(SiteStatus.PLANNING.label)
        assert entry.changes['status']['new'] == str(SiteStatus.ACTIVE.label)

    def test_save_without_changes_writes_nothing(self, site):
        before = entries_for(site).count()
        site.save()
        assert entries_for(site).count() == before

    def test_soft_delete_and_restore(self, site):
        site.delete()
        site.restore()
        actions = list(entries_for(site).values_list('action', flat=True))
        assert actions[-2:] == [AuditAction.DELETE, AuditAction.RESTORE]

    def test_hard_delete(self, cabinet, site):
        from projects.models import Site
        pk = site.pk
        Site.all_objects.filter(pk=pk).delete()  # bypasses soft delete
        entry = AuditLogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Site), object_id=str(pk),
            action=AuditAction.HARD_DELETE,
        ).get()
        assert entry.cabinet_id == cabinet.pk

    def test_cabinet_resolved_through_parent_records(self, site):
        from projects.models import ProjectPhase
        phase = ProjectPhase.objects.create(site=site, name='Fondations')
        assert entries_for(phase).get().cabinet_id == site.cabinet_id

    def test_without_request_actor_is_system(self, site):
        entry = entries_for(site).get()
        assert entry.actor is None
        assert entry.actor_label == 'Système'
        assert entry.ip_address is None

    def test_password_is_never_written(self, user):
        user.set_password('NouveauMotDePasse!42')
        user.save()
        entry = entries_for(user).filter(action=AuditAction.UPDATE).get()
        assert entry.changes['password'] == {
            'label': entry.changes['password']['label'], 'old': SECRET_PLACEHOLDER, 'new': SECRET_PLACEHOLDER,
        }
        assert 'NouveauMotDePasse' not in str(entry.changes)

    def test_cabinet_switch_is_journaled(self, superuser, cabinet):
        CabinetContextLog.objects.create(cabinet=cabinet, switched_by=superuser, action=CabinetContextLog.SWITCH)
        entry = AuditLogEntry.objects.filter(action=AuditAction.CABINET_SWITCH).latest('id')
        assert entry.actor == superuser
        assert entry.cabinet_id == cabinet.pk

    def test_disabled_setting_records_nothing(self, settings, site_factory):
        settings.AUDIT_LOG_ENABLED = False
        site = site_factory()
        assert not entries_for(site).exists()

    def test_entries_are_append_only(self, site):
        entry = entries_for(site).get()
        entry.object_repr = 'falsifié'
        with pytest.raises(ValueError):
            entry.save()
        with pytest.raises(ValueError):
            entry.delete()


@pytest.mark.django_db
class TestAuthCapture:
    def test_login_and_logout(self, client, user):
        client.post(reverse('account_login'), {'login': 'testuser', 'password': 'testpass123'})
        client.post(reverse('account_logout'))
        actions = list(entries_for(user).filter(
            action__in=[AuditAction.LOGIN, AuditAction.LOGOUT]).values_list('action', flat=True))
        assert actions == [AuditAction.LOGIN, AuditAction.LOGOUT]
        login = entries_for(user).filter(action=AuditAction.LOGIN).get()
        assert login.actor == user
        assert login.ip_address == '127.0.0.1'

    def test_failed_login_keeps_identifier_but_not_password(self, client, user):
        client.post(reverse('account_login'), {'login': 'testuser', 'password': 'mauvais-secret'})
        entry = AuditLogEntry.objects.filter(action=AuditAction.LOGIN_FAILED).latest('id')
        assert entry.actor is None
        assert entry.actor_label == 'testuser'
        assert 'mauvais-secret' not in str(entry.__dict__)


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestJournalViews:
    def test_superuser_sees_journal_and_menu_entry(self, admin_client, site):
        response = admin_client.get(reverse('audit_log_list'))
        assert response.status_code == 200
        assert site.name in response.content.decode()
        assert reverse('audit_log_list') in admin_client.get(reverse('home')).content.decode()

    @pytest.mark.parametrize('name', ['audit_log_list', 'audit_log_export'])
    def test_non_superuser_is_refused(self, director_client, name):
        response = director_client.get(reverse(name))
        assert response.status_code == 302
        assert response.url == reverse('home')

    def test_anonymous_is_sent_to_login(self, client):
        response = client.get(reverse('audit_log_list'))
        assert response.status_code == 302
        assert 'login' in response.url

    def test_menu_entry_hidden_from_non_superusers(self, director_client):
        assert reverse('audit_log_list') not in director_client.get(reverse('home')).content.decode()

    def test_filters(self, admin_client, user, site_factory):
        mine = run_in_request(user, lambda: site_factory(name='Chantier Filtré'))
        other = site_factory(name='Chantier Système')

        content = admin_client.get(reverse('audit_log_list'), {'actor': user.pk}).content.decode()
        assert mine.name in content and other.name not in content

        ct = ContentType.objects.get_for_model(type(mine))
        content = admin_client.get(reverse('audit_log_list'),
                                   {'model': ct.pk, 'object_id': mine.pk}).content.decode()
        assert mine.name in content and other.name not in content

        mine.delete()
        content = admin_client.get(reverse('audit_log_list'),
                                   {'action': AuditAction.DELETE, 'q': 'Chantier'}).content.decode()
        assert mine.name in content and other.name not in content

    def test_detail_shows_diff_and_context(self, admin_client, user, site):
        site.status = SiteStatus.ACTIVE
        run_in_request(user, site.save)
        entry = entries_for(site).filter(action=AuditAction.UPDATE).get()

        response = admin_client.get(reverse('audit_log_detail', args=[entry.pk]))
        content = response.content.decode()
        assert response.status_code == 200
        assert str(SiteStatus.ACTIVE.label) in content
        assert '10.1.2.3' in content

    def test_csv_export_follows_filters(self, admin_client, user, site_factory):
        run_in_request(user, lambda: site_factory(name='Export Inclus'))
        site_factory(name='Export Exclu')

        response = admin_client.get(reverse('audit_log_export'), {'actor': user.pk})
        body = b''.join(response.streaming_content).decode('utf-8-sig')
        assert response['Content-Type'].startswith('text/csv')
        assert body.splitlines()[0].startswith('Date;Utilisateur;Action')
        assert 'Export Inclus' in body
        assert 'Export Exclu' not in body

    def test_user_and_cabinet_pages_link_to_their_journal(self, admin_client, user, cabinet):
        user_page = admin_client.get(reverse('accounts:admin_user_detail', args=[user.pk])).content.decode()
        assert f"{reverse('audit_log_list')}?actor={user.pk}" in user_page
        cab_page = admin_client.get(reverse('accounts:admin_cabinet_detail', args=[cabinet.pk])).content.decode()
        assert f"{reverse('audit_log_list')}?cabinet={cabinet.pk}" in cab_page

    def test_site_page_links_to_its_history_for_superusers_only(self, admin_client, user, site):
        from django.template import Context, Template

        ct = ContentType.objects.get_for_model(type(site))
        history_url = f"{reverse('audit_log_list')}?model={ct.pk}&amp;object_id={site.pk}"
        page = admin_client.get(reverse('projects:site_detail', kwargs={'unique_id': site.unique_id}))
        assert page.status_code == 200
        assert history_url in page.content.decode()

        tpl = Template("{% load audit_tags %}{% audit_history_url obj as u %}[{{ u }}]")
        request = RequestFactory().get('/')
        request.user = user  # not a superuser
        assert tpl.render(Context({'request': request, 'obj': site})) == '[]'

    @pytest.mark.parametrize('obj_fixture, url_name', [
        ('expense', 'finance:expense_detail'),
        ('invoice', 'revenue:invoice_detail'),
    ])
    def test_expense_and_invoice_pages_link_to_their_history(self, request, admin_client, obj_fixture, url_name):
        obj = request.getfixturevalue(obj_fixture)
        ct = ContentType.objects.get_for_model(type(obj))
        history_url = f"{reverse('audit_log_list')}?model={ct.pk}&amp;object_id={obj.pk}"
        page = admin_client.get(reverse(url_name, args=[obj.pk]))
        assert page.status_code == 200
        assert history_url in page.content.decode()

    @pytest.mark.parametrize('obj_fixture, url_name', [
        ('expense', 'finance:expense_detail'),
        ('invoice', 'revenue:invoice_detail'),
    ])
    def test_history_button_hidden_from_cabinet_members(self, request, director_client, obj_fixture, url_name):
        obj = request.getfixturevalue(obj_fixture)
        page = director_client.get(reverse(url_name, args=[obj.pk]))
        assert page.status_code == 200
        assert reverse('audit_log_list') not in page.content.decode()


@pytest.mark.django_db
class TestRetention:
    def test_purge_removes_only_entries_past_retention(self, settings, site):
        from datetime import timedelta
        from django.utils import timezone
        from core.tasks import purge_audit_log

        settings.AUDIT_LOG_RETENTION_DAYS = 30
        recent = entries_for(site).get()
        old = AuditLogEntry.objects.create(action=AuditAction.LOGIN, actor_label='ancien',
                                           timestamp=timezone.now() - timedelta(days=31))

        assert purge_audit_log() == 1
        assert not AuditLogEntry.objects.filter(pk=old.pk).exists()
        assert AuditLogEntry.objects.filter(pk=recent.pk).exists()

    def test_zero_retention_keeps_everything(self, settings, site):
        from core.tasks import purge_audit_log
        settings.AUDIT_LOG_RETENTION_DAYS = 0
        assert purge_audit_log() == 0
        assert entries_for(site).exists()
