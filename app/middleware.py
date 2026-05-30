"""Request/response middleware for the Flask ``hello_world`` service.

This module supplies the **"middleware"** capability mandated by the project
rule, implemented the idiomatic Flask way through the application's
``before_request`` / ``after_request`` request hooks. The legacy Node.js
implementation (``server.js``) had *no* middleware layer at all -- its single
``http.createServer`` callback unconditionally wrote the response::

    const server = http.createServer((req, res) => {  // server.js:L6-L10
      res.statusCode = 200;
      res.setHeader('Content-Type', 'text/plain');
      res.end('Hello, World!\\n');
    });

These hooks are therefore a *production-grade enhancement layered on top of*
that behavior, not a port of any existing logic. They add observability
(per-request logging) and a defensive ``Content-Type`` guard **without changing
the observable success behavior** of the server.

Critical parity constraint (AAP 0.6.3)
--------------------------------------
The ``after_request`` hook **must not mutate the success response beyond
enforcing the bare** ``text/plain`` **media type**. The frozen public contract
that every code path must preserve is:

* status ``200``;
* body ``Hello, World!\\n`` -- exactly 14 bytes, including the trailing newline;
* ``Content-Type: text/plain`` with **no** ``charset`` suffix;
* ``Content-Length: 14``.

On the normal success path ``app/routes.py`` already constructs the response as
``Response('Hello, World!\\n', status=200, content_type='text/plain')``, so the
``Content-Type`` guard below is a verified **no-op** there. It exists only as a
defensive measure for any unexpected/edge response (e.g. a framework-generated
error page) so that no request can ever escape with a divergent media type.

Design notes
------------
* **Logging via** ``app.logger``. Emission goes through the application's own
  logger so it honors the process-wide configuration installed by
  ``app/logging_config.py`` (``configure_logging`` wires the root logger and a
  console handler; ``app.logger`` propagates to it). This module therefore does
  **not** create an ad-hoc / root logger of its own.
* **Lazy ``%``-style logging.** Log calls pass their interpolation arguments
  positionally (``app.logger.info('%s %s', request.method, sanitized_path)``)
  so the message is only formatted when the record is actually emitted -- never
  with eager f-strings.
* **Log-injection neutralization (CWE-117).** Werkzeug percent-decodes the
  request target, so ``request.path`` may contain raw CR/LF (from ``%0d%0a``)
  or other control characters. Logging it verbatim would let a single request
  forge extra log records. The ``before_request`` hook therefore routes the
  path through :func:`_sanitize_log_value`, which escapes control characters to
  ``\\xNN`` so each request yields exactly one before-line and one after-line.
  ``request.method`` needs no such treatment -- the HTTP request line cannot
  carry CR/LF inside the method token.
* **Never** ``response.mimetype = 'text/plain'``. Assigning the ``mimetype``
  property appends ``; charset=utf-8`` (empirically confirmed on
  Werkzeug 3.1.8), which would *break* the no-charset parity requirement. Only
  the bare header string is assigned: ``response.headers['Content-Type'] =
  'text/plain'``.
* **Imports only from** :mod:`flask`. The single dependency is the
  :data:`flask.request` proxy, used to read the incoming method and path inside
  the ``before_request`` hook. There are no internal (``app.*``) imports, which
  keeps this module free of any circular-import coupling with the application
  factory in ``app/__init__.py``.
* **No request-driven branching.** The hooks only *observe* the request (for
  logging); they never read or branch on the body/path to alter the response.
  The response itself is owned entirely by ``app/routes.py``.
"""

from flask import request


def _sanitize_log_value(value):
    """Neutralize control characters in a value before it is logged (CWE-117).

    Werkzeug percent-decodes the request target, so an attacker can smuggle raw
    carriage-return / line-feed bytes (``%0d%0a``) -- or any other control
    character -- into ``request.path``. Logging that value verbatim would let a
    *single* request forge additional log records (fake request lines, fake
    ``status=`` lines), corrupting the audit trail, SIEM ingestion, and any
    grep / line-count based monitoring -- a log-injection / log-forgery flaw
    (CWE-117). This helper defuses that by replacing every non-printable
    character with its ``\\xNN`` escape, so the returned value is always a
    single, printable token that still faithfully (and harmlessly) represents
    what was received.

    Printable characters -- letters, digits, punctuation, and the space -- are
    preserved unchanged so ordinary paths log exactly as before; only control
    characters (CR, LF, TAB, NUL, ESC, the rest of the C0/C1 ranges, and DEL)
    are escaped. Membership is decided by :meth:`str.isprintable`, which treats
    every Unicode control / separator character (except the ordinary space) as
    non-printable.

    Args:
        value (str): The raw value to sanitize, e.g. ``request.path``.

    Returns:
        str: ``value`` with every control character replaced by its ``\\xNN``
        escape; safe to embed in a single log line.
    """
    # Escape any non-printable character to a literal ``\xNN`` sequence (e.g. CR
    # -> ``\x0d``, LF -> ``\x0a``); keep printable characters as-is so normal
    # paths are unchanged. The result can never contain a real newline, so it
    # cannot break out of its log record.
    return ''.join(
        ch if ch.isprintable() else '\\x{:02x}'.format(ord(ch))
        for ch in value
    )


