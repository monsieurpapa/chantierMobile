"""
Tests for the Devis / État de besoin comparison feature (2026-10-07):

- ProjectPhase.parent_phase — one-level-deep sous-étape hierarchy.
- PriceLibraryItem.work_category / material — required per item_type.
- DQELine.phase + exploded_requirements() — the ratio/explosion engine
  that turns a WORK_ITEM quantity into elementary material quantities,
  and a MATERIAL-type line's direct quantity.
- pricing.MaterialConsumptionRatio — global-default vs cabinet-override.
- pricing.services.compare_material_usage/material_request_variance_report
  /has_red_variance — the red/orange/green comparison engine.
- MaterialRequestItem.phase — same-site validation.
- MaterialRequest.authorize()'s soft-overage overage_justification
  requirement.
- accounts.Cabinet's material-variance threshold fields.
- revenue.Devis.source_dqe.
"""
import pytest
from decimal import Decimal
from datetime import date
from django.core.exceptions import ValidationError

from projects.models import ProjectPhase
from pricing.models import PriceLibraryItem, DQE, DQELine, MaterialConsumptionRatio
from pricing.services import (
    compare_material_usage, material_request_variance_report, has_red_variance,
)
from materials.models import Material, MaterialRequest, MaterialRequestItem
from revenue.models import Devis
from chantiermobile.constants import (
    PriceItemType, WorkCategory, MaterialVarianceStatus, DQEStatus, DevisStatus,
    MaterialRequestStatus,
)


# --- Fixtures local to this module ---

@pytest.fixture
def sub_phase_factory(db, phase_factory):
    def create_sub_phase(site, parent, **kwargs):
        defaults = {'name': 'Sous-étape'}
        defaults.update(kwargs)
        return phase_factory(site, parent_phase=parent, **defaults)
    return create_sub_phase


@pytest.fixture
def ciment(db):
    return Material.objects.create(name='Ciment (sac 50kg)', unit='sac', estimated_cost_per_unit=Decimal('8.00'))


@pytest.fixture
def sable(db):
    return Material.objects.create(name='Sable', unit='m3', estimated_cost_per_unit=Decimal('15.00'))


@pytest.fixture
def work_item_beton(db, cabinet):
    return PriceLibraryItem.objects.create(
        cabinet=cabinet, code='OUV-BETON', designation='Béton dosé 350 - fondations',
        item_type=PriceItemType.WORK_ITEM, work_category=WorkCategory.BETON,
        unit='m3', unit_price=Decimal('120.00'),
    )


@pytest.fixture
def material_item_ciment(db, cabinet, ciment):
    return PriceLibraryItem.objects.create(
        cabinet=cabinet, code='MAT-CIMENT', designation='Ciment',
        item_type=PriceItemType.MATERIAL, material=ciment,
        unit='sac', unit_price=Decimal('8.00'),
    )


@pytest.fixture
def ciment_ratio(db, ciment):
    """Global-default ratio: 7 sacs de ciment per m3 of BETON."""
    return MaterialConsumptionRatio.objects.create(
        cabinet=None, work_category=WorkCategory.BETON, material=ciment,
        ratio=Decimal('7.0000'), ratio_unit='sacs/m3',
    )


@pytest.fixture
def dqe(db, cabinet, site):
    return DQE.objects.create(cabinet=cabinet, site=site, reference='DQE-TEST-001', title='Test DQE', status=DQEStatus.DRAFT)


# --- ProjectPhase hierarchy ---

