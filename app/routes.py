"""URL routing for the Flask ``hello_world`` service.

This module supplies the **"routing"** capability mandated by the project rule,
implemented the idiomatic Flask way through a :class:`flask.Blueprint`. It is the
faithful Python port of the single behavior the legacy Node.js server exhibited:
**every request -- any HTTP method, any path -- returns one identical, fixed
response** (``server.js``:L6-L10)::

    const server = http.createServer((req, res) => {  // server.js:L6-L10
      res.statusCode = 200;
      res.setHeader('Content-Type', 'text/plain');
      res.end('Hello, World!\\n');
    });

The legacy ``http.createServer`` callback never inspected the request -- it had
no router, no method table, and no notion of a "not found" or "method not
allowed" path. It unconditionally wrote ``200`` / ``text/plain`` /
``Hello, World!\\n``. Flask, by contrast, is a *routed* framework whose defaults
diverge from that behavior (unmatched paths yield ``404``, unmatched methods
yield ``405``, and ``OPTIONS``/``HEAD`` are auto-handled). This module therefore
*neutralizes* those framework defaults so the observable contract stays
byte-for-byte identical to the legacy server.

Frozen public contract (byte-for-byte; AAP 0.2.2, 0.6.1)
--------------------------------------------------------
Every code path in this module preserves:

* status ``200``;
* body ``Hello, World!\\n`` -- exactly 14 bytes, including the trailing newline;
* ``Content-Type: text/plain`` with **no** ``charset`` suffix;
* ``Content-Length: 14`` (auto-computed by Werkzeug for the non-streamed body).

THE single most important parity directive (AAP 0.6.1) -- Content-Type
---------------------------------------------------------------------
The legacy server emits ``Content-Type: text/plain`` with **no** charset suffix.
Flask's three response-construction strategies behave differently -- empirically
re-confirmed against Flask 3.1.3 / Werkzeug 3.1.8 in this environment:

================================================================  ===========================  =======
Strategy                                                          Resulting Content-Type       Verdict
================================================================  ===========================  =======
``return 'Hello, World!\\n'`` (bare string)                        ``text/html; charset=utf-8``  wrong
``Response(..., mimetype='text/plain')``                          ``text/plain; charset=utf-8`` wrong
``Response('Hello, World!\\n', status=200,``                       ``text/plain``                exact
``         content_type='text/plain')``
================================================================  ===========================  =======

Consequently this module **always** constructs responses with the explicit
``content_type='text/plain'`` keyword. It **never** returns a bare string (which
yields ``text/html``) and **never** uses ``mimetype=`` (which appends
``; charset=utf-8``). Only the bare header string matches the legacy server.

Universal method & path acceptance (AAP 0.6.2)
----------------------------------------------
Two route rules are bound to a single view so that *both* the root and every
sub-path are covered, and the full HTTP method list is declared on each:

* ``@bp.route('/', defaults={'path': ''}, ...)`` -- the root, supplying an empty
  ``path`` argument to the shared view; and
* ``@bp.route('/<path:path>', ...)`` -- every other path (the ``path``
  converter matches slash-containing remainders, e.g. ``/a/b/c``).

Each rule declares ``methods=ALLOWED_METHODS`` plus two flags whose effect was
verified empirically:

* ``strict_slashes=False`` -- prevents Werkzeug's ``308`` redirect for
  trailing-slash variants the legacy server never issued (``GET /trailing/``
  returns ``200`` directly rather than redirecting).
* ``provide_automatic_options=False`` -- routes ``OPTIONS`` *to the view* so it
  returns the ``Hello, World!\\n`` body. With Flask's automatic ``OPTIONS``
  handling (the default), ``OPTIONS`` would short-circuit to an empty body plus
  an ``Allow`` header -- a divergence from the legacy behavior.

``HEAD`` is auto-derived from ``GET`` by Werkzeug (the body is stripped while the
headers, including ``Content-Length: 14``, are retained), which matches the
legacy handling; no special-casing is required.

Defensive error handlers (AAP 0.6.2)
------------------------------------
:func:`register_error_handlers` installs **app-level** ``404`` and ``405``
handlers that return the same ``200`` / ``text/plain`` response. These are a
belt-and-braces guard: the catch-all routes above already accept every method on
every path, but the handlers ensure that *no* request can ever escape with an
error status the legacy server would not have produced (verified for unusual
methods such as ``TRACE`` and ``PROPFIND``). They are registered on the
application -- **not** the Blueprint -- because Blueprint-scoped ``404`` handlers
do not catch routing ``404`` s; only ``@app.errorhandler(404)`` does.

Design notes
------------
* **Imports only from** :mod:`flask`. The module depends solely on
  :class:`flask.Blueprint` and :class:`flask.Response`; there are no internal
  (``app.*``) imports, which keeps it free of any circular-import coupling with
  the application factory in ``app/__init__.py`` (which imports ``bp`` and
  ``register_error_handlers`` from here).
* **No request-driven branching.** The view never reads or branches on the
  request body, headers, method, or path to vary the response -- the legacy
  server never did (AAP 0.2.2). Every request returns the same thing.
* **No shared mutable state.** The view and handlers hold no module-level mutable
  state, so the application is safe under multiple synchronous Gunicorn workers
  (AAP 0.6.3).
* **Plain text only.** There is no ``jsonify`` / JSON path; the body is always
  the fixed plain-text string (AAP 0.6.3).
* **Never stream.** The full body string is returned so Werkzeug computes
  ``Content-Length: 14`` automatically; the response is not streamed.

Public symbols
--------------
* :data:`bp` -- the ``'main'`` Blueprint carrying the catch-all routes; the
  application factory registers it via ``app.register_blueprint(bp)``.
* :func:`register_error_handlers` -- registers the defensive ``404``/``405``
  handlers on the application; the factory calls it as
  ``register_error_handlers(app)``.
"""

