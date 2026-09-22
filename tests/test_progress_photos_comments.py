"""
Tests for the Director's request: engineers should be able to attach
multiple photos to a site progress report (as evidence of the work
described), and anyone with access to the chantier should be able to
comment on a report or on one of its photos — not just the roles that can
file the report itself.

Covers: projects.models.ProgressPhoto / ProgressComment, the multi-file
upload on SiteProgressCreateView, projects.views.ProgressDetailView,
progress_photo_add and progress_comment_add.
"""
import io
import pytest
from datetime import date
from django.core.exceptions import ValidationError
from django.urls import reverse

from projects.models import SiteProgress, ProgressPhoto, ProgressComment

# `phase` fixture comes from tests/conftest.py (shared with the expense-form
# dynamic-fields tests, which also need a phase on a site).


def _image(name='photo.png'):
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), color='white').save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


@pytest.fixture
def progress(db, phase, user):
    return SiteProgress.objects.create(
        phase=phase, report_date=date.today(), percentage_complete=40,
        description='Coulage des fondations terminé.', created_by=user,
    )


@pytest.mark.django_db
class TestProgressPhotoModel:
    def test_str_and_ordering(self, progress, user):
        p1 = ProgressPhoto.objects.create(progress=progress, image=_image('a.png'), uploaded_by=user)
        p2 = ProgressPhoto.objects.create(progress=progress, image=_image('b.png'), uploaded_by=user)
        assert list(progress.photos.all()) == [p1, p2]
        assert str(p1).startswith('Photo')

    def test_site_delete_cascades_to_photos_and_comments(self, site, progress, user):
        photo = ProgressPhoto.objects.create(progress=progress, image=_image(), uploaded_by=user)
        ProgressComment.objects.create(progress=progress, photo=photo, author=user, body='RAS')
        site.delete()
        assert ProgressPhoto.objects.filter(pk=photo.pk).exists() is False
        assert ProgressComment.all_objects.get(progress=progress).is_deleted is True
        assert ProgressPhoto.all_objects.get(pk=photo.pk).is_deleted is True


@pytest.mark.django_db
class TestProgressCommentModel:
    def test_comment_on_report_has_no_photo(self, progress, user):
        comment = ProgressComment.objects.create(progress=progress, author=user, body='Bon avancement')
        assert comment.photo is None

    def test_clean_rejects_photo_from_a_different_report(self, progress, phase, user):
        other_progress = SiteProgress.objects.create(
            phase=phase, report_date=date.today(), percentage_complete=10, description='Autre rapport',
        )
        other_photo = ProgressPhoto.objects.create(progress=other_progress, image=_image(), uploaded_by=user)
        comment = ProgressComment(progress=progress, photo=other_photo, author=user, body='Mismatched')
        with pytest.raises(ValidationError):
            comment.clean()


@pytest.mark.django_db
class TestSiteProgressCreateWithPhotos:
    def test_create_report_with_multiple_photos(self, engineer_client, phase, engineer_user):
        url = reverse('projects:progress_create', kwargs={'phase_id': phase.unique_id})
        response = engineer_client.post(url, {
            'report_date': date.today().isoformat(),
            'percentage_complete': '55',
            'description': 'Ferraillage posé, coffrage en cours.',
            'photos': [_image('site1.png'), _image('site2.png')],
        })
        report = SiteProgress.objects.get(phase=phase)
        assert response.status_code == 302
        assert report.created_by == engineer_user
        assert report.photos.count() == 2
        assert all(p.uploaded_by == engineer_user for p in report.photos.all())

    def test_create_report_without_photos_still_works(self, engineer_client, phase):
        url = reverse('projects:progress_create', kwargs={'phase_id': phase.unique_id})
        response = engineer_client.post(url, {
            'report_date': date.today().isoformat(),
            'percentage_complete': '20',
            'description': 'Terrassement en cours.',
        })
        assert response.status_code == 302
        report = SiteProgress.objects.get(phase=phase)
        assert report.photos.count() == 0

    def test_create_redirects_to_progress_detail(self, engineer_client, phase):
        url = reverse('projects:progress_create', kwargs={'phase_id': phase.unique_id})
        response = engineer_client.post(url, {
            'report_date': date.today().isoformat(),
            'percentage_complete': '20',
            'description': 'Terrassement en cours.',
        })
        report = SiteProgress.objects.get(phase=phase)
        assert response.url == reverse('projects:progress_detail', kwargs={'unique_id': report.unique_id})


