"""Personnel profile links from a chantier's "Personnel" tab (2026-10-27).

Bug: on some chantiers (Marguerite…) clicking a crew member gave a 404.
Two causes, both reproduced here:

1. Cross-cabinet assignment: the person's record belongs to another cabinet
   than the chantier (a superadmin browsing "Tous les cabinets" could pick
   any personnel for any chantier, and a name quick-added there was filed
   under the oldest cabinet). The profile page only looked in the viewer's
   cabinet(s), so anyone working in the chantier's cabinet got a 404.
2. Soft-deleted personnel: deleting a person kept their assignments, so the
   crew list still linked to a profile that no longer exists.
"""
import json
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import Cabinet, UserCabinetRole
from chantiermobile.constants import ApprovalStatus, SiteStatus, UserRoles
from personnel.models import Personnel, SiteAssignment


@pytest.fixture
def other_cabinet(db):
    return Cabinet.objects.create(name='Autre cabinet', address='x', tax_id='OTHER-1')


@pytest.fixture
def marguerite(site_factory):
    return site_factory(name='Marguerite (test)', status=SiteStatus.ACTIVE)


def _assign(person, site):
    return SiteAssignment.objects.create(personnel=person, site=site, role='Maçon', start_date=date.today(), daily_rate=10)


def _detail(person):
    return reverse('personnel:personnel_detail', kwargs={'unique_id': person.unique_id})


def _site(site):
    return reverse('projects:site_detail', kwargs={'unique_id': site.unique_id})


@pytest.mark.django_db
class TestCrossCabinetCrew:
    def test_profile_opens_from_the_chantiers_cabinet(self, director_client, marguerite, other_cabinet):
        stray = Personnel.objects.create(cabinet=other_cabinet, first_name='Jean', last_name='Ailleurs', default_daily_rate=10)
        _assign(stray, marguerite)
        assert _detail(stray) in director_client.get(_site(marguerite)).content.decode()
        assert director_client.get(_detail(stray)).status_code == 200

    def test_unrelated_person_of_another_cabinet_stays_hidden(self, director_client, other_cabinet, site_factory):
        foreign_site = site_factory(name='Chez les autres', cabinet=other_cabinet)
        outsider = Personnel.objects.create(cabinet=other_cabinet, first_name='Paul', last_name='Dehors', default_daily_rate=10)
        _assign(outsider, foreign_site)
        assert director_client.get(_detail(outsider)).status_code == 404

    def test_superadmin_switched_into_the_chantiers_cabinet(self, admin_client, cabinet, marguerite, other_cabinet):
        stray = Personnel.objects.create(cabinet=other_cabinet, first_name='Jean', last_name='Ailleurs', default_daily_rate=10)
        _assign(stray, marguerite)
        session = admin_client.session
        session['active_cabinet_id'] = cabinet.pk
        session.save()
        assert admin_client.get(_detail(stray)).status_code == 200

    def test_superadmin_sees_everyone(self, admin_client, other_cabinet):
        outsider = Personnel.objects.create(cabinet=other_cabinet, first_name='Paul', last_name='Dehors', default_daily_rate=10)
        assert admin_client.get(_detail(outsider)).status_code == 200


@pytest.mark.django_db
class TestDeletedPersonnel:
    def test_deleted_person_is_not_linked(self, director_client, cabinet, marguerite):
        gone = Personnel.objects.create(cabinet=cabinet, first_name='Ancien', last_name='Ouvrier', default_daily_rate=10)
        _assign(gone, marguerite)
        gone.delete()
        content = director_client.get(_site(marguerite)).content.decode()
        assert _detail(gone) not in content
        assert 'Ancien Ouvrier' in content and 'Retiré du personnel' in content