def register_middleware(app):
    """Attach the request/response hooks to ``app`` (the rule's "middleware").

    Registers two Flask hooks on the supplied application:

    * a ``before_request`` hook that logs the incoming request's HTTP method and
      path, and
    * an ``after_request`` hook that enforces the bare ``text/plain``
      ``Content-Type`` (defensively, as a no-op on the normal success path) and
      logs the outgoing response status.

    The function is invoked once from the application factory
    (``create_app`` in ``app/__init__.py``) during application construction. It
    has no return value; its effect is the side effect of registering the hooks
    on ``app``.

    Neither hook alters the frozen success contract (status ``200`` /
    ``text/plain`` with no charset / ``Content-Length: 14`` / body
    ``Hello, World!\\n``); see the module docstring and AAP 0.6.3.

    Args:
        app: The :class:`flask.Flask` application instance to attach the hooks
            to. Its ``logger`` attribute is used as the emission channel, so the
            output respects whatever logging configuration has already been
            installed (see ``app/logging_config.py``).
    """

    @app.before_request
    def _log_request():
        """Log the incoming request method and path, then defer to routing.

        The path is passed through :func:`_sanitize_log_value` first so that
        control characters Werkzeug may have decoded into it (notably CR/LF from
        ``%0d%0a``) cannot forge additional log records (CWE-117). Uses
        ``%``-style lazy interpolation so the message is only formatted if the
        record is emitted at the active level. Returns ``None`` so that Flask
        continues normal request dispatch -- returning any non-``None`` value
        here would short-circuit routing and replace the view's response, which
        would diverge from the legacy server's behavior.
        """
        # Observe the request for logging only; never branch on it to change
        # the response (the response is fixed by app/routes.py).
        #
        # ``request.path`` is sanitized before it is logged: Werkzeug
        # percent-decodes the request target, so an attacker can inject raw
        # CR/LF (``%0d%0a``) into the path and forge extra log lines
        # (log injection / forgery, CWE-117). ``_sanitize_log_value`` escapes
        # those control characters so a single request always produces exactly
        # one before_request record. ``request.method`` is left as-is: the HTTP
        # request line guarantees the method token contains no CR/LF, so it is
        # not an injection vector. ``%``-style args keep the interpolation lazy.
        app.logger.info('%s %s', request.method, _sanitize_log_value(request.path))
        # Explicitly return None: do NOT short-circuit the request dispatch.
        return None

    @app.after_request
    def _enforce_and_log(response):
        """Enforce a bare ``text/plain`` Content-Type and log the status.

        On the normal success path ``app/routes.py`` has already set
        ``Content-Type: text/plain`` (no charset), so the guard below does
        nothing. For any other (edge) response it coerces the header to the bare
        string ``'text/plain'`` -- *without* appending a charset, changing the
        status code, touching the body, or recomputing ``Content-Length``.

        Args:
            response: The :class:`flask.Response` produced by the view (or by
                Flask for an error path).

        Returns:
            flask.Response: The same ``response`` object, unchanged except for
            the defensive ``Content-Type`` normalization. The object **must** be
            returned; returning ``None`` (or anything else) would break the
            response.
        """
        # Enforce the bare 'text/plain' media type only when it is not already
        # exactly that value. Assigning the raw header string keeps it
        # charset-free; we deliberately avoid ``response.mimetype = 'text/plain'``
        # because that appends '; charset=utf-8' and would break parity.
        if response.headers.get('Content-Type') != 'text/plain':
            response.headers['Content-Type'] = 'text/plain'

        # Log the final response status with lazy %-style interpolation.
        app.logger.info('status=%s', response.status_code)

        # Always return the (un-mutated beyond Content-Type) response object.
        return response