@pytest.mark.django_db
class TestProgressDetailView:
    def test_visible_to_any_role_with_cabinet_access(self, accountant_client, accountant_user, cabinet, progress):
        # Accountant isn't one of the roles that can file/photo a progress
        # report, but should still be able to *view* it — this is meant to
        # be readable/discussable by the whole cabinet, not engineer-only.
        url = reverse('projects:progress_detail', kwargs={'unique_id': progress.unique_id})
        response = accountant_client.get(url)
        assert response.status_code == 200
        assert response.context['can_add_photo'] is False
        assert response.context['can_comment'] is True

    def test_engineer_can_add_photo_flag_true(self, engineer_client, progress):
        url = reverse('projects:progress_detail', kwargs={'unique_id': progress.unique_id})
        response = engineer_client.get(url)
        assert response.context['can_add_photo'] is True

    def test_not_visible_to_user_outside_the_cabinet(self, client, django_user_model, progress):
        outsider = django_user_model.objects.create_user(username='outsider', password='testpass123')
        client.login(username='outsider', password='testpass123')
        url = reverse('projects:progress_detail', kwargs={'unique_id': progress.unique_id})
        response = client.get(url)
        assert response.status_code == 404


@pytest.mark.django_db
class TestProgressPhotoAdd:
    def test_engineer_can_add_follow_up_photo(self, engineer_client, engineer_user, progress):
        url = reverse('projects:progress_photo_add', kwargs={'unique_id': progress.unique_id})
        response = engineer_client.post(url, {'photos': [_image('followup.png')]})
        assert response.status_code == 302
        assert progress.photos.count() == 1
        assert progress.photos.first().uploaded_by == engineer_user

    def test_accountant_cannot_add_photo(self, accountant_client, progress):
        url = reverse('projects:progress_photo_add', kwargs={'unique_id': progress.unique_id})
        response = accountant_client.post(url, {'photos': [_image()]})
        assert response.status_code == 302
        assert progress.photos.count() == 0

    def test_get_does_not_create_photo(self, engineer_client, progress):
        url = reverse('projects:progress_photo_add', kwargs={'unique_id': progress.unique_id})
        engineer_client.get(url)
        assert progress.photos.count() == 0

    def test_empty_submission_shows_error_and_creates_nothing(self, engineer_client, progress):
        url = reverse('projects:progress_photo_add', kwargs={'unique_id': progress.unique_id})
        response = engineer_client.post(url, {})
        assert response.status_code == 302
        assert progress.photos.count() == 0


@pytest.mark.django_db
class TestProgressCommentAdd:
    def test_any_cabinet_role_can_comment(self, accountant_client, accountant_user, progress):
        """The key relaxation vs. photo uploads: commenting is open to
        anyone with cabinet access, not just DIRECTOR/CHIEF_ENGINEER/ENGINEER."""
        url = reverse('projects:progress_comment_add', kwargs={'unique_id': progress.unique_id})
        response = accountant_client.post(url, {'body': 'Ça avance bien.'})
        assert response.status_code == 302
        comment = ProgressComment.objects.get(progress=progress)
        assert comment.author == accountant_user
        assert comment.body == 'Ça avance bien.'
        assert comment.photo is None

    def test_comment_can_target_a_specific_photo(self, director_client, user, progress):
        photo = ProgressPhoto.objects.create(progress=progress, image=_image(), uploaded_by=user)
        url = reverse('projects:progress_comment_add', kwargs={'unique_id': progress.unique_id})
        response = director_client.post(url, {'body': "C'est quoi cette fissure ?", 'photo': str(photo.unique_id)})
        assert response.status_code == 302
        comment = ProgressComment.objects.get(progress=progress)
        assert comment.photo == photo

    def test_empty_comment_rejected(self, director_client, progress):
        url = reverse('projects:progress_comment_add', kwargs={'unique_id': progress.unique_id})
        response = director_client.post(url, {'body': '   '})
        assert response.status_code == 302
        assert ProgressComment.objects.filter(progress=progress).count() == 0

    def test_user_outside_cabinet_cannot_comment(self, client, django_user_model, progress):
        outsider = django_user_model.objects.create_user(username='outsider2', password='testpass123')
        client.login(username='outsider2', password='testpass123')
        url = reverse('projects:progress_comment_add', kwargs={'unique_id': progress.unique_id})
        response = client.post(url, {'body': 'Should not work'})
        assert response.status_code == 302
        assert ProgressComment.objects.filter(progress=progress).count() == 0
