"""
Tests for the multi-cabinet (multi-tenant) data-isolation gaps found during
a SaaS-readiness audit and fixed in this phase:

1. ProjectPhase create/update/delete views had NO cabinet check at all —
   a cross-tenant IDOR letting a Director in Cabinet A read/edit/delete a
   phase belonging to Cabinet B just by knowing (or guessing) its id.
   Fixed: ProjectPhaseCreateView now resolves `site_id` against a
   cabinet-scoped queryset and scopes the role check to that site's
   cabinet; ProjectPhaseUpdateView/DeleteView now use CabinetAccessMixin
   like every sibling Update/Delete view in the app (Site, Budget, ...).

2. MaterialRequestListView ignored a superuser's active-cabinet switch —
   switching into a cabinet didn't narrow this one list, unlike every
   other cabinet-scoped list in the app.

3. PriceLibraryItemCreateView / DQECreateView could silently mis-tag a
   new record to the wrong cabinet for a user who holds roles in more
   than one cabinet (`cabinet_roles.first()` picks arbitrarily). Fixed by
   centralizing cabinet resolution in
   CabinetAccessMixin.get_user_cabinet(), which no longer guesses for an
   ambiguous multi-cabinet user, and by having those two forms add an
   explicit 'cabinet' field (CabinetAccessMixin.get_ambiguous_cabinet_
   choices, scoped to only the requester's own cabinets) when
   get_user_cabinet() can't resolve one on its own — so a multi-cabinet
   user gets a way to say which cabinet they mean instead of either a
   silent guess or being flatly blocked. This is deliberately local to
   the two affected forms rather than a global per-page cabinet
   switcher, which would add a DB query to every request for every
   regular user (see TestSwitchCabinetViewForRegularUsers below).
"""
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse

from accounts.models import Cabinet, UserCabinetRole
from chantiermobile.constants import UserRoles, ApprovalStatus
from core.mixins import get_session_cabinet


# ---------------------------------------------------------------------
# Shared fixtures: a second, unrelated cabinet ("Cabinet B") and a user
# who legitimately belongs to both cabinets.
# ---------------------------------------------------------------------

@pytest.fixture
def cabinet_b(db):
    return Cabinet.objects.create(name='Cabinet B', address='456 Other St', tax_id='OTHER456')


@pytest.fixture
def site_b(db, site_factory, cabinet_b):
    return site_factory(cabinet=cabinet_b, name='Site B')


@pytest.fixture
def phase_b(db, site_b, phase_factory):
    return phase_factory(site_b, name='Phase B')


