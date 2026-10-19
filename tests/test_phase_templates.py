"""Tests for PhaseTemplate — the cabinet-wide ("global" when
cabinet=None) étape/sous-étape catalog added 2026-10-19 while exploring
the app with the client's Appartements CCLK devis ("une liste d'étapes
possibles irrespective of a project/chantier"). Covers the model's
one-level-deep guard, instantiate_for_site()'s idempotency, and the two
new views (read-only catalogue list + the bulk-import action)."""
import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from projects.models import PhaseTemplate, ProjectPhase


@pytest.fixture
def major_template(db):
    return PhaseTemplate.objects.create(cabinet=None, name='Travaux de fondation', category='GROS_OEUVRE', order=0)


@pytest.fixture
def sub_template(db, major_template):
    return PhaseTemplate.objects.create(cabinet=None, parent_template=major_template, name='Semelle en BA', category='GROS_OEUVRE', order=0)


@pytest.mark.django_db
class TestPhaseTemplateModel:
    def test_global_default_has_no_cabinet(self, major_template):
        assert major_template.cabinet_id is None
        assert major_template.is_sub_template is False

    def test_sub_template_is_one_level_deep_only(self, major_template, sub_template):
        assert sub_template.is_sub_template is True
        grandchild = PhaseTemplate(cabinet=None, parent_template=sub_template, name='Trop profond', category='GROS_OEUVRE')
        with pytest.raises(ValidationError):
            grandchild.full_clean()

    def test_major_with_subs_cannot_become_a_sub_itself(self, major_template, sub_template):
        other = PhaseTemplate.objects.create(cabinet=None, name='Rez-de-chaussée', category='GROS_OEUVRE')
        major_template.parent_template = other
        with pytest.raises(ValidationError):
            major_template.full_clean()

    def test_catalog_for_cabinet_includes_global_defaults_and_own_rows(self, cabinet, major_template):
        own = PhaseTemplate.objects.create(cabinet=cabinet, name='Étape maison', category='FINISSAGE')
        other_cabinet_template = PhaseTemplate.objects.create(
            cabinet=None, name='Autre modèle global', category='FINISSAGE',
        )
        names = set(PhaseTemplate.catalog_for_cabinet(cabinet).values_list('name', flat=True))
        assert major_template.name in names  # global default
        assert own.name in names  # this cabinet's own
        assert other_cabinet_template.name in names  # also a global default


@pytest.mark.django_db
class TestInstantiateForSite:
    def test_instantiate_creates_phase_and_sub_phase(self, site, major_template, sub_template):
        phase = major_template.instantiate_for_site(site)
        assert phase.name == major_template.name
        assert phase.site_id == site.id
        assert phase.parent_phase_id is None
        sub_phase = site.phases.get(name=sub_template.name)
        assert sub_phase.parent_phase_id == phase.pk

    def test_instantiate_is_idempotent(self, site, major_template, sub_template):
        major_template.instantiate_for_site(site)
        major_template.instantiate_for_site(site)
        assert site.phases.filter(name=major_template.name).count() == 1
        assert site.phases.filter(name=sub_template.name).count() == 1

    def test_instantiating_a_lone_sub_template_creates_its_parent_phase_too(self, site, sub_template):
        sub_phase = sub_template.instantiate_for_site(site)
        assert sub_phase.parent_phase.name == sub_template.parent_template.name


@pytest.mark.django_db
class TestPhaseTemplateViews:
    def test_catalog_list_shows_global_templates(self, director_client, major_template, sub_template):
        response = director_client.get(reverse('projects:phase_template_list'))
        assert response.status_code == 200
        assert major_template in response.context['templates']
        assert major_template.name.encode() in response.content

    def test_import_action_creates_phases_and_is_idempotent(self, director_client, site, major_template, sub_template):
        url = reverse('projects:phase_template_import', kwargs={'unique_id': site.unique_id})
        response = director_client.post(url)
        assert response.status_code == 302
        assert ProjectPhase.objects.filter(site=site, name=major_template.name).count() == 1
        assert ProjectPhase.objects.filter(site=site, name=sub_template.name).count() == 1

        # Re-running the import doesn't duplicate the phases.
        director_client.post(url)
        assert ProjectPhase.objects.filter(site=site, name=major_template.name).count() == 1

    def test_import_action_requires_director_tier_role(self, client, user, site, major_template):
        client.force_login(user)
        url = reverse('projects:phase_template_import', kwargs={'unique_id': site.unique_id})
        response = client.post(url)
        assert response.status_code == 302
        assert not ProjectPhase.objects.filter(site=site, name=major_template.name).exists()