@pytest.mark.django_db
class TestProjectPhaseHierarchy:
    def test_top_level_phase_has_no_parent(self, phase):
        assert phase.is_sub_phase is False
        assert phase.top_level_phase == phase

    def test_sub_phase_one_level(self, site, phase, sub_phase_factory):
        sub = sub_phase_factory(site, phase, name='Semelles bloc A')
        assert sub.is_sub_phase is True
        assert sub.top_level_phase == phase
        assert sub.parent_phase_id == phase.pk

    def test_cannot_nest_two_levels_deep(self, site, phase, sub_phase_factory):
        sub = sub_phase_factory(site, phase, name='Niveau 2')
        grandchild = ProjectPhase(site=site, name='Niveau 3', parent_phase=sub)
        with pytest.raises(ValidationError):
            grandchild.full_clean()

    def test_parent_must_be_same_site(self, site, site_factory, phase):
        other_site = site_factory(name='Autre chantier')
        child = ProjectPhase(site=other_site, name='Mauvais chantier', parent_phase=phase)
        with pytest.raises(ValidationError):
            child.full_clean()

    def test_phase_cannot_be_its_own_parent(self, phase):
        phase.parent_phase = phase
        with pytest.raises(ValidationError):
            phase.full_clean()

    def test_phase_with_children_cannot_itself_become_a_sub_phase(self, site, phase, sub_phase_factory, phase_factory):
        """A phase that already has sous-étapes can't become someone
        else's sous-étape — that would create a 2nd nesting level from
        the other direction (the parent's-parent check alone doesn't
        catch this, since it only looks at the *new* parent's parent,
        not at this phase's own children)."""
        sub_phase_factory(site, phase, name='Semelles bloc A')
        other_top_level = phase_factory(site, name='Autre étape principale')
        phase.parent_phase = other_top_level
        with pytest.raises(ValidationError):
            phase.full_clean()


# --- ProjectPhaseForm / phase create-edit views: sous-étape picker ---

@pytest.mark.django_db
class TestProjectPhaseFormParentPicker:
    def test_parent_phase_queryset_scoped_to_site_top_level_phases(self, site, site_factory, phase, phase_factory):
        from projects.forms import ProjectPhaseForm
        other_site = site_factory(name='Autre chantier')
        other_site_phase = phase_factory(other_site, name='Hors site')
        form = ProjectPhaseForm(site=site)
        qs = form.fields['parent_phase'].queryset
        assert phase in qs
        assert other_site_phase not in qs

    def test_parent_phase_queryset_excludes_self_on_edit(self, site, phase):
        from projects.forms import ProjectPhaseForm
        form = ProjectPhaseForm(instance=phase, site=site)
        assert phase not in form.fields['parent_phase'].queryset

    def test_parent_phase_queryset_empty_when_phase_already_has_children(self, site, phase, sub_phase_factory, phase_factory):
        from projects.forms import ProjectPhaseForm
        sub_phase_factory(site, phase, name='Déjà une sous-étape')
        phase_factory(site, name='Autre étape principale')
        form = ProjectPhaseForm(instance=phase, site=site)
        assert form.fields['parent_phase'].queryset.count() == 0

    def test_sub_phase_excluded_from_parent_choices(self, site, phase, sub_phase_factory):
        """A sous-étape itself never appears as a selectable parent —
        only top-level phases do."""
        from projects.forms import ProjectPhaseForm
        sub = sub_phase_factory(site, phase, name='Semelles bloc A')
        form = ProjectPhaseForm(site=site)
        assert sub not in form.fields['parent_phase'].queryset
        assert phase in form.fields['parent_phase'].queryset

    def test_create_view_creates_a_sub_phase(self, director_client, site, phase):
        from django.urls import reverse
        from projects.models import ProjectPhase
        url = reverse('projects:phase_create', kwargs={'site_id': site.unique_id})
        response = director_client.post(url, {
            'name': 'Semelles bloc A',
            'parent_phase': phase.pk,
            'start_date': date.today().isoformat(),
        })
        assert response.status_code == 302
        created = ProjectPhase.objects.get(name='Semelles bloc A')
        assert created.parent_phase_id == phase.pk
        assert created.is_sub_phase is True

    def test_update_view_rejects_making_a_parent_phase_a_sub_phase(self, director_client, site, phase, sub_phase_factory, phase_factory):
        """End-to-end: posting a phase-with-children's own update form
        with a parent_phase selected should fail validation rather than
        silently create a 2-level hierarchy. Since the queryset is
        already empty for such a phase (see the form test above), any
        posted value is simply not a valid choice."""
        from django.urls import reverse
        sub_phase_factory(site, phase, name='Déjà une sous-étape')
        other_top_level = phase_factory(site, name='Autre étape principale')
        url = reverse('projects:phase_update', kwargs={'unique_id': phase.unique_id})
        response = director_client.post(url, {
            'name': phase.name,
            'parent_phase': other_top_level.pk,
            'start_date': date.today().isoformat(),
        })
        assert response.status_code == 200  # re-rendered with form errors, not a redirect
        phase.refresh_from_db()
        assert phase.parent_phase_id is None


