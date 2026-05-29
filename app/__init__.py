"""Application package for the Flask ``hello_world`` service.

This module defines the **application factory** :func:`create_app`, the single
construct that builds and returns a fully-configured :class:`flask.Flask`
instance. It is the faithful Python successor to the legacy Node.js
``http.createServer(...)`` call (``server.js`` lines 6-10)::

    const server = http.createServer((req, res) => {  // server.js:L6-L10
      res.statusCode = 200;
      res.setHeader('Content-Type', 'text/plain');
      res.end('Hello, World!\\n');
    });

Where the legacy server collapsed server construction, configuration, and the
request handler into a single 14-line file, the factory delegates each concern
to a dedicated sibling module and merely *wires them together*:

* configuration         -> :mod:`app.config`         (env-driven ``Config`` classes)
* logging               -> :mod:`app.logging_config` (stdlib ``logging`` setup)
* routing               -> :mod:`app.routes`         (catch-all ``Blueprint``)
* middleware            -> :mod:`app.middleware`      (before/after request hooks)
* defensive guards      -> :mod:`app.routes`         (app-level 404/405 handlers)

Specification authority: AAP sections 0.1.2, 0.3.2 (Application Factory),
0.4.1, 0.4.2.

Why an application factory?
---------------------------
The factory pattern is the canonical Flask layout for anything beyond a single
module. It keeps **all** construction work inside :func:`create_app` so that:

* importing this package has **no side effects** -- it never instantiates an
  app, binds a port, or starts a server (those are the jobs of ``wsgi.py`` for
  Gunicorn/PM2 and ``run.py`` for development);
* tests can build isolated app instances and inject an alternative
  configuration via the ``config_class`` argument; and
* the returned app holds **no shared mutable state**, so it is safe to serve
  under multiple synchronous Gunicorn workers (AAP 0.6.3).

Frozen HTTP contract (byte-for-byte; do NOT alter)
--------------------------------------------------
The app returned by :func:`create_app` MUST answer **every** request -- any HTTP
method, any path -- with the exact contract the legacy server produced
(``server.js`` lines 6-10):

* status ``200``;
* body ``Hello, World!\\n`` -- exactly 14 bytes, including the trailing newline;
* ``Content-Type: text/plain`` with **no** ``charset`` suffix;
* ``Content-Length: 14`` (auto-computed by Werkzeug for the non-streamed body).

This factory does not implement that contract directly; it *enables* it by
registering the catch-all Blueprint (:data:`app.routes.bp`) and the defensive
404/405 handlers (:func:`app.routes.register_error_handlers`). It deliberately
adds nothing that could change the contract.

Public symbols
--------------
* :func:`create_app` -- the application factory consumed by ``wsgi.py``,
  ``run.py``, and ``tests/test_app.py`` via ``from app import create_app``.
"""

# --- External framework import (AAP 0.4.2) ------------------------------------
# Flask is the WSGI application class that replaces the legacy Node core ``http``
# module. The legacy ``const http = require('http')`` is dropped entirely; the
# Flask/Werkzeug stack supplies the server, so no ``http``-equivalent is needed.
from flask import Flask

# --- Internal package imports (absolute, per AAP 0.4.2/0.4.3) -----------------
# Every cross-module reference uses the absolute ``from app.<module> import ...``
# convention -- never relative imports -- so the import graph is unambiguous
# regardless of how the package is launched (``flask run``, ``python run.py``,
# ``gunicorn wsgi:app``, or ``pytest``).
from app.config import get_config, Config
from app.routes import bp, register_error_handlers
from app.middleware import register_middleware
from app.logging_config import configure_logging


