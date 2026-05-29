"""Parity tests for the Flask rewrite of the legacy Node.js Hello-World server.

These tests assert that the Flask application reproduces the legacy server's
HTTP contract byte-for-byte. Behavioral reference: legacy ``server.js`` which
responded to every request (any method, any path) with status 200,
``Content-Type: text/plain`` (no charset), and the 14-byte body
``Hello, World!`` followed by a newline.

The app is built via the application factory (``from app import create_app``)
and exercised through Flask's ``test_client()``.
"""
import pytest

from app import create_app

EXPECTED_BODY = b'Hello, World!\n'   # 14 bytes including the trailing newline
EXPECTED_LENGTH = 14

# The seven methods the app explicitly declares (AAP 0.6.2).
METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']

# Representative paths: root, arbitrary, deep-nested, trailing-slash, and a
# /static/* path (must be owned by the catch-all, not Flask's static route).
PATHS = [
    '/',
    '/any/random/path',
    '/submit',
    '/a/b/c/d/e/f',
    '/trailing/',
    '/static/anything.txt',
]


@pytest.fixture
def client():
    """Build the app via the factory and return a Flask test client."""
    app = create_app()
    app.testing = True
    return app.test_client()


def _assert_contract_headers(response):
    """Assert the status and header parity shared by every response."""
    # Status is always 200 (legacy: res.statusCode = 200).
    assert response.status_code == 200
    # Content-Type is the BARE 'text/plain' with NO charset suffix.
    assert response.headers['Content-Type'] == 'text/plain'
    assert 'charset' not in response.headers['Content-Type']
    # Content-Length is exactly 14 on every response (including HEAD).
    assert response.headers['Content-Length'] == '14'


@pytest.mark.parametrize('path', PATHS)
def test_get_returns_hello_world(client, path):
    """GET on any path returns the exact 200/text/plain/14-byte contract."""
    response = client.get(path)
    _assert_contract_headers(response)
    assert response.data == EXPECTED_BODY
    assert len(response.data) == EXPECTED_LENGTH


@pytest.mark.parametrize('path', PATHS)
@pytest.mark.parametrize('method', METHODS)
def test_universal_method_and_path_acceptance(client, method, path):
    """Every method on every path returns the identical contract.

    HEAD strips the body (Werkzeug auto-derives it from GET) but keeps the
    headers; all other methods -- including OPTIONS, because the app sets
    provide_automatic_options=False -- return the full 14-byte body.
    """
    response = client.open(path, method=method)
    _assert_contract_headers(response)
    if method == 'HEAD':
        assert response.data == b''
    else:
        assert response.data == EXPECTED_BODY
        assert len(response.data) == EXPECTED_LENGTH


def test_options_has_body_not_allow_only(client):
    """OPTIONS reaches the view and returns the body (not an Allow-only reply)."""
    response = client.open('/', method='OPTIONS')
    _assert_contract_headers(response)
    assert response.data == EXPECTED_BODY


def test_head_has_empty_body_but_keeps_headers(client):
    """HEAD returns an empty body while preserving Content-Length: 14."""
    response = client.open('/', method='HEAD')
    _assert_contract_headers(response)
    assert response.data == b''


def test_trailing_slash_does_not_redirect(client):
    """strict_slashes=False => trailing-slash paths return 200, never a 308."""
    response = client.get('/trailing/')
    assert response.status_code == 200


def test_unconventional_method_still_returns_200(client):
    """Defensive guard: even an undeclared method yields the 200 contract.

    The app-level 404/405 error handlers return the same 200/text/plain body,
    so no request can produce an error status the legacy server would not.
    """
    response = client.open('/', method='PROPFIND')
    _assert_contract_headers(response)
    assert response.data == EXPECTED_BODY


def test_factory_preserves_legacy_loopback_defaults():
    """The factory yields the legacy loopback defaults (127.0.0.1:3000)."""
    app = create_app()
    assert app.config['HOST'] == '127.0.0.1'
    assert app.config['PORT'] == 3000