# --- PriceLibraryItem work_category / material ---

@pytest.mark.django_db
class TestPriceLibraryItemClassification:
    def test_work_item_requires_work_category(self, cabinet):
        item = PriceLibraryItem(
            cabinet=cabinet, code='X1', designation='Ouvrage sans catégorie',
            item_type=PriceItemType.WORK_ITEM, unit='m3', unit_price=Decimal('100'),
        )
        with pytest.raises(ValidationError):
            item.full_clean()

    def test_non_work_item_rejects_work_category(self, cabinet):
        item = PriceLibraryItem(
            cabinet=cabinet, code='X2', designation='Matériau avec catégorie en trop',
            item_type=PriceItemType.MATERIAL, work_category=WorkCategory.BETON,
            unit='kg', unit_price=Decimal('5'),
        )
        with pytest.raises(ValidationError):
            item.full_clean()

    def test_work_item_with_category_is_valid(self, work_item_beton):
        work_item_beton.full_clean()  # does not raise


# --- DQELine.phase + exploded_requirements() ---

@pytest.mark.django_db
class TestDQELineExplosion:
    def test_phase_must_match_dqe_site(self, dqe, work_item_beton, site_factory):
        other_site = site_factory(name='Autre chantier')
        other_phase = ProjectPhase.objects.create(site=other_site, name='Étape ailleurs')
        line = DQELine(dqe=dqe, price_item=work_item_beton, phase=other_phase, quantity=Decimal('10'), unit_price=Decimal('120'))
        with pytest.raises(ValidationError):
            line.full_clean()

    def test_work_item_explodes_through_ratio(self, dqe, phase, work_item_beton, ciment_ratio, ciment):
        line = DQELine.objects.create(
            dqe=dqe, price_item=work_item_beton, phase=phase,
            quantity=Decimal('10'), unit_price=Decimal('120'),
        )
        exploded = line.exploded_requirements()
        assert exploded[ciment.pk] == Decimal('70.0000')

    def test_material_item_contributes_direct_quantity(self, dqe, phase, material_item_ciment, ciment):
        line = DQELine.objects.create(
            dqe=dqe, price_item=material_item_ciment, phase=phase,
            quantity=Decimal('25'), unit_price=Decimal('8'),
        )
        exploded = line.exploded_requirements()
        assert exploded[ciment.pk] == Decimal('25')

    def test_cabinet_override_ratio_preferred_over_global_default(self, dqe, phase, work_item_beton, ciment_ratio, ciment, cabinet):
        MaterialConsumptionRatio.objects.create(
            cabinet=cabinet, work_category=WorkCategory.BETON, material=ciment,
            ratio=Decimal('8.5000'), ratio_unit='sacs/m3',
        )
        line = DQELine.objects.create(
            dqe=dqe, price_item=work_item_beton, phase=phase,
            quantity=Decimal('10'), unit_price=Decimal('120'),
        )
        exploded = line.exploded_requirements()
        assert exploded[ciment.pk] == Decimal('85.0000')

    def test_work_item_without_ratio_explodes_to_nothing(self, dqe, phase, cabinet):
        item = PriceLibraryItem.objects.create(
            cabinet=cabinet, code='OUV-NORATIO', designation='Ouvrage sans ratio',
            item_type=PriceItemType.WORK_ITEM, work_category=WorkCategory.AUTRE,
            unit='m3', unit_price=Decimal('50'),
        )
        line = DQELine.objects.create(dqe=dqe, price_item=item, phase=phase, quantity=Decimal('5'), unit_price=Decimal('50'))
        assert line.exploded_requirements() == {}


# --- MaterialConsumptionRatio basics ---