@pytest.mark.django_db
class TestNoNewMismatches:
    def test_assignment_form_rejects_another_cabinets_person(self, admin_client, marguerite, other_cabinet):
        stray = Personnel.objects.create(cabinet=other_cabinet, first_name='Jean', last_name='Ailleurs', default_daily_rate=10)
        response = admin_client.post(reverse('personnel:assignment_create'), {
            'personnel': stray.pk, 'site': marguerite.pk, 'role': 'Maçon',
            'start_date': date.today().isoformat(), 'daily_rate': '10',
        })
        assert response.status_code == 200
        assert not SiteAssignment.objects.filter(personnel=stray, site=marguerite).exists()
        assert 'cabinet' in response.content.decode()

    def test_quick_add_with_a_chantier_files_the_person_there(self, admin_client, marguerite, other_cabinet):
        # The superadmin has not switched cabinet; the oldest cabinet would be
        # picked without the chantier (other_cabinet is created later here,
        # so make it the older one to prove the chantier wins).
        Cabinet.objects.filter(pk=other_cabinet.pk).update(created_at=marguerite.cabinet.created_at.replace(year=2000))
        body = admin_client.post(reverse('personnel:personnel_quick_create'),
                                 data=json.dumps({'name': 'Neuf Venu', 'site': marguerite.pk}),
                                 content_type='application/json').json()
        assert Personnel.objects.get(pk=body['id']).cabinet_id == marguerite.cabinet_id

    def test_quick_add_cannot_target_a_foreign_chantier(self, client, cabinet, other_cabinet, site_factory):
        foreign_site = site_factory(name='Chez les autres', cabinet=other_cabinet)
        director = get_user_model().objects.create_user(username='dir_qc', password='pw-12345')
        UserCabinetRole.objects.create(user=director, cabinet=cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
        client.force_login(director)
        body = client.post(reverse('personnel:personnel_quick_create'),
                           data=json.dumps({'name': 'Neuf Venu', 'site': foreign_site.pk}),
                           content_type='application/json').json()
        person = Personnel.objects.get(pk=body['id'])
        assert person.cabinet_id == cabinet.pk
        assert not SiteAssignment.objects.filter(personnel=person).exists()


@pytest.mark.django_db
class TestCheckCrewLinksCommand:
    def test_report_and_fix(self, cabinet, marguerite, other_cabinet):
        from io import StringIO
        from django.core.management import call_command
        stray = Personnel.objects.create(cabinet=other_cabinet, first_name='Jean', last_name='Ailleurs', default_daily_rate=10)
        _assign(stray, marguerite)
        gone = Personnel.objects.create(cabinet=cabinet, first_name='Ancien', last_name='Ouvrier', default_daily_rate=10)
        orphan = _assign(gone, marguerite)
        gone.delete()

        out = StringIO()
        call_command('check_crew_links', stdout=out)
        assert 'Jean Ailleurs' in out.getvalue() and 'Ancien Ouvrier' in out.getvalue()
        stray.refresh_from_db()
        assert stray.cabinet_id == other_cabinet.pk  # report only

        call_command('check_crew_links', '--fix', stdout=StringIO())
        stray.refresh_from_db()
        assert stray.cabinet_id == cabinet.pk
        assert not SiteAssignment.objects.filter(pk=orphan.pk).exists()
        assert SiteAssignment.all_objects.filter(pk=orphan.pk, is_deleted=True).exists()

    def test_multi_cabinet_person_left_alone(self, cabinet, marguerite, other_cabinet, site_factory):
        from io import StringIO
        from django.core.management import call_command
        busy = Personnel.objects.create(cabinet=other_cabinet, first_name='Deux', last_name='Cabinets', default_daily_rate=10)
        _assign(busy, marguerite)
        _assign(busy, site_factory(name='Chez les autres', cabinet=other_cabinet))
        out = StringIO()
        call_command('check_crew_links', '--fix', stdout=out)
        busy.refresh_from_db()
        assert busy.cabinet_id == other_cabinet.pk and 'à la main' in out.getvalue()