def create_app(config_class=None):
    """Build and return a fully-configured Flask application.

    This is the application factory. It performs every piece of construction
    work for the ``hello_world`` service -- configuration loading, logging
    setup, middleware registration, route (Blueprint) registration, and the
    installation of defensive error handlers -- and returns the ready-to-serve
    :class:`flask.Flask` instance. It replaces the legacy Node.js
    ``http.createServer`` callback (``server.js`` lines 6-10).

    The function is intentionally callable with **zero arguments** so that the
    production entrypoints can use it directly (``wsgi.py`` exposes
    ``app = create_app()`` for Gunicorn/PM2; ``run.py`` calls ``create_app()``
    for the development server). The optional ``config_class`` parameter lets
    the test suite inject an alternative configuration object without relying on
    environment variables.

    Wiring order (and why it matters)
    ---------------------------------
    1. **Construct the app** with ``static_folder=None`` so Flask does *not*
       register its automatic ``/static/<path:filename>`` route. With static
       handling disabled, the universal catch-all in :mod:`app.routes` owns
       *every* path -- including ``/static/*`` -- guaranteeing the legacy
       "any path returns the same response" behavior (AAP 0.6.2). The defensive
       404 handler preserves parity even for paths Flask would not otherwise
       match.
    2. **Load the base configuration** (:class:`app.config.Config`) first. This
       establishes the full set of baseline settings -- ``HOST`` / ``PORT`` /
       ``LOG_LEVEL`` / ``FLASK_ENV`` (the legacy loopback defaults
       ``127.0.0.1:3000``) -- so they are always present even when a test
       injects a partial ``config_class`` that defines only a subset of values.
    3. **Select and overlay the active configuration.** When no ``config_class``
       is supplied, :func:`app.config.get_config` chooses
       ``DevelopmentConfig``/``ProductionConfig`` from ``FLASK_ENV``. The
       selected (or injected) class is layered on top of the base via
       :meth:`flask.Config.from_object`, which loads only UPPERCASE attributes
       (including inherited ones) into ``app.config``.
    4. **Initialize logging** (:func:`app.config`-driven
       :func:`app.logging_config.configure_logging`) *after* configuration is
       loaded -- because it reads ``app.config['LOG_LEVEL']`` -- and *before*
       the remaining registration steps, so any log emitted during middleware
       or route registration is captured by the configured handler.
    5. **Register middleware** (:func:`app.middleware.register_middleware`):
       the ``before_request`` / ``after_request`` hooks that log each request
       and defensively enforce the bare ``text/plain`` media type without
       altering the frozen success contract.
    6. **Register the routes Blueprint** (:data:`app.routes.bp`): the catch-all
       route that returns the fixed ``200`` / ``text/plain`` /
       ``Hello, World!\\n`` response for any method on any path.
    7. **Register defensive error handlers**
       (:func:`app.routes.register_error_handlers`): app-level ``404``/``405``
       handlers that return the same ``200`` response, ensuring no request can
       ever escape with an error status the legacy server would not have
       produced. These must be registered on the *application* (not the
       Blueprint), because Blueprint-scoped handlers do not catch routing
       ``404`` s.

    Args:
        config_class: Optional configuration object (typically a
            :class:`app.config.Config` subclass) to load on top of the base
            defaults. When ``None`` (the default), the class returned by
            :func:`app.config.get_config` is used, selecting the configuration
            appropriate to the current ``FLASK_ENV``.

    Returns:
        flask.Flask: A fully-configured application instance. After this call,
        ``app.config['HOST']``, ``app.config['PORT']``, and
        ``app.config['LOG_LEVEL']`` are populated (defaulting to
        ``'127.0.0.1'``, ``3000``, and ``'INFO'``), ``app.logger`` is usable,
        and the catch-all routes, middleware hooks, and defensive error handlers
        are all registered.
    """
    # Step 1 -- construct the WSGI application. ``static_folder=None`` disables
    # Flask's automatic static route so the catch-all Blueprint owns every path
    # (AAP 0.6.2). No work happens at import time; everything is contained here.
    app = Flask(__name__, static_folder=None)

    # Step 2 -- establish the baseline configuration. Loading the base
    # ``Config`` first guarantees the legacy loopback defaults
    # (HOST=127.0.0.1, PORT=3000, LOG_LEVEL=INFO, FLASK_ENV=development) are
    # always present, even if an injected ``config_class`` only overrides a
    # subset of them. ``from_object`` reads only UPPERCASE attributes.
    app.config.from_object(Config)

    # Step 3 -- select the active configuration when none was injected, then
    # overlay it. ``get_config`` resolves Development/Production from FLASK_ENV;
    # both are ``Config`` subclasses, so the default path reproduces the base
    # defaults exactly while adding the environment-specific ``DEBUG`` flag.
    if config_class is None:
        config_class = get_config()
    app.config.from_object(config_class)

    # Step 4 -- configure process-wide logging using the now-loaded LOG_LEVEL,
    # before any subsequent registration so those steps can log if needed.
    # Replaces the legacy ``console.log`` with the stdlib ``logging`` module.
    configure_logging(app)

    # Step 5 -- attach the before/after request hooks (request logging +
    # defensive text/plain enforcement). These never alter the success contract.
    register_middleware(app)

    # Step 6 -- mount the catch-all routing Blueprint that produces the fixed
    # 200 / text/plain / 'Hello, World!\n' response for every method and path.
    app.register_blueprint(bp)

    # Step 7 -- install the app-level 404/405 defensive guards that also return
    # the identical 200 response, so no request can ever yield an error status.
    register_error_handlers(app)

    # The fully-wired application is returned; callers decide how to serve it
    # (Gunicorn via wsgi.py, the dev server via run.py, or test_client in tests).
    return app