@pytest.fixture
def multi_cabinet_director(db, cabinet, cabinet_b):
    """A director with an approved role in both `cabinet` and `cabinet_b`."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = User.objects.create_user(username='multi_director', password='testpass123')
    UserCabinetRole.objects.create(user=u, cabinet=cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
    UserCabinetRole.objects.create(user=u, cabinet=cabinet_b, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
    return u


@pytest.fixture
def multi_cabinet_client(client, multi_cabinet_director):
    client.login(username='multi_director', password='testpass123')
    return client


# ---------------------------------------------------------------------
# 1. ProjectPhase cross-cabinet IDOR
# ---------------------------------------------------------------------

@pytest.mark.django_db
class TestProjectPhaseCabinetIsolation:
    def test_create_rejects_foreign_cabinet_site(self, director_client, site_b):
        """director_client's user only holds a role on `cabinet`
        (fixture) — site_b belongs to a different cabinet entirely."""
        url = reverse('projects:phase_create', kwargs={'site_id': site_b.unique_id})
        response = director_client.post(url, {
            'name': 'Sneaky Phase', 'start_date': date.today().isoformat(),
        })
        assert response.status_code == 404
        from projects.models import ProjectPhase
        assert not ProjectPhase.objects.filter(name='Sneaky Phase').exists()

    def test_create_succeeds_for_own_cabinet_site(self, director_client, site):
        url = reverse('projects:phase_create', kwargs={'site_id': site.unique_id})
        response = director_client.post(url, {
            'name': 'Legit Phase', 'start_date': date.today().isoformat(),
        })
        from projects.models import ProjectPhase
        assert ProjectPhase.objects.filter(name='Legit Phase', site=site).exists()
        assert response.status_code == 302

    def test_update_view_404s_for_foreign_cabinet_phase(self, director_client, phase_b):
        url = reverse('projects:phase_update', kwargs={'unique_id': phase_b.unique_id})
        response = director_client.get(url)
        assert response.status_code == 404

    def test_update_view_works_for_own_cabinet_phase(self, director_client, phase):
        url = reverse('projects:phase_update', kwargs={'unique_id': phase.unique_id})
        response = director_client.get(url)
        assert response.status_code == 200

    def test_delete_view_404s_for_foreign_cabinet_phase(self, director_client, phase_b):
        url = reverse('projects:phase_delete', kwargs={'unique_id': phase_b.unique_id})
        response = director_client.post(url)
        assert response.status_code == 404
        phase_b.refresh_from_db()

    def test_delete_view_works_for_own_cabinet_phase(self, director_client, phase):
        url = reverse('projects:phase_delete', kwargs={'unique_id': phase.unique_id})
        response = director_client.post(url)
        assert response.status_code == 302
        from projects.models import ProjectPhase
        assert not ProjectPhase.objects.filter(pk=phase.pk).exists()

    def test_superuser_still_unrestricted(self, admin_client, site_b):
        """Superusers bypass RoleRequiredMixin entirely (pre-existing,
        documented behavior) — this fix must not touch that."""
        url = reverse('projects:phase_create', kwargs={'site_id': site_b.unique_id})
        response = admin_client.post(url, {
            'name': 'Admin Phase', 'start_date': date.today().isoformat(),
        })
        from projects.models import ProjectPhase
        assert ProjectPhase.objects.filter(name='Admin Phase', site=site_b).exists()
        assert response.status_code == 302


# ---------------------------------------------------------------------
# 2. MaterialRequestListView + superuser cabinet switch
# ---------------------------------------------------------------------

@pytest.mark.django_db
class TestMaterialRequestListSuperuserCabinetSwitch:
    def test_superuser_without_switch_sees_every_cabinet(self, admin_client, material_request_factory, site, site_b):
        mr_a = material_request_factory(site=site)
        mr_b = material_request_factory(site=site_b)
        response = admin_client.get(reverse('materials:request_list'))
        ids = {r.pk for r in response.context['requests']}
        assert mr_a.pk in ids
        assert mr_b.pk in ids

    def test_superuser_switched_cabinet_sees_only_that_cabinet(self, admin_client, cabinet, material_request_factory, site, site_b):
        mr_a = material_request_factory(site=site)
        mr_b = material_request_factory(site=site_b)
        switch = admin_client.post(reverse('accounts:switch_cabinet'), {'cabinet_id': cabinet.pk})
        assert switch.status_code == 302
        response = admin_client.get(reverse('materials:request_list'))
        ids = {r.pk for r in response.context['requests']}
        assert mr_a.pk in ids
        assert mr_b.pk not in ids


# ---------------------------------------------------------------------
# 3a. Cabinet switcher now available to (and safely scoped for) a
#     multi-cabinet regular user, not just superusers.
# ---------------------------------------------------------------------

@pytest.mark.django_db
class TestSwitchCabinetViewForRegularUsers:
    def test_multi_cabinet_user_can_switch_into_own_cabinet(self, multi_cabinet_client, cabinet_b):
        response = multi_cabinet_client.post(reverse('accounts:switch_cabinet'), {'cabinet_id': cabinet_b.pk})
        assert response.status_code == 302
        assert multi_cabinet_client.session.get('active_cabinet_id') == cabinet_b.pk

    def test_regular_user_cannot_switch_into_a_cabinet_they_dont_belong_to(self, director_client, cabinet_b):
        """director_client's user has no role at all on cabinet_b."""
        response = director_client.post(reverse('accounts:switch_cabinet'), {'cabinet_id': cabinet_b.pk})
        assert response.status_code == 404
        assert 'active_cabinet_id' not in director_client.session

    def test_clearing_active_cabinet_works_for_regular_user(self, multi_cabinet_client, cabinet_b):
        multi_cabinet_client.post(reverse('accounts:switch_cabinet'), {'cabinet_id': cabinet_b.pk})
        response = multi_cabinet_client.post(reverse('accounts:switch_cabinet'), {'cabinet_id': ''})
        assert response.status_code == 302
        assert 'active_cabinet_id' not in multi_cabinet_client.session

    def test_active_cabinet_context_stays_superuser_only(self, multi_cabinet_client, director_client):
        """The global per-page cabinet-switcher context processor was
        deliberately NOT extended to regular users — doing so added a
        query to every single page load for every non-superuser (see
        tests/test_performance.py's query-count budgets), just to serve a
        rare case. Regular multi-cabinet disambiguation is instead
        resolved locally on the specific creation forms that need it
        (see TestCreateViewCabinetMistaggingFix) — this test pins that
        the global context processor is unaffected, for both a
        single-cabinet and a multi-cabinet regular user."""
        for client in (director_client, multi_cabinet_client):
            response = client.get(reverse('projects:site_list'))
            assert 'all_cabinets' not in response.context
            assert 'active_cabinet' not in response.context


