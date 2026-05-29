"""Parity tests for the Flask rewrite of the legacy Node.js Hello-World server.

These tests assert that the Flask application reproduces the legacy server's
HTTP contract byte-for-byte. Behavioral reference: legacy ``server.js`` which
responded to every request (any method, any path) with status 200,
``Content-Type: text/plain`` (no charset), and the 14-byte body
``Hello, World!`` followed by a newline.

The app is built via the application factory (``from app import create_app``)
and exercised through Flask's ``test_client()``.
"""
import io
import logging
from contextlib import redirect_stderr

import pytest
from werkzeug.test import run_wsgi_app

from app import create_app
from app.config import Config
from app.middleware import _sanitize_log_value

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


# ---------------------------------------------------------------------------
# Regression tests for the Infrastructure & Observability QA checkpoint
# (F5 logging, F4 request-logging middleware). Each guards one finding so the
# resolved behavior cannot silently regress.
# ---------------------------------------------------------------------------


def _redirect_console_handler_to_buffer():
    """Point the configured root ``StreamHandler`` at a fresh ``StringIO``.

    ``configure_logging`` (run inside ``create_app``) installs a single root
    ``StreamHandler`` writing to stderr. For deterministic assertions we
    redirect that handler's stream to an in-memory buffer and read it back. The
    next ``create_app`` re-runs ``dictConfig``, which replaces the handler, so
    this redirection never leaks across tests.
    """
    buf = io.StringIO()
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.stream = buf
    return buf


def test_log_level_honored_in_development_debug_mode():
    """Finding 1: LOG_LEVEL must be honored even when DEBUG=True (dev mode).

    Flask forces ``app.logger.level = DEBUG`` in debug mode; ``configure_logging``
    must pin ``app.logger`` to the configured level so ``LOG_LEVEL=WARNING``
    suppresses the INFO request/response logs.
    """
    class WarningDevConfig(Config):
        DEBUG = True
        LOG_LEVEL = 'WARNING'

    app = create_app(WarningDevConfig)
    assert app.debug is True
    # The application logger must honor the configured WARNING level rather than
    # the DEBUG that Flask would otherwise force on in debug mode.
    assert app.logger.level == logging.WARNING

    buf = _redirect_console_handler_to_buffer()
    app.testing = True
    app.test_client().get('/probe')
    out = buf.getvalue()
    # INFO request/response lines must be SUPPRESSED at LOG_LEVEL=WARNING.
    assert 'GET /probe' not in out
    assert 'status=200' not in out


def test_log_level_info_still_emits_request_logs():
    """Finding 1 companion: at LOG_LEVEL=INFO the request logs DO appear."""
    class InfoDevConfig(Config):
        DEBUG = True
        LOG_LEVEL = 'INFO'

    app = create_app(InfoDevConfig)
    assert app.logger.level == logging.INFO

    buf = _redirect_console_handler_to_buffer()
    app.testing = True
    app.test_client().get('/probe')
    out = buf.getvalue()
    assert 'GET /probe' in out
    assert 'status=200' in out


def test_invalid_log_level_falls_back_without_crashing():
    """Finding 2: an invalid LOG_LEVEL must NOT crash application creation.

    It must fall back to ``INFO`` and emit a single actionable warning naming
    ``LOG_LEVEL`` instead of raising ``ValueError`` (which would take every
    Gunicorn worker down at startup).
    """
    class BogusConfig(Config):
        DEBUG = False
        LOG_LEVEL = 'BOGUS'

    buf = io.StringIO()
    # ``configure_logging`` emits the warning during ``create_app``; capture
    # stderr so the ``StreamHandler`` created inside ``dictConfig`` writes into
    # our buffer.
    with redirect_stderr(buf):
        app = create_app(BogusConfig)  # must NOT raise

    # Fallback applied: both the root and the application logger resolve to INFO.
    assert logging.getLogger().level == logging.INFO
    assert app.logger.level == logging.INFO

    warning = buf.getvalue()
    assert 'LOG_LEVEL' in warning
    assert 'BOGUS' in warning
    assert 'INFO' in warning


def test_invalid_log_level_app_still_serves_contract():
    """Finding 2: after the fallback, the frozen HTTP contract is unaffected."""
    class BogusConfig(Config):
        DEBUG = False
        LOG_LEVEL = 'nope-not-a-level'

    app = create_app(BogusConfig)
    app.testing = True
    response = app.test_client().get('/')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain'
    assert 'charset' not in response.headers['Content-Type']
    assert response.headers['Content-Length'] == '14'
    assert response.data == EXPECTED_BODY


def test_sanitize_log_value_neutralizes_control_chars():
    """Finding 3 (unit): the sanitizer escapes CR/LF and other control chars."""
    raw = '/inject\r\nstatus=999\tx\x00y'
    safe = _sanitize_log_value(raw)
    # No raw control characters survive.
    assert '\r' not in safe
    assert '\n' not in safe
    assert '\t' not in safe
    assert '\x00' not in safe
    # The control characters are present only in their escaped, single-line form.
    assert '\\x0d' in safe   # CR
    assert '\\x0a' in safe   # LF
    # Ordinary printable characters (and the space) pass through unchanged.
    assert _sanitize_log_value('/normal/path-1_2.txt') == '/normal/path-1_2.txt'
    assert _sanitize_log_value('/a b') == '/a b'


def test_crlf_path_does_not_forge_log_lines():
    """Finding 3 (integration): a CRLF-injected path yields exactly two records.

    Werkzeug decodes ``%0d%0a`` into literal CR/LF in ``PATH_INFO``. The
    ``before_request`` log must neutralize them so a single request produces
    exactly one before_request line and one after_request (``status=200``)
    line -- never the forged ``status=999`` / ``GET /fake`` lines an attacker
    tries to inject.
    """
    class InfoConfig(Config):
        DEBUG = False
        LOG_LEVEL = 'INFO'

    app = create_app(InfoConfig)
    buf = _redirect_console_handler_to_buffer()

    # PATH_INFO already containing literal CR/LF -- exactly what Werkzeug yields
    # after decoding /inject%0d%0astatus=999%0aFORGEDLINE%0d%0aGET%20/fake.
    decoded_path = '/inject\r\nstatus=999\nFORGEDLINE\r\nGET /fake'
    environ = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': decoded_path,
        'SERVER_NAME': '127.0.0.1',
        'SERVER_PORT': '3000',
        'wsgi.url_scheme': 'http',
        'wsgi.input': io.BytesIO(b''),
        'wsgi.errors': io.StringIO(),
        'CONTENT_LENGTH': '0',
    }
    run_wsgi_app(app, environ, buffered=True)
    out = buf.getvalue()
    lines = out.rstrip('\n').split('\n')

    # Exactly two log records for the single request: one before, one after.
    assert len(lines) == 2
    # The after_request line is the genuine one and reports the real status.
    assert lines[1] == 'status=200'
    # No raw CR/LF leaked into the log stream.
    assert '\r' not in out
    # The forged tokens never appear as standalone records.
    assert '\nstatus=999' not in out
    assert '\nGET /fake' not in out
