"""Centralized logging configuration for the Flask ``hello_world`` service.

This module is the Python successor to the single ``console.log(...)`` call in
the legacy Node.js implementation (``server.js`` lines 12-14)::

    server.listen(port, hostname, () => {
      console.log(`Server running at http://${hostname}:${port}/`);
    });

It fulfils the "logging" capability mandated by the project rule by replacing
that ad-hoc ``console.log`` with the Python standard :mod:`logging` module,
configured declaratively through :func:`logging.config.dictConfig`.

Responsibilities
----------------
* :func:`configure_logging` -- install a process-wide logging configuration
  sourced from ``app.config['LOG_LEVEL']`` (validating that value and falling
  back to ``'INFO'`` on an unrecognized name). It installs **two** formatter /
  handler pairs:

  - a **structured** ``default`` formatter
    (``[%(asctime)s] %(levelname)s in %(module)s: %(message)s`` -- Flask's own
    conventional format) on the root ``console`` handler, so ordinary
    application logs (notably the middleware's per-request before/after lines)
    carry the ``[<ts>] <LEVEL> in <module>: <message>`` prefix the
    observability checkpoint requires; and
  - a **bare** ``%(message)s`` ``startup`` formatter on a dedicated
    ``startup_console`` handler wired only to the non-propagating
    :data:`STARTUP_LOGGER_NAME` logger, reserved exclusively for the startup
    banner.

  It deliberately does **not** emit the startup banner itself (see below).
* :func:`log_startup` -- emit the single canonical startup line
  ``Server running at http://{HOST}:{PORT}/`` through the dedicated startup
  logger so it renders byte-for-byte (no prefix), mirroring the legacy server's
  output including the trailing slash.

Two log renderings, one configuration (observability checkpoint)
----------------------------------------------------------------
A single ``%(message)s`` formatter cannot satisfy both observability
requirements at once: the startup banner must be byte-for-byte bare, yet the
per-request logs must carry the structured ``[<ts>] <LEVEL> in <module>:``
prefix. This module resolves that by splitting the two concerns across two
loggers: the **root** logger (structured ``console`` handler) renders every
ordinary log line, while the dedicated, non-propagating
:data:`STARTUP_LOGGER_NAME` logger (bare ``startup_console`` handler) renders
the banner only. Because the startup logger does not propagate, the banner is
emitted exactly once and never picks up the structured prefix.

Why the startup line lives in its own function (AAP 0.6.3)
----------------------------------------------------------
The legacy server prints the "Server running at ..." line **exactly once**, when
``server.listen`` fires. Under Gunicorn the WSGI callable (``wsgi:app`` ->
:func:`app.create_app`) is imported and executed **once per worker** when
``preload_app`` is left at its default of ``False``. If ``configure_logging``
(invoked from the application factory, i.e. per worker) also emitted the banner,
the line would be duplicated once per worker -- diverging from the legacy
single-emission behavior. The banner is therefore isolated in
:func:`log_startup`, which the *entrypoints* call exactly once: ``run.py`` before
``app.run`` for development, and a Gunicorn master-process hook (``on_starting``)
for production. In production that hook lives in ``gunicorn.conf.py`` -- which
Gunicorn auto-loads from the working directory for the bare
``gunicorn wsgi:app`` command (no ``-c`` flag required) -- and is mirrored in
``wsgi.py`` for the explicit ``gunicorn -c wsgi.py wsgi:app`` invocation; both
delegate to :func:`log_startup`, so the banner fires once in the master process
regardless of which command is used. Keeping the exact wording in a single
function also guarantees there is one, and only one, source of truth for the
message.

Design constraints
------------------
* **Standard library only.** This module imports nothing beyond
  :mod:`logging` / :mod:`logging.config`. In particular it never imports
  ``app.config``; configuration values are read off the ``app.config`` mapping
  passed in by the caller, which keeps the module free of any circular import
  with the application factory in ``app/__init__.py``.
* **The HTTP response contract is untouched.** Logging is a pure side effect; it
  never influences the HTTP status code, headers, or body returned to a client
  (the deterministic ``200`` / ``text/plain`` / ``Hello, World!\\n`` response is
  owned by ``app/routes.py``).
"""

import logging
import logging.config

# Name of the dedicated, non-propagating logger that carries the startup banner.
# The banner ("Server running at http://{HOST}:{PORT}/") must render byte-for-byte
# with NO prefix, while every other application log line (notably the middleware's
# per-request before/after records) must render with the structured
# ``[<ts>] <LEVEL> in <module>: <message>`` prefix. Those two requirements are
# satisfied by giving the banner its own logger (this name) wired to a bare
# message-only handler with ``propagate=False`` -- see :func:`configure_logging`
# (which defines it) and :func:`log_startup` (which emits through it). Kept as a
# module-level constant so the configuration and the emission site cannot drift.
STARTUP_LOGGER_NAME = 'hello_world.startup'


