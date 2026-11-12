"""Public presentation page (2026-11-12).

- "/" shows the presentation page to visitors who are not signed in and
  the dashboard to everyone else; /presentation/ always shows it.
- It links to every way in: sign in, create an account, forgot password.
- Every image / clip it references is shipped in static/.
- It is translated (English via the language switch).
"""
import re

import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse
from django.utils import translation


@pytest.mark.django_db
class TestRouting:
    def test_anonymous_root_shows_the_landing_page(self, client):
        response = client.get(reverse('home'))
        assert response.status_code == 200
        assert 'landing.html' in [t.name for t in response.templates]

    def test_signed_in_root_still_shows_the_dashboard(self, director_client):
        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        names = [t.name for t in response.templates]
        assert 'home.html' in names and 'landing.html' not in names

    def test_presentation_url_for_signed_in_user(self, director_client):
        content = director_client.get(reverse('landing')).content.decode()
        assert 'Ouvrir mon tableau de bord' in content
        assert f'href="{reverse("home")}"' in content

    def test_superadmin_can_open_both(self, admin_client):
        assert admin_client.get(reverse('landing')).status_code == 200
        assert 'home.html' in [t.name for t in admin_client.get(reverse('home')).templates]


@pytest.mark.django_db
class TestLinks:
    def test_every_account_entry_point_is_linked(self, client):
        content = client.get(reverse('home')).content.decode()
        for name in ('account_login', 'account_signup', 'account_reset_password'):
            assert f'href="{reverse(name)}"' in content, name
        # Primary calls to action appear in the header, hero and closing band.
        assert content.count(f'href="{reverse("account_signup")}"') >= 4
        assert content.count(f'href="{reverse("account_login")}"') >= 4

    def test_in_page_anchors_exist(self, client):
        content = client.get(reverse('home')).content.decode()
        ids = set(re.findall(r'id="([^"]+)"', content))
        for anchor in set(re.findall(r'href="#([^"]+)"', content)):
            assert anchor in ids, anchor

    def test_referenced_static_files_exist(self, client):
        content = client.get(reverse('home')).content.decode()
        paths = set(re.findall(r'/static/((?:landing|assets)/[^"\')\s]+)', content))
        assert any(p.endswith('.mp4') for p in paths) and any(p.endswith('.webp') for p in paths)
        for path in paths:
            assert finders.find(path), path

    def test_images_have_alt_text(self, client):
        content = client.get(reverse('home')).content.decode()
        for tag in re.findall(r'<img [^>]+>', content):
            assert 'alt="' in tag, tag


@pytest.mark.django_db
def test_english_version(client):
    with translation.override('en'):
        response = client.get(reverse('home'), HTTP_ACCEPT_LANGUAGE='en')
    content = response.content.decode()
    if 'Create an account' not in content:
        client.cookies['django_language'] = 'en'
        content = client.get(reverse('home')).content.decode()
    assert 'Create an account' in content and 'Sign in' in content
    assert 'What you can do' in content


@pytest.mark.django_db
def test_dashboard_tracking_rows_toggle_in_js(director_client, site_factory):
    """Regression: rows used data-bs-toggle="collapse", which the Falcon
    theme makes unclickable (pointer-events:none on its children)."""
    from chantiermobile.constants import PhaseStatus, SiteStatus
    from projects.models import ProjectPhase
    site = site_factory(name='Ligne cliquable', status=SiteStatus.ACTIVE)
    ProjectPhase.objects.create(site=site, name='Fondations', status=PhaseStatus.EN_COURS)
    content = director_client.get(reverse('home')).content.decode()
    row = re.search(r'<tr class="cm-track-row"[^>]*>', content).group(0)
    assert 'data-cm-expand=' in row and 'data-bs-toggle' not in row
