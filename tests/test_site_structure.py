"""Tests for the Site floors/structure feature (added 2026-10-08): a
Site now carries floor_count/basement_count/footprint_area_m2/
structure_type, Site.sync_levels() keeps one SiteLevel row per actual
floor (RDC, R+N, sous-sols) in sync with those counts, and each level's
structural detail (height, murs, poutres, colonnes, dalle) rolls up into
a site-wide concrete/maçonnerie/acier estimate used to pre-fill DQE line
quantities (see pricing.services.structural_quantity_estimate).
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.core.exceptions import ValidationError

from accounts.models import UserCabinetRole
from chantiermobile.constants import UserRoles, ApprovalStatus, StructureType
from projects.models import Site, SiteLevel


@pytest.mark.django_db
class TestSyncLevels:
    def test_default_site_has_only_rdc(self, site):
        site.sync_levels()
        assert list(site.levels.values_list('level_index', flat=True)) == [0]
        assert site.levels.get(level_index=0).label == 'Rez-de-chaussée (RDC)'

    def test_floor_count_creates_one_level_per_floor_plus_rdc(self, site):
        site.floor_count = 3
        site.save(update_fields=['floor_count'])
        site.sync_levels()
        indexes = list(site.levels.order_by('level_index').values_list('level_index', flat=True))
        assert indexes == [0, 1, 2, 3]

    def test_basement_count_creates_negative_indexes(self, site):
        site.floor_count = 1
        site.basement_count = 2
        site.save(update_fields=['floor_count', 'basement_count'])
        site.sync_levels()
        indexes = list(site.levels.order_by('level_index').values_list('level_index', flat=True))
        assert indexes == [-2, -1, 0, 1]
        assert site.levels.get(level_index=-1).label == 'Sous-sol 1'
        assert site.levels.get(level_index=1).label == 'R+1'

    def test_lowering_floor_count_soft_deletes_excess_levels(self, site):
        site.floor_count = 3
        site.save(update_fields=['floor_count'])
        site.sync_levels()
        r3 = site.levels.get(level_index=3)
        r3.height_m = Decimal('2.80')
        r3.save(update_fields=['height_m'])

        site.floor_count = 1
        site.save(update_fields=['floor_count'])
        site.sync_levels()

        assert list(site.levels.order_by('level_index').values_list('level_index', flat=True)) == [0, 1]
        assert not SiteLevel.objects.filter(pk=r3.pk).exists()
        assert SiteLevel.all_objects.get(pk=r3.pk).is_deleted is True

    def test_raising_floor_count_back_restores_dormant_level_with_its_data(self, site):
        """A level soft-deleted by a lowered floor_count comes back with
        whatever data it held, rather than a fresh blank row, when the
        count is raised again to include it."""
        site.floor_count = 2
        site.save(update_fields=['floor_count'])
        site.sync_levels()
        r2 = site.levels.get(level_index=2)
        r2.height_m = Decimal('3.10')
        r2.notes = 'Retrait de façade'
        r2.save(update_fields=['height_m', 'notes'])

        site.floor_count = 1
        site.save(update_fields=['floor_count'])
        site.sync_levels()
        assert not site.levels.filter(level_index=2).exists()

        site.floor_count = 2
        site.save(update_fields=['floor_count'])
        site.sync_levels()
        restored = site.levels.get(level_index=2)
        assert restored.pk == r2.pk
        assert restored.height_m == Decimal('3.10')
        assert restored.notes == 'Retrait de façade'

    def test_sync_levels_called_twice_is_idempotent(self, site):
        site.floor_count = 2
        site.save(update_fields=['floor_count'])
        site.sync_levels()
        site.sync_levels()
        assert site.levels.count() == 3


@pytest.mark.django_db
class TestSiteLevelComputedProperties:
    def test_label_rdc_etage_sous_sol(self, site):
        rdc = SiteLevel.objects.create(site=site, level_index=0)
        r2 = SiteLevel.objects.create(site=site, level_index=2)
        sous_sol = SiteLevel.objects.create(site=site, level_index=-1)
        assert rdc.label == 'Rez-de-chaussée (RDC)'
        assert r2.label == 'R+2'
        assert sous_sol.label == 'Sous-sol 1'

    def test_effective_floor_area_falls_back_to_site_footprint(self, site):
        site.footprint_area_m2 = Decimal('120.00')
        site.save(update_fields=['footprint_area_m2'])
        level = SiteLevel.objects.create(site=site, level_index=0)
        assert level.effective_floor_area_m2 == Decimal('120.00')

        level.floor_area_m2 = Decimal('95.00')
        level.save(update_fields=['floor_area_m2'])
        assert level.effective_floor_area_m2 == Decimal('95.00')

    def test_wall_area_nets_out_openings_and_floors_at_zero(self, site):
        level = SiteLevel.objects.create(
            site=site, level_index=0, height_m=Decimal('3.00'),
            wall_length_m=Decimal('40.00'), opening_area_m2=Decimal('10.00'),
        )
        # 40 * 3 - 10 = 110
        assert level.wall_area_m2 == Decimal('110.00')

        level.opening_area_m2 = Decimal('999.00')
        level.save(update_fields=['opening_area_m2'])
        assert level.wall_area_m2 == Decimal('0')

    def test_wall_area_is_none_when_inputs_missing(self, site):
        level = SiteLevel.objects.create(site=site, level_index=0)
        assert level.wall_area_m2 is None

    def test_concrete_volume_sums_beams_columns_and_slab(self, site):
        level = SiteLevel.objects.create(
            site=site, level_index=0, height_m=Decimal('3.00'),
            floor_area_m2=Decimal('100.00'), slab_thickness_m=Decimal('0.15'),
            beam_total_length_m=Decimal('50.00'), beam_section_width_m=Decimal('0.20'), beam_section_height_m=Decimal('0.40'),
            column_count=10, column_section_width_m=Decimal('0.20'), column_section_depth_m=Decimal('0.20'),
        )
        # slab: 100 * 0.15 = 15
        # beams: 50 * 0.20 * 0.40 = 4
        # columns: 10 * 3.00 * 0.20 * 0.20 = 1.2
        assert level.slab_volume_m3 == Decimal('15.00')
        assert level.beam_volume_m3 == Decimal('4.0000')
        assert level.column_volume_m3 == Decimal('1.200')
        assert level.concrete_volume_m3 == Decimal('20.2000')

    def test_concrete_volume_zero_when_dimensions_missing(self, site):
        level = SiteLevel.objects.create(site=site, level_index=0)
        assert level.concrete_volume_m3 == Decimal('0')


@pytest.mark.django_db
class TestSiteAggregateEstimates:
    def test_totals_sum_across_levels(self, site):
        SiteLevel.objects.create(
            site=site, level_index=0, height_m=Decimal('3.00'), floor_area_m2=Decimal('50.00'),
            slab_thickness_m=Decimal('0.15'), wall_length_m=Decimal('20.00'), opening_area_m2=Decimal('0'),
        )
        SiteLevel.objects.create(
            site=site, level_index=1, height_m=Decimal('3.00'), floor_area_m2=Decimal('50.00'),
            slab_thickness_m=Decimal('0.15'), wall_length_m=Decimal('20.00'), opening_area_m2=Decimal('0'),
        )
        # Each level: slab = 50*0.15 = 7.5 m3 concrete; wall = 20*3 = 60 m2
        assert site.total_concrete_volume_m3 == Decimal('15.0000') or site.total_concrete_volume_m3 == Decimal('15.00')
        assert site.total_wall_area_m2 == Decimal('120.00')

    def test_estimated_rebar_uses_cabinet_density(self, site):
        SiteLevel.objects.create(
            site=site, level_index=0, floor_area_m2=Decimal('10.00'), slab_thickness_m=Decimal('1.00'),
        )
        # concrete volume = 10 m3
        site.cabinet.rebar_density_kg_per_m3 = Decimal('120.00')
        site.cabinet.save(update_fields=['rebar_density_kg_per_m3'])
        assert site.estimated_rebar_kg == Decimal('1200.0000') or site.estimated_rebar_kg == Decimal('1200.00')

    def test_no_levels_gives_zero_totals_not_an_error(self, site):
        assert site.total_concrete_volume_m3 == 0
        assert site.total_wall_area_m2 == 0
        assert site.estimated_rebar_kg == 0


@pytest.mark.django_db
class TestStructuralQuantityEstimateService:
    def test_matches_site_properties(self, site):
        from pricing.services import structural_quantity_estimate
        SiteLevel.objects.create(
            site=site, level_index=0, floor_area_m2=Decimal('20.00'), slab_thickness_m=Decimal('0.20'),
        )
        estimate = structural_quantity_estimate(site)
        assert estimate['concrete_m3'] == site.total_concrete_volume_m3
        assert estimate['wall_area_m2'] == site.total_wall_area_m2
        assert estimate['rebar_kg'] == site.estimated_rebar_kg


@pytest.mark.django_db
class TestSiteFormIntegration:
    def test_creating_site_with_floor_count_creates_levels(self, director_client, cabinet):
        response = director_client.post(reverse('projects:site_create'), {
            'name': 'Tour Test', 'location': 'Kinshasa', 'status': 'PLANNING',
            'contract_mode': 'CLE_EN_MAIN', 'floor_count': '2', 'basement_count': '0',
            'footprint_area_m2': '80.00', 'structure_type': StructureType.POTEAUX_POUTRES,
        }, follow=True)
        assert response.status_code == 200
        created = Site.objects.get(name='Tour Test')
        assert list(created.levels.order_by('level_index').values_list('level_index', flat=True)) == [0, 1, 2]

    def test_updating_floor_count_resyncs_levels(self, director_client, site):
        url = reverse('projects:site_update', kwargs={'unique_id': site.unique_id})
        response = director_client.post(url, {
            'name': site.name, 'location': site.location, 'status': site.status,
            'contract_mode': site.contract_mode, 'floor_count': '2', 'basement_count': '0',
        }, follow=True)
        assert response.status_code == 200
        site.refresh_from_db()
        assert list(site.levels.order_by('level_index').values_list('level_index', flat=True)) == [0, 1, 2]


@pytest.mark.django_db
class TestSiteStructureUpdateView:
    def test_director_can_view_and_submit(self, director_client, site):
        site.floor_count = 1
        site.save(update_fields=['floor_count'])
        site.sync_levels()
        url = reverse('projects:site_structure_update', kwargs={'unique_id': site.unique_id})
        get_response = director_client.get(url)
        assert get_response.status_code == 200
        assert len(get_response.context['levels_formset'].forms) == 2

        management = get_response.context['levels_formset'].management_form
        data = {
            'levels-TOTAL_FORMS': management['TOTAL_FORMS'].value(),
            'levels-INITIAL_FORMS': management['INITIAL_FORMS'].value(),
            'levels-MIN_NUM_FORMS': management['MIN_NUM_FORMS'].value(),
            'levels-MAX_NUM_FORMS': management['MAX_NUM_FORMS'].value(),
        }
        for i, level in enumerate(site.levels.order_by('level_index')):
            data[f'levels-{i}-id'] = level.pk
            data[f'levels-{i}-height_m'] = '3.00'
            data[f'levels-{i}-wall_length_m'] = '30.00'
            data[f'levels-{i}-opening_area_m2'] = '5.00'
        post_response = director_client.post(url, data)
        assert post_response.status_code == 302
        for level in site.levels.all():
            level.refresh_from_db()
            assert level.height_m == Decimal('3.00')

    def test_submitting_with_blank_opening_area_does_not_crash(self, director_client, site):
        """Regression test: opening_area_m2 is blank=True on the form (the
        field reads as optional — no `required` attribute on the widget),
        so a submission that leaves it empty must not hit the database's
        NOT NULL constraint (the field used to be null=False)."""
        site.floor_count = 1
        site.save(update_fields=['floor_count'])
        site.sync_levels()
        url = reverse('projects:site_structure_update', kwargs={'unique_id': site.unique_id})
        management = director_client.get(url).context['levels_formset'].management_form
        data = {
            'levels-TOTAL_FORMS': management['TOTAL_FORMS'].value(),
            'levels-INITIAL_FORMS': management['INITIAL_FORMS'].value(),
            'levels-MIN_NUM_FORMS': management['MIN_NUM_FORMS'].value(),
            'levels-MAX_NUM_FORMS': management['MAX_NUM_FORMS'].value(),
        }
        for i, level in enumerate(site.levels.order_by('level_index')):
            data[f'levels-{i}-id'] = level.pk
            data[f'levels-{i}-height_m'] = '3.00'
            data[f'levels-{i}-wall_length_m'] = '30.00'
            data[f'levels-{i}-opening_area_m2'] = ''
        post_response = director_client.post(url, data)
        assert post_response.status_code == 302

    def test_lead_engineer_of_own_site_can_access(self, engineer_client, engineer_user, site):
        site.lead_engineer = engineer_user
        site.save(update_fields=['lead_engineer'])
        site.sync_levels()
        url = reverse('projects:site_structure_update', kwargs={'unique_id': site.unique_id})
        response = engineer_client.get(url)
        assert response.status_code == 200

    def test_unrelated_engineer_is_bounced(self, client, cabinet, site, django_user_model):
        other = django_user_model.objects.create_user(username='other_eng_structure', password='testpass123')
        UserCabinetRole.objects.create(user=other, cabinet=cabinet, role=UserRoles.ENGINEER, status=ApprovalStatus.APPROVED)
        client.login(username='other_eng_structure', password='testpass123')
        site.sync_levels()
        url = reverse('projects:site_structure_update', kwargs={'unique_id': site.unique_id})
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse('projects:site_detail', kwargs={'unique_id': site.unique_id})


@pytest.mark.django_db
class TestSiteStructuralEstimateApi:
    def test_returns_site_estimate(self, director_client, site):
        SiteLevel.objects.create(site=site, level_index=0, floor_area_m2=Decimal('40.00'), slab_thickness_m=Decimal('0.20'))
        url = reverse('pricing:site_structural_estimate') + f'?site={site.pk}'
        response = director_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data['concrete_m3'] == pytest.approx(8.0)

    def test_scoped_to_own_cabinet(self, director_client, site_factory):
        from accounts.models import Cabinet
        other_cabinet = Cabinet.objects.create(name='Autre Cabinet Structure')
        other_site = site_factory(cabinet=other_cabinet)
        SiteLevel.objects.create(site=other_site, level_index=0, floor_area_m2=Decimal('40.00'), slab_thickness_m=Decimal('0.20'))
        url = reverse('pricing:site_structural_estimate') + f'?site={other_site.pk}'
        response = director_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data['concrete_m3'] == 0