@pytest.mark.django_db
class TestMaterialConsumptionRatio:
    def test_ratio_must_be_positive(self, ciment):
        ratio = MaterialConsumptionRatio(
            cabinet=None, work_category=WorkCategory.BETON, material=ciment,
            ratio=Decimal('0'), ratio_unit='sacs/m3',
        )
        with pytest.raises(ValidationError):
            ratio.full_clean()

    def test_unique_per_cabinet_category_material(self, ciment, cabinet):
        # NULL (global-default, cabinet=None) rows are exempt from the
        # unique_together check — same "NULL != NULL" SQL semantics noted
        # on MaterialRequestItem.Meta — so this exercises the constraint
        # with a concrete cabinet instead, where it does bite.
        MaterialConsumptionRatio.objects.create(
            cabinet=cabinet, work_category=WorkCategory.BETON, material=ciment,
            ratio=Decimal('7.0000'), ratio_unit='sacs/m3',
        )
        dup = MaterialConsumptionRatio(
            cabinet=cabinet, work_category=WorkCategory.BETON, material=ciment,
            ratio=Decimal('5'), ratio_unit='sacs/m3',
        )
        with pytest.raises(ValidationError):
            dup.validate_unique()


# --- pricing.services comparison engine ---

@pytest.mark.django_db
class TestCompareMaterialUsage:
    def _accepted_devis_with_dqe(self, site, dqe):
        return Devis.objects.create(
            site=site, source_dqe=dqe, devis_number='DEV-CMP-001', client_name='Client Test',
            issue_date=date.today(), status=DevisStatus.ACCEPTE,
        )

    def test_not_budgeted_when_no_accepted_devis(self, site, phase, ciment):
        result = compare_material_usage(site, phase, ciment)
        assert result['baseline'] == Decimal('0')
        assert result['status'] == MaterialVarianceStatus.GREEN

    def test_green_under_orange_threshold(self, site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory):
        DQELine.objects.create(dqe=dqe, price_item=work_item_beton, phase=phase, quantity=Decimal('10'), unit_price=Decimal('120'))
        self._accepted_devis_with_dqe(site, dqe)
        # Baseline = 70 sacs. Request 50 sacs (~71%) -> GREEN (cabinet defaults 100/120).
        req = material_request_factory(status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=req, material=ciment, phase=phase, quantity=Decimal('50'))
        result = compare_material_usage(site, phase, ciment)
        assert result['status'] == MaterialVarianceStatus.GREEN

    def test_orange_between_thresholds(self, site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory):
        DQELine.objects.create(dqe=dqe, price_item=work_item_beton, phase=phase, quantity=Decimal('10'), unit_price=Decimal('120'))
        self._accepted_devis_with_dqe(site, dqe)
        # Baseline = 70. Request 77 (=110%) -> ORANGE.
        req = material_request_factory(status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=req, material=ciment, phase=phase, quantity=Decimal('77'))
        result = compare_material_usage(site, phase, ciment)
        assert result['status'] == MaterialVarianceStatus.ORANGE

    def test_red_above_red_threshold(self, site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory):
        DQELine.objects.create(dqe=dqe, price_item=work_item_beton, phase=phase, quantity=Decimal('10'), unit_price=Decimal('120'))
        self._accepted_devis_with_dqe(site, dqe)
        # Baseline = 70. Request 100 (~143%) -> RED.
        req = material_request_factory(status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=req, material=ciment, phase=phase, quantity=Decimal('100'))
        result = compare_material_usage(site, phase, ciment)
        assert result['status'] == MaterialVarianceStatus.RED

    def test_rejected_requests_excluded_from_cumulative(self, site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory):
        DQELine.objects.create(dqe=dqe, price_item=work_item_beton, phase=phase, quantity=Decimal('10'), unit_price=Decimal('120'))
        self._accepted_devis_with_dqe(site, dqe)
        req = material_request_factory(status=MaterialRequestStatus.REJECTED)
        MaterialRequestItem.objects.create(request=req, material=ciment, phase=phase, quantity=Decimal('1000'))
        result = compare_material_usage(site, phase, ciment)
        assert result['cumulative_requested'] == Decimal('0')
        assert result['status'] == MaterialVarianceStatus.GREEN

    def test_sub_phase_requests_roll_up_to_parent(self, site, phase, sub_phase_factory, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory):
        sub = sub_phase_factory(site, phase, name='Semelles bloc A')
        DQELine.objects.create(dqe=dqe, price_item=work_item_beton, phase=phase, quantity=Decimal('10'), unit_price=Decimal('120'))
        self._accepted_devis_with_dqe(site, dqe)
        req = material_request_factory(status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=req, material=ciment, phase=sub, quantity=Decimal('100'))
        # Comparing against the parent phase should include the sub-phase's request.
        result = compare_material_usage(site, phase, ciment)
        assert result['cumulative_requested'] == Decimal('100')
        assert result['status'] == MaterialVarianceStatus.RED