def configure_logging(app):
    """Configure process-wide logging via :func:`logging.config.dictConfig`.

    Installs two ``StreamHandler`` s (both writing to ``stderr`` by default,
    matching Flask's own logging destination):

    * a **structured** root ``console`` handler
      (``[%(asctime)s] %(levelname)s in %(module)s: %(message)s``) at the
      verbosity named by ``app.config['LOG_LEVEL']`` (defaulting to ``'INFO'``).
      Configuring the *root* logger ensures every logger that propagates to it --
      including Flask's ``app.logger`` and the request logger used by the
      middleware -- emits through this handler at the chosen level, carrying the
      structured ``[<ts>] <LEVEL> in <module>: <message>`` prefix; and
    * a **bare** ``startup_console`` handler (``%(message)s``) wired solely to the
      dedicated, non-propagating :data:`STARTUP_LOGGER_NAME` logger, used only by
      :func:`log_startup` so the startup banner renders with no prefix.

    Robust ``LOG_LEVEL`` handling
    -----------------------------
    The configured ``LOG_LEVEL`` is **validated** before it is used. An
    unrecognized level name -- typically an environment-variable typo such as
    ``'BOGUS'`` -- is replaced with the safe ``'INFO'`` default and surfaced via
    a single, actionable warning. This is deliberate: handing an unknown level
    straight to :func:`logging.config.dictConfig` raises
    ``ValueError: Unknown level`` (``"Unable to configure root logger"``), which
    would abort :func:`app.create_app` and take every Gunicorn worker down with
    an opaque traceback. Falling back keeps the service available on a config
    typo while still telling the operator what happened. Recognized names (the
    standard ``CRITICAL``/``ERROR``/``WARNING``/``INFO``/``DEBUG`` plus their
    documented aliases, as enumerated by
    :func:`logging.getLevelNamesMapping`) pass through unchanged; a non-string
    level (e.g. a numeric ``logging.INFO``) is also accepted as-is.

    Honoring ``LOG_LEVEL`` on ``app.logger`` (even in debug mode)
    -------------------------------------------------------------
    After configuring the root logger, the resolved level is pinned onto
    ``app.logger`` explicitly via :meth:`logging.Logger.setLevel`. Configuring
    only the root level is insufficient in development: ``DevelopmentConfig``
    sets ``DEBUG=True``, and Flask's ``create_logger`` force-sets
    ``app.logger.level = DEBUG`` whenever ``app.debug`` is true and the logger
    has no explicit level. Request/response records then originate at
    ``app.logger`` (effective ``DEBUG``) and propagate to the root console
    handler (handler level ``NOTSET`` = 0), bypassing the root level -- so a
    ``LOG_LEVEL=WARNING`` would fail to suppress the INFO request logs. Pinning
    the level on ``app.logger`` makes the configured verbosity authoritative in
    *both* development and production, regardless of the debug flag.

    This function is invoked from the application factory
    (:func:`app.create_app`) and is therefore executed once per Gunicorn worker.
    It is intentionally **idempotent in effect**:
    :func:`logging.config.dictConfig` *replaces* the active configuration on each
    call, so invoking it repeatedly (e.g. once per worker, or once per test that
    builds an app) simply re-establishes the same handler set rather than
    accumulating duplicate handlers.

    The startup banner is deliberately **not** emitted here -- doing so would
    duplicate it once per worker (see the module docstring and
    :func:`log_startup`).

    Args:
        app: The Flask application whose ``config`` mapping supplies the
            ``LOG_LEVEL`` value and whose ``app.logger`` level is pinned to the
            resolved verbosity (see above). Apart from that logger-level
            assignment, no other attribute of the application is mutated.
    """
    # Resolve the desired verbosity from configuration, falling back to the same
    # 'INFO' default declared in ``app/config.py`` so the two modules agree even
    # when this helper is exercised in isolation. The raw value is preserved so
    # the warning below can report exactly what the operator supplied.
    raw_level = app.config.get('LOG_LEVEL', 'INFO')

    # Normalize and VALIDATE the level. String names are upper-cased so an
    # otherwise-valid but differently-cased value (e.g. 'info') is accepted, then
    # checked against the set of names the logging module actually recognizes
    # (``logging.getLevelNamesMapping()`` -> CRITICAL/ERROR/WARNING/INFO/DEBUG
    # plus the FATAL/WARN/NOTSET aliases). An unrecognized name (a config typo
    # such as 'BOGUS') is NOT passed to ``dictConfig`` -- doing so raises
    # ``ValueError: Unknown level`` and aborts ``create_app()``, taking every
    # Gunicorn worker down. Instead it is replaced with the safe 'INFO' default
    # and flagged so a single, actionable warning can be emitted once the logging
    # pipeline is live (see below). Non-string levels (e.g. a numeric
    # ``logging.INFO``) are accepted untouched, since ``dictConfig`` also accepts
    # integer levels.
    invalid_level = False
    if isinstance(raw_level, str):
        candidate = raw_level.upper()
        if candidate in logging.getLevelNamesMapping():
            log_level = candidate
        else:
            invalid_level = True
            log_level = 'INFO'
    else:
        log_level = raw_level

    logging.config.dictConfig({
        'version': 1,
        # Preserve loggers that already exist when this runs (Flask's
        # ``app.logger``, Werkzeug's logger, any third-party loggers); we only
        # (re)configure the formatters, handlers, and logger levels below.
        'disable_existing_loggers': False,
        'formatters': {
            # Structured, operator-facing format for ordinary application logs --
            # notably the per-request before/after lines emitted by the
            # middleware. This is Flask's own conventional default format and the
            # exact shape the observability checkpoint requires:
            # ``[<ts>] <LEVEL> in <module>: <message>`` (e.g.
            # ``[2026-01-01 12:00:00,000] INFO in middleware: GET /probe``). The
            # ``%(module)s`` token resolves to the source module of the logging
            # call site, so middleware records render ``in middleware:``.
            'default': {
                'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
            },
            # Message-only format reserved EXCLUSIVELY for the startup banner. The
            # canonical banner emitted by the entrypoints (``run.py`` before
            # ``app.run`` in development, and the Gunicorn ``on_starting`` hook in
            # production) must render byte-for-byte as
            # ``Server running at http://127.0.0.1:3000/`` -- identical to the
            # legacy Node ``console.log`` output (server.js:L13), trailing slash
            # included and with *no* leading prefix. Routing the banner through a
            # dedicated logger that uses this bare formatter (the
            # ``STARTUP_LOGGER_NAME`` logger below) preserves that byte-for-byte
            # parity while letting every *other* log line carry the structured
            # ``default`` prefix above. This is the fix for the prior conflict in
            # which a single ``%(message)s`` formatter stripped the structured
            # prefix from the request/response logs.
            'startup': {
                'format': '%(message)s',
            },
        },
        'handlers': {
            # Primary console handler for ordinary application logs. Uses the
            # structured ``default`` formatter and is attached to the root logger,
            # so every propagating logger (including Flask's ``app.logger`` and the
            # middleware request logger) is rendered with the structured prefix.
            'console': {
                # ``StreamHandler`` defaults to ``sys.stderr`` -- the same
                # destination Flask uses for its own default handler.
                'class': 'logging.StreamHandler',
                'formatter': 'default',
            },
            # Dedicated handler for the startup banner ONLY. Uses the bare
            # ``startup`` formatter so the banner is emitted with no prefix, and is
            # wired solely to the non-propagating ``STARTUP_LOGGER_NAME`` logger
            # below, so the banner is rendered exactly once, bare.
            'startup_console': {
                'class': 'logging.StreamHandler',
                'formatter': 'startup',
            },
        },
        'loggers': {
            # Dedicated, non-propagating logger that carries the startup banner.
            # :func:`log_startup` emits through this logger so the banner renders
            # via the bare ``startup`` formatter (no prefix), byte-for-byte
            # identical to the legacy line. ``propagate`` is ``False`` so the
            # record does NOT also travel to the structured root ``console``
            # handler -- that guarantees the banner appears exactly once and is
            # never prefixed. Its level is pinned to ``INFO`` independently of the
            # configured ``LOG_LEVEL`` so the banner is always emitted at startup,
            # mirroring the legacy ``console.log`` that fired unconditionally.
            STARTUP_LOGGER_NAME: {
                'level': 'INFO',
                'handlers': ['startup_console'],
                'propagate': False,
            },
        },
        'root': {
            # Honor the configured verbosity at the root logger so that every
            # propagating logger (including ``app.logger`` and the middleware
            # request logger) is filtered to it and rendered through the
            # structured ``console`` handler above.
            'level': log_level,
            'handlers': ['console'],
        },
    })

    # Pin the resolved level onto the application logger explicitly. The root
    # level set above is not sufficient on its own: in development mode
    # (``DEBUG=True``) Flask's ``create_logger`` forces ``app.logger.level`` to
    # ``DEBUG`` the first time the logger is accessed, after which INFO records
    # originate at ``app.logger`` (effective ``DEBUG``) and stream straight
    # through the root console handler (handler level ``NOTSET`` = 0), never
    # consulting the root level. Setting the level on ``app.logger`` here makes
    # ``LOG_LEVEL`` authoritative in both development and production (e.g.
    # ``LOG_LEVEL=WARNING`` correctly suppresses the INFO request/response logs).
    #
    # Accessing ``app.logger`` at this point is safe with respect to emission
    # parity: the root console handler is already configured by the
    # ``dictConfig`` call above, so Flask's ``has_level_handler`` check passes and
    # it does NOT attach a second, default handler to ``app.logger`` -- each
    # record is therefore still emitted exactly once.
    app.logger.setLevel(log_level)

    # If the configured ``LOG_LEVEL`` was unrecognized, surface a single,
    # operator-facing warning now -- after the pipeline is live and the app
    # logger is pinned to the (fallback) 'INFO' level, so this ``WARNING`` record
    # (level 30 >= the effective INFO level 20) is guaranteed to be emitted
    # through the console handler rather than silently dropped. ``%``-style lazy
    # interpolation defers formatting until emission; ``%r`` quotes the offending
    # value so it is unambiguous in the log.
    if invalid_level:
        app.logger.warning(
            "Invalid LOG_LEVEL %r; falling back to 'INFO'. "
            "Valid levels: CRITICAL, ERROR, WARNING, INFO, DEBUG.",
            raw_level,
        )