# ---------------------------------------------------------------------
# 3b. get_session_cabinet() re-validates a non-superuser's session value
# ---------------------------------------------------------------------

@pytest.mark.django_db
class TestGetSessionCabinetRevalidation:
    def test_stale_foreign_cabinet_in_session_is_ignored_and_cleared(self, rf, multi_cabinet_director, cabinet_b):
        """Simulates a role revoked after the user switched into
        cabinet_b: a value already sitting in the session must never be
        trusted blindly for a non-superuser."""
        from django.contrib.sessions.middleware import SessionMiddleware
        UserCabinetRole.objects.filter(user=multi_cabinet_director, cabinet=cabinet_b).delete()

        request = rf.get('/')
        request.user = multi_cabinet_director
        SessionMiddleware(lambda r: None).process_request(request)
        request.session['active_cabinet_id'] = cabinet_b.pk
        request.session.save()

        assert get_session_cabinet(request) is None
        assert 'active_cabinet_id' not in request.session


# ---------------------------------------------------------------------
# 3c. Creation flows no longer silently mis-tag a multi-cabinet user's
#     new record.
# ---------------------------------------------------------------------

@pytest.mark.django_db
class TestCreateViewCabinetMistaggingFix:
    def test_single_cabinet_director_creates_price_item_normally(self, director_client, cabinet):
        response = director_client.post(reverse('pricing:price_item_create'), {
            'code': 'MO-001', 'designation': 'Maçon', 'item_type': 'LABOR',
            'unit': 'jour', 'unit_price': '15.00', 'is_active': 'on',
        })
        from pricing.models import PriceLibraryItem
        item = PriceLibraryItem.objects.get(code='MO-001')
        assert item.cabinet == cabinet
        assert response.status_code == 302

    def test_multi_cabinet_director_without_active_cabinet_is_blocked(self, multi_cabinet_client):
        """No 'cabinet' choice submitted at all — the field the ambiguous
        case adds is required, so the form simply fails validation."""
        response = multi_cabinet_client.post(reverse('pricing:price_item_create'), {
            'code': 'MO-002', 'designation': 'Maçon', 'item_type': 'LABOR',
            'unit': 'jour', 'unit_price': '15.00', 'is_active': 'on',
        })
        from pricing.models import PriceLibraryItem
        assert response.status_code == 200  # form re-rendered, not redirected
        assert not PriceLibraryItem.objects.filter(code='MO-002').exists()

    def test_multi_cabinet_director_gets_explicit_cabinet_field(self, multi_cabinet_client):
        """get_ambiguous_cabinet_choices() surfaces an inline 'cabinet'
        field on the form itself (rather than only the superuser-only
        navbar switcher), scoped to just this user's own two cabinets."""
        response = multi_cabinet_client.get(reverse('pricing:price_item_create'))
        assert 'cabinet' in response.context['form'].fields
        pks = set(response.context['form'].fields['cabinet'].queryset.values_list('pk', flat=True))
        director = response.wsgi_request.user
        expected = set(Cabinet.objects.filter(user_roles__user=director).values_list('pk', flat=True))
        assert pks == expected

    def test_multi_cabinet_director_resolves_via_explicit_cabinet_field(self, multi_cabinet_client, cabinet_b):
        """Submitting the inline 'cabinet' field tags the new record
        correctly, with no prior session switch needed."""
        response = multi_cabinet_client.post(reverse('pricing:price_item_create'), {
            'code': 'MO-004', 'designation': 'Maçon', 'item_type': 'LABOR',
            'unit': 'jour', 'unit_price': '15.00', 'is_active': 'on',
            'cabinet': str(cabinet_b.pk),
        })
        from pricing.models import PriceLibraryItem
        item = PriceLibraryItem.objects.get(code='MO-004')
        assert item.cabinet == cabinet_b
        assert response.status_code == 302

    def test_multi_cabinet_director_cannot_submit_a_foreign_cabinet_id(self, multi_cabinet_client, cabinet_b):
        """The inline field's queryset is scoped to the requester's own
        cabinets, so Django's ModelChoiceField rejects any other pk —
        this is the actual guard against mis-tagging, not just UI."""
        foreign = Cabinet.objects.create(name='Foreign Cabinet', address='x', tax_id='FOREIGN1')
        response = multi_cabinet_client.post(reverse('pricing:price_item_create'), {
            'code': 'MO-005', 'designation': 'Maçon', 'item_type': 'LABOR',
            'unit': 'jour', 'unit_price': '15.00', 'is_active': 'on',
            'cabinet': str(foreign.pk),
        })
        from pricing.models import PriceLibraryItem
        assert response.status_code == 200
        assert not PriceLibraryItem.objects.filter(code='MO-005').exists()

    def test_multi_cabinet_director_with_active_cabinet_tags_correctly(self, multi_cabinet_client, cabinet_b):
        switch = multi_cabinet_client.post(reverse('accounts:switch_cabinet'), {'cabinet_id': cabinet_b.pk})
        assert switch.status_code == 302
        response = multi_cabinet_client.post(reverse('pricing:price_item_create'), {
            'code': 'MO-003', 'designation': 'Maçon', 'item_type': 'LABOR',
            'unit': 'jour', 'unit_price': '15.00', 'is_active': 'on',
        })
        from pricing.models import PriceLibraryItem
        item = PriceLibraryItem.objects.get(code='MO-003')
        assert item.cabinet == cabinet_b
        assert response.status_code == 302

    def test_dqe_create_blocked_for_ambiguous_multi_cabinet_user(self, multi_cabinet_client):
        response = multi_cabinet_client.post(reverse('pricing:dqe_create'), {
            'reference': 'DQE-2026-001', 'title': 'Test DQE', 'status': 'DRAFT', 'notes': '',
            # Formset management data included only so the template can
            # render the (empty) lines table without erroring — the
            # cabinet check runs and blocks before the formset is
            # ever consulted.
            'lines-TOTAL_FORMS': '0', 'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '0', 'lines-MAX_NUM_FORMS': '1000',
        })
        from pricing.models import DQE
        assert response.status_code == 200
        assert not DQE.objects.filter(reference='DQE-2026-001').exists()

    def test_dqe_create_succeeds_for_single_cabinet_director(self, director_client, cabinet):
        from pricing.models import PriceLibraryItem
        price_item = PriceLibraryItem.objects.create(
            cabinet=cabinet, code='MAT-001', designation='Ciment', item_type='MATERIAL',
            unit='sac', unit_price=Decimal('12.50'),
        )
        response = director_client.post(reverse('pricing:dqe_create'), {
            'reference': 'DQE-2026-002', 'title': 'Test DQE', 'status': 'DRAFT', 'notes': '',
            'lines-TOTAL_FORMS': '1', 'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '0', 'lines-MAX_NUM_FORMS': '1000',
            'lines-0-price_item': str(price_item.pk),
            'lines-0-designation': '',
            'lines-0-quantity': '10',
            'lines-0-unit_price': '12.50',
        })
        from pricing.models import DQE
        dqe = DQE.objects.get(reference='DQE-2026-002')
        assert dqe.cabinet == cabinet
        assert dqe.lines.count() == 1
        assert response.status_code == 302
