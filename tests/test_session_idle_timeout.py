"""
Tests for session idle timeout: an authenticated session should be ended
after 15 minutes of inactivity (core.middleware.SessionIdleTimeoutMiddleware),
with an explicit "your session expired" message rather than a silent drop
into an anonymous session. settings.SESSION_COOKIE_AGE / SESSION_SAVE_EVERY_REQUEST
enforce the same policy independently at the session-store level; these
tests exercise the middleware's own explicit path since that's the one
with user-visible behavior to check.
"""
import time

import pytest
from django.conf import settings
from django.urls import reverse


@pytest.mark.django_db
class TestSessionIdleTimeout:
    def test_active_session_is_not_logged_out(self, director_client):
        """Two quick requests in a row (well under the timeout) should
        both succeed as the same authenticated user."""
        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        assert response.wsgi_request.user.is_authenticated

    def test_idle_session_beyond_timeout_is_logged_out(self, director_client):
        # Prime the session with a `last_activity` far enough in the past
        # to already exceed the configured timeout.
        response = director_client.get(reverse('home'))
        assert response.status_code == 200

        session = director_client.session
        session['last_activity'] = time.time() - settings.SESSION_IDLE_TIMEOUT_SECONDS - 60
        session.save()

        response = director_client.get(reverse('home'))
        assert response.status_code == 302
        assert response['Location'] == reverse('account_login')
        assert not response.wsgi_request.user.is_authenticated

    def test_idle_logout_shows_a_message(self, director_client):
        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        session = director_client.session
        session['last_activity'] = time.time() - settings.SESSION_IDLE_TIMEOUT_SECONDS - 60
        session.save()

        response = director_client.get(reverse('home'), follow=True)
        messages_shown = [str(m) for m in response.context['messages']]
        assert any('expiré' in m for m in messages_shown)

    def test_session_just_under_the_timeout_is_not_logged_out(self, director_client):
        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        session = director_client.session
        session['last_activity'] = time.time() - settings.SESSION_IDLE_TIMEOUT_SECONDS + 30
        session.save()

        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        assert response.wsgi_request.user.is_authenticated

    def test_anonymous_request_is_unaffected(self, client):
        response = client.get(reverse('account_login'))
        assert response.status_code == 200

    def test_session_cookie_age_matches_idle_timeout(self):
        assert settings.SESSION_COOKIE_AGE == settings.SESSION_IDLE_TIMEOUT_SECONDS == 15 * 60

    def test_activity_stamp_is_throttled_not_written_every_request(self, director_client):
        """A second request within SESSION_IDLE_TOUCH_INTERVAL_SECONDS of
        the first shouldn't rewrite `last_activity` — see the comment on
        SESSION_IDLE_TIMEOUT_SECONDS in settings.py for why this matters
        (a session-table write on every single authenticated request adds
        up fast, both in production and in this suite's own runtime)."""
        director_client.get(reverse('home'))
        first_stamp = director_client.session['last_activity']

        director_client.get(reverse('home'))
        second_stamp = director_client.session['last_activity']

        assert first_stamp == second_stamp
