"""
/healthz is Railway's deploy healthcheck (railway.toml): it must answer 200
to an anonymous plain-HTTP request, even with production's SSL redirect on.
"""
import pytest
from django.test import override_settings


@pytest.mark.unit
@pytest.mark.django_db
def test_healthz_is_public(client):
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.content == b'ok'


@pytest.mark.unit
@pytest.mark.django_db
@override_settings(
    SECURE_SSL_REDIRECT=True,
    SECURE_REDIRECT_EXEMPT=[r'^healthz$'],
    ALLOWED_HOSTS=['healthcheck.railway.app'],
)
def test_healthz_skips_ssl_redirect(client):
    response = client.get('/healthz', HTTP_HOST='healthcheck.railway.app')
    assert response.status_code == 200