def log_startup(app):
    """Emit the canonical startup banner exactly once, with no prefix.

    Logs the line ``Server running at http://{HOST}:{PORT}/`` through the
    dedicated, non-propagating ``STARTUP_LOGGER_NAME`` logger (configured by
    :func:`configure_logging` with the bare ``%(message)s`` formatter). With the
    default configuration this renders as ``Server running at
    http://127.0.0.1:3000/`` -- byte-for-byte identical to the legacy Node.js
    server's ``console.log`` output (``server.js`` line 13), including the
    trailing slash and with **no** ``[<ts>] <LEVEL> in <module>:`` prefix.

    Why a dedicated logger (not ``app.logger``)
    -------------------------------------------
    Ordinary application logs -- in particular the middleware's per-request
    before/after records emitted through ``app.logger`` -- must carry the
    structured ``[<ts>] <LEVEL> in <module>: <message>`` prefix (the
    observability checkpoint requires it). The startup banner, by contrast, must
    stay byte-for-byte bare. Emitting the banner through this separate logger --
    which :func:`configure_logging` wires to the bare ``startup`` formatter with
    ``propagate=False`` -- satisfies both at once: the request logs are
    structured (via the root ``console`` handler) while the banner is bare (via
    the ``startup_console`` handler) and is never duplicated onto the structured
    handler. The dedicated logger is pinned at ``INFO`` regardless of
    ``LOG_LEVEL``, so the banner always fires at startup just as the legacy
    ``console.log`` did.

    This is the *single* source of truth for the startup message. It is invoked
    by the entrypoints -- ``run.py`` before ``app.run`` in development, the
    Gunicorn master-process ``on_starting`` hook (auto-loaded from
    ``gunicorn.conf.py`` for the bare ``gunicorn wsgi:app`` command, and also
    defined in ``wsgi.py`` for the explicit ``-c wsgi.py`` invocation) in
    production -- so that the banner is printed once at startup rather than once
    per worker (AAP 0.6.3).

    Args:
        app: The Flask application supplying ``config`` (for the ``HOST`` /
            ``PORT`` values). The banner is emitted through the dedicated
            startup logger rather than ``app.logger`` (see above).
    """
    # Source host/port from configuration, defaulting to the legacy loopback
    # binding (``server.js`` lines 3-4: hostname='127.0.0.1', port=3000) so the
    # banner matches the original server out of the box.
    host = app.config.get('HOST', '127.0.0.1')
    port = app.config.get('PORT', 3000)

    # Emit through the dedicated, non-propagating startup logger so the banner
    # renders via the bare ``startup`` formatter (no prefix) and is never
    # duplicated onto the structured root handler. %-style lazy interpolation
    # defers formatting until emission; the trailing slash after the port is
    # mandatory for byte-for-byte parity with the legacy line (server.js:L13).
    logging.getLogger(STARTUP_LOGGER_NAME).info(
        'Server running at http://%s:%s/', host, port
    )