# --- MaterialRequestItem.phase validation ---

@pytest.mark.django_db
class TestMaterialRequestItemPhase:
    def test_phase_must_belong_to_request_site(self, material_request_factory, site_factory, ciment):
        other_site = site_factory(name='Autre chantier 2')
        other_phase = ProjectPhase.objects.create(site=other_site, name='Étape ailleurs')
        req = material_request_factory(status=MaterialRequestStatus.PENDING)
        item = MaterialRequestItem(request=req, material=ciment, phase=other_phase, quantity=Decimal('5'))
        with pytest.raises(ValidationError):
            item.full_clean()

    def test_phase_on_same_site_is_valid(self, material_request_factory, phase, ciment):
        req = material_request_factory(status=MaterialRequestStatus.PENDING)
        item = MaterialRequestItem(request=req, material=ciment, phase=phase, quantity=Decimal('5'))
        item.full_clean()  # does not raise


# --- MaterialRequest.authorize() soft-overage requirement ---

@pytest.mark.django_db
class TestAuthorizeOverageJustification:
    def _setup_red_request(self, site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory, django_user_model):
        DQELine.objects.create(dqe=dqe, price_item=work_item_beton, phase=phase, quantity=Decimal('10'), unit_price=Decimal('120'))
        Devis.objects.create(
            site=site, source_dqe=dqe, devis_number='DEV-OVER-001', client_name='Client',
            issue_date=date.today(), status=DevisStatus.ACCEPTE,
        )
        requester = django_user_model.objects.create_user(username='overage_requester', password='testpass123')
        req = material_request_factory(requested_by=requester, status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=req, material=ciment, phase=phase, quantity=Decimal('100'))
        return req

    def test_has_red_variance_true_when_over_red_threshold(self, site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory, django_user_model):
        req = self._setup_red_request(site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory, django_user_model)
        assert has_red_variance(req) is True

    def test_authorize_without_justification_raises(self, site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory, django_user_model):
        req = self._setup_red_request(site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory, django_user_model)
        director = django_user_model.objects.create_user(username='overage_director', password='testpass123')
        from accounts.models import UserCabinetRole
        from chantiermobile.constants import UserRoles, ApprovalStatus
        UserCabinetRole.objects.create(user=director, cabinet=req.site.cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
        with pytest.raises(ValidationError):
            req.authorize(director)

    def test_authorize_with_justification_succeeds(self, site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory, django_user_model):
        req = self._setup_red_request(site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory, django_user_model)
        director = django_user_model.objects.create_user(username='overage_director2', password='testpass123')
        from accounts.models import UserCabinetRole
        from chantiermobile.constants import UserRoles, ApprovalStatus
        UserCabinetRole.objects.create(user=director, cabinet=req.site.cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
        req.authorize(director, overage_justification='Dépassement validé avec le client, surcoût pris en charge.')
        req.refresh_from_db()
        assert req.status == MaterialRequestStatus.APPROVED
        assert 'Dépassement validé' in req.overage_justification

    def test_authorize_without_red_variance_needs_no_justification(self, material_request_factory, django_user_model, cabinet):
        req = material_request_factory(status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=req, material_name='Divers hors catalogue', quantity=Decimal('3'))
        director = django_user_model.objects.create_user(username='plain_director', password='testpass123')
        from accounts.models import UserCabinetRole
        from chantiermobile.constants import UserRoles, ApprovalStatus
        UserCabinetRole.objects.create(user=director, cabinet=cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
        req.authorize(director)  # does not raise
        req.refresh_from_db()
        assert req.status == MaterialRequestStatus.APPROVED
        assert req.overage_justification == ''


# --- Cabinet thresholds ---

@pytest.mark.django_db
class TestCabinetMaterialThresholds:
    def test_defaults(self, cabinet):
        assert cabinet.material_variance_orange_threshold_pct == Decimal('100.00')
        assert cabinet.material_variance_red_threshold_pct == Decimal('120.00')

    def test_orange_cannot_exceed_red(self, cabinet):
        cabinet.material_variance_orange_threshold_pct = Decimal('150')
        cabinet.material_variance_red_threshold_pct = Decimal('120')
        with pytest.raises(ValidationError):
            cabinet.full_clean()


# --- Devis.source_dqe ---

@pytest.mark.django_db
class TestDevisSourceDqe:
    def test_devis_can_link_to_dqe(self, site, dqe):
        devis = Devis.objects.create(
            site=site, source_dqe=dqe, devis_number='DEV-SRC-001', client_name='Client',
            issue_date=date.today(),
        )
        assert devis.source_dqe_id == dqe.pk

    def test_source_dqe_is_optional(self, site):
        devis = Devis.objects.create(
            site=site, devis_number='DEV-SRC-002', client_name='Client',
            issue_date=date.today(),
        )
        assert devis.source_dqe_id is None


# --- Views / JSON APIs ---

@pytest.mark.django_db
class TestMaterialUsageComparisonApi:
    def test_requires_login(self, client, site, phase, ciment):
        from django.urls import reverse
        url = reverse('pricing:material_usage_comparison')
        response = client.get(url, {'site': site.pk, 'phase': phase.pk, 'material': ciment.pk, 'quantity': '10'})
        assert response.status_code in (302, 403)

    def test_green_status_for_unbudgeted_with_no_request(self, director_client, site, phase, ciment):
        from django.urls import reverse
        url = reverse('pricing:material_usage_comparison')
        response = director_client.get(url, {'site': site.pk, 'phase': phase.pk, 'material': ciment.pk, 'quantity': '0'})
        assert response.status_code == 200
        data = response.json()
        assert data['ok'] is True
        assert data['status'] == 'GREEN'

    def test_missing_params_returns_not_ok(self, director_client, site):
        from django.urls import reverse
        url = reverse('pricing:material_usage_comparison')
        response = director_client.get(url, {'site': site.pk})
        assert response.status_code == 200
        assert response.json()['ok'] is False

    def test_reflects_red_variance(self, director_client, site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory):
        from django.urls import reverse
        DQELine.objects.create(dqe=dqe, price_item=work_item_beton, phase=phase, quantity=Decimal('10'), unit_price=Decimal('120'))
        Devis.objects.create(
            site=site, source_dqe=dqe, devis_number='DEV-API-001', client_name='Client',
            issue_date=date.today(), status=DevisStatus.ACCEPTE,
        )
        url = reverse('pricing:material_usage_comparison')
        # Baseline is 70 sacs; asking "what if I add 100" with nothing
        # requested yet should land RED (100/70 ≈ 143%).
        response = director_client.get(url, {'site': site.pk, 'phase': phase.pk, 'material': ciment.pk, 'quantity': '100'})
        data = response.json()
        assert data['ok'] is True
        assert data['status'] == 'RED'


@pytest.mark.django_db
class TestMaterialConsumptionRatioViews:
    def test_list_requires_director_tier(self, client, user, cabinet):
        from django.urls import reverse
        client.login(username='testuser', password='testpass123')
        response = client.get(reverse('pricing:ratio_list'))
        assert response.status_code == 302  # bounced — not director-tier

    def test_director_can_view_list(self, director_client):
        from django.urls import reverse
        response = director_client.get(reverse('pricing:ratio_list'))
        assert response.status_code == 200

    def test_director_can_create_cabinet_ratio(self, director_client, ciment):
        from django.urls import reverse
        response = director_client.post(reverse('pricing:ratio_create'), {
            'work_category': WorkCategory.MACONNERIE,
            'material': ciment.pk,
            'ratio': '0.5000',
            'ratio_unit': 'sacs/m2',
            'notes': '',
        })
        assert response.status_code == 302
        assert MaterialConsumptionRatio.objects.filter(work_category=WorkCategory.MACONNERIE, material=ciment, cabinet__isnull=False).exists()


@pytest.mark.django_db
class TestCabinetMaterialThresholdSettingsView:
    def test_director_can_view_and_update(self, director_client, cabinet):
        from django.urls import reverse
        url = reverse('pricing:material_thresholds')
        response = director_client.get(url)
        assert response.status_code == 200

        response = director_client.post(url, {
            'material_variance_orange_threshold_pct': '90',
            'material_variance_red_threshold_pct': '110',
        })
        assert response.status_code == 302
        cabinet.refresh_from_db()
        assert cabinet.material_variance_orange_threshold_pct == Decimal('90.00')
        assert cabinet.material_variance_red_threshold_pct == Decimal('110.00')

    def test_engineer_cannot_access(self, engineer_client):
        from django.urls import reverse
        response = engineer_client.get(reverse('pricing:material_thresholds'))
        assert response.status_code == 302


@pytest.mark.django_db
class TestDevisComplianceReportView:
    def test_renders_without_accepted_devis(self, director_client, site):
        from django.urls import reverse
        response = director_client.get(reverse('pricing:devis_compliance_report', kwargs={'pk': site.pk}))
        assert response.status_code == 200
        assert b'Aucune comparaison possible' in response.content or 'devis' in response.content.decode().lower()

    def test_renders_with_variance_rows(self, director_client, site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory):
        from django.urls import reverse
        DQELine.objects.create(dqe=dqe, price_item=work_item_beton, phase=phase, quantity=Decimal('10'), unit_price=Decimal('120'))
        Devis.objects.create(
            site=site, source_dqe=dqe, devis_number='DEV-REPORT-001', client_name='Client',
            issue_date=date.today(), status=DevisStatus.ACCEPTE,
        )
        req = material_request_factory(status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=req, material=ciment, phase=phase, quantity=Decimal('100'))
        response = director_client.get(reverse('pricing:devis_compliance_report', kwargs={'pk': site.pk}))
        assert response.status_code == 200
        assert ciment.name.encode() in response.content


@pytest.mark.django_db
class TestMaterialRequestDetailVarianceDisplay:
    def test_requires_overage_justification_flag_in_context(self, director_client, site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory):
        from django.urls import reverse
        DQELine.objects.create(dqe=dqe, price_item=work_item_beton, phase=phase, quantity=Decimal('10'), unit_price=Decimal('120'))
        Devis.objects.create(
            site=site, source_dqe=dqe, devis_number='DEV-DETAIL-001', client_name='Client',
            issue_date=date.today(), status=DevisStatus.ACCEPTE,
        )
        req = material_request_factory(status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=req, material=ciment, phase=phase, quantity=Decimal('100'))
        response = director_client.get(reverse('materials:request_detail', kwargs={'pk': req.pk}))
        assert response.status_code == 200
        assert response.context['requires_overage_justification'] is True
        assert b'overage_justification' in response.content

    def test_per_item_variance_badge_actually_renders(self, director_client, site, phase, dqe, work_item_beton, ciment_ratio, ciment, material_request_factory):
        """Regression test: MaterialRequestDetailView.get_context_data()
        annotates `row['item'].variance_comparison` on instances returned
        by `material_request_variance_report()`. If that function's
        queryset (`material_request.items.<...>.all()`) isn't the exact
        same cached queryset the view already prefetched
        ('items__material', 'items__phase'), chaining so much as a
        `.select_related()` on it silently returns *different* item
        instances — the annotation lands on throwaway objects, and the
        template's `req.items.all()` loop (reusing the prefetch cache)
        renders every row's "Conformité devis" cell as a bare '—', with
        no visible symptom beyond that one column. Asserting on the
        actual rendered badge (not just the context dict) is what catches
        this; asserting on `material_request_variance_report()`'s return
        value alone, or even on `requires_overage_justification` (computed
        straight from that return value, not from the annotated
        instances), would not."""
        from django.urls import reverse
        DQELine.objects.create(dqe=dqe, price_item=work_item_beton, phase=phase, quantity=Decimal('10'), unit_price=Decimal('120'))
        Devis.objects.create(
            site=site, source_dqe=dqe, devis_number='DEV-BADGE-001', client_name='Client',
            issue_date=date.today(), status=DevisStatus.ACCEPTE,
        )
        req = material_request_factory(status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=req, material=ciment, phase=phase, quantity=Decimal('100'))
        response = director_client.get(reverse('materials:request_detail', kwargs={'pk': req.pk}))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Dépassement' in content
        assert 'badge-subtle-danger' in content
