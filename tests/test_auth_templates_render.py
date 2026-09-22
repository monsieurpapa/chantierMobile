"""
Ad-hoc smoke tests for the auth-page template rewrite (Falcon-styled,
extending falcon_base.html directly instead of the dead base.html
body_class/top_nav blocks). Not meant to be a permanent addition -- just
verifies every rewritten template renders without a TemplateSyntaxError,
NoReverseMatch, or missing-context crash for both the anonymous and
authenticated cases where relevant.
"""
import pytest
from django.urls import reverse
from allauth.account.models import EmailConfirmationHMAC, EmailAddress


@pytest.mark.django_db
class TestAuthPagesRender:
    def test_login(self, client):
        r = client.get(reverse('account_login'))
        assert r.status_code == 200
        assert b'chantiermobile-mark.svg' in r.content

    def test_signup(self, client):
        r = client.get(reverse('account_signup'))
        assert r.status_code == 200
        assert b'chantiermobile-logo.svg' in r.content
        assert b'falcon/assets' not in r.content

    def test_password_reset(self, client):
        r = client.get(reverse('account_reset_password'))
        assert r.status_code == 200
        assert b'chantiermobile-logo.svg' in r.content

    def test_password_reset_done(self, client):
        r = client.get(reverse('account_reset_password_done'))
        assert r.status_code == 200

    def test_password_reset_from_key_invalid_token(self, client):
        # allauth renders the "token_fail" branch for a bogus uid/token pair
        url = reverse('account_reset_password_from_key', kwargs={'uidb36': '1', 'key': 'bogus-token'})
        r = client.get(url, follow=True)
        assert r.status_code == 200
        assert 'invalide' in r.content.decode().lower() or 'Lien invalide' in r.content.decode()

    def test_password_reset_from_key_done(self, client):
        r = client.get(reverse('account_reset_password_from_key_done'))
        assert r.status_code == 200

    def test_account_inactive(self, client):
        r = client.get(reverse('account_inactive'))
        assert r.status_code == 200
        assert b'chantiermobile-logo.svg' in r.content

    def test_verification_sent(self, client):
        r = client.get(reverse('account_email_verification_sent'))
        assert r.status_code == 200

    def test_logout_get_shows_confirm_page(self, client, user):
        client.force_login(user)
        r = client.get(reverse('account_logout'))
        assert r.status_code == 200
        assert b'account_logout' in r.content or b'Se d\xc3\xa9connecter' in r.content

    def test_logout_post_logs_out_and_redirects(self, client, user):
        client.force_login(user)
        r = client.post(reverse('account_logout'))
        assert r.status_code == 302
        # session should now be anonymous
        r2 = client.get(reverse('accounts:profile_update'))
        assert r2.status_code in (302, 403)

    def test_password_change_page_for_logged_in_user(self, client, user):
        client.force_login(user)
        r = client.get(reverse('account_change_password'))
        assert r.status_code == 200
        assert b'chantiermobile-logo.svg' in r.content
        assert b'assets/img/logo.png' not in r.content

    def test_email_confirm_invalid_key(self, client):
        r = client.get(reverse('account_confirm_email', kwargs={'key': 'not-a-real-key'}))
        assert r.status_code == 200

    def test_profile_update_renders(self, client, user):
        # "Back to Home"/"Back to Dashboard" now use {% url 'home' %} instead
        # of a hardcoded href="/" -- since 'home' itself resolves to "/",
        # the rendered markup is the same; what matters is the page renders
        # without a NoReverseMatch, confirmed by the 200 here.
        client.force_login(user)
        r = client.get(reverse('accounts:profile_update'))
        assert r.status_code == 200