from flask import Blueprint, Response

# ---------------------------------------------------------------------------
# Blueprint -- the rule's "routing" capability.
#
# Named 'main'; the second argument (__name__) is the import name Flask uses to
# locate the blueprint's resources. The application factory registers this
# blueprint on the Flask app, mounting the catch-all routes defined below.
# ---------------------------------------------------------------------------
bp = Blueprint('main', __name__)

# The frozen response body, defined exactly once. 14 bytes including the
# trailing newline -- byte-for-byte parity with the legacy server's
# ``res.end('Hello, World!\n')`` (server.js:L9; ``od``-confirmed at 14 bytes).
RESPONSE_BODY = 'Hello, World!\n'

# The full HTTP method list accepted on every route. Declaring all of these
# (rather than relying on Flask's GET-only default) reproduces the legacy
# server's universal method acceptance -- it answered any method identically
# because it never consulted ``req.method`` (server.js:L6-L10).
ALLOWED_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']


@bp.route('/', defaults={'path': ''}, methods=ALLOWED_METHODS,
          strict_slashes=False, provide_automatic_options=False)
@bp.route('/<path:path>', methods=ALLOWED_METHODS,
          strict_slashes=False, provide_automatic_options=False)
def catch_all(path):
    """Return the fixed ``Hello, World!`` response for *any* method and path.

    This is the single view backing both route rules. The root rule supplies
    ``path=''`` via its ``defaults`` mapping; the ``/<path:path>`` rule supplies
    the matched remainder (which may itself contain slashes, e.g. ``a/b/c``).
    The ``path`` argument is accepted to satisfy both rules' signatures but is
    **deliberately ignored** -- the response never varies by path, exactly as the
    legacy server never inspected the request (AAP 0.2.2).

    The response is constructed with an explicit ``content_type='text/plain'``
    so the ``Content-Type`` header is the bare ``text/plain`` (no ``charset``
    suffix), matching the legacy header byte-for-byte (AAP 0.6.1). Returning a
    bare string would yield ``text/html`` and ``mimetype='text/plain'`` would
    append ``; charset=utf-8`` -- both are avoided here. The full body string is
    returned (not streamed) so Werkzeug auto-computes ``Content-Length: 14``.

    Args:
        path (str): The matched URL remainder (``''`` for the root). Accepted for
            both route rules' signatures and intentionally unused; the response
            is identical regardless of its value.

    Returns:
        flask.Response: A response with status ``200``, body
        ``Hello, World!\\n`` (14 bytes), and ``Content-Type: text/plain`` with no
        charset. ``HEAD`` requests reuse this via Werkzeug's auto-derivation
        (body stripped, ``Content-Length: 14`` retained).
    """
    # Explicit content_type='text/plain' => bare 'text/plain' (no charset).
    # This is THE parity-critical line (AAP 0.6.1): never a bare string, never
    # mimetype=. Status is 200 on this -- the only -- code path.
    return Response(RESPONSE_BODY, status=200, content_type='text/plain')


def register_error_handlers(app):
    """Install app-level ``404``/``405`` guards returning the success response.

    The catch-all routes in this module already accept every method on every
    path, so in normal operation these handlers are never reached. They exist as
    a defensive guard (AAP 0.6.2) ensuring that **no** request can ever produce
    an error status the legacy server would not have produced -- including
    unusual methods (e.g. ``TRACE``, ``PROPFIND``) that fall outside
    :data:`ALLOWED_METHODS` and would otherwise yield Flask's ``405``.

    The handlers are registered on the **application** rather than the
    Blueprint, because Blueprint-scoped ``404`` handlers do not catch routing
    ``404`` s -- only ``@app.errorhandler(404)`` does. Each handler returns the
    identical ``200`` / ``text/plain`` / ``Hello, World!\\n`` response produced
    by :func:`catch_all`, so the public contract holds on every code path.

    This function is invoked once from the application factory
    (``create_app`` in ``app/__init__.py``) as ``register_error_handlers(app)``.
    It has no return value; its effect is the side effect of registering the two
    handlers on ``app``.

    Args:
        app (flask.Flask): The application instance to attach the error handlers
            to.
    """

    @app.errorhandler(404)
    def _not_found(error):
        """Return the fixed ``200`` response in place of a ``404``.

        Args:
            error: The :class:`werkzeug.exceptions.NotFound` raised by routing.
                Accepted per Flask's error-handler signature and intentionally
                unused -- the response never varies.

        Returns:
            flask.Response: status ``200``, body ``Hello, World!\\n``,
            ``Content-Type: text/plain`` (no charset).
        """
        return Response(RESPONSE_BODY, status=200, content_type='text/plain')

    @app.errorhandler(405)
    def _method_not_allowed(error):
        """Return the fixed ``200`` response in place of a ``405``.

        Args:
            error: The :class:`werkzeug.exceptions.MethodNotAllowed` raised when
                a method outside :data:`ALLOWED_METHODS` is used. Accepted per
                Flask's error-handler signature and intentionally unused.

        Returns:
            flask.Response: status ``200``, body ``Hello, World!\\n``,
            ``Content-Type: text/plain`` (no charset).
        """
        return Response(RESPONSE_BODY, status=200, content_type='text/plain')
