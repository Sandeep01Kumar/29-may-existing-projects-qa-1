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
  (formatter + console handler + root *and* application logger level) sourced
  from ``app.config['LOG_LEVEL']``, validating that value and falling back to
  ``'INFO'`` on an unrecognized name. It deliberately does **not** emit the
  startup banner (see below).
* :func:`log_startup` -- emit the single canonical startup line
  ``Server running at http://{HOST}:{PORT}/`` that mirrors the legacy server's
  output byte-for-byte, including the trailing slash.

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
for production. Keeping the exact wording in a single function also guarantees
there is one, and only one, source of truth for the message.

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


def configure_logging(app):
    """Configure process-wide logging via :func:`logging.config.dictConfig`.

    Installs a single ``StreamHandler`` (which writes to ``stderr`` by default,
    matching Flask's own logging destination) wired to the root logger at the
    verbosity named by ``app.config['LOG_LEVEL']`` (defaulting to ``'INFO'``).
    Configuring the *root* logger ensures every logger that propagates to it --
    including Flask's ``app.logger`` and the request loggers used by the
    middleware -- emits through the same handler at the chosen level.

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
        # (re)configure the formatter, handler, and root level below.
        'disable_existing_loggers': False,
        'formatters': {
            'default': {
                # Message-only format: the rendered log line is *exactly* the
                # message passed to the logging call, with no timestamp / level /
                # module prefix. This is mandatory for startup-line parity. The
                # canonical banner emitted by the entrypoints (``run.py`` before
                # ``app.run`` in development, and the Gunicorn ``on_starting`` hook
                # in production) must render byte-for-byte as
                # ``Server running at http://127.0.0.1:3000/`` -- identical to the
                # legacy Node ``console.log`` output (server.js:L13), trailing
                # slash included and with *no* leading prefix. A prefixing
                # formatter (e.g. the conventional
                # ``[%(asctime)s] %(levelname)s in %(module)s: %(message)s``) would
                # prepend ``[<ts>] INFO in <module>: `` and break that
                # byte-for-byte equality. The request/response lines emitted by the
                # middleware render bare under this formatter too, which is
                # acceptable -- the logging *capability* is unchanged and only the
                # rendered prefix is dropped.
                'format': '%(message)s',
            },
        },
        'handlers': {
            'console': {
                # ``StreamHandler`` defaults to ``sys.stderr`` -- the same
                # destination Flask uses for its own default handler.
                'class': 'logging.StreamHandler',
                'formatter': 'default',
            },
        },
        'root': {
            # Honor the configured verbosity at the root logger so that every
            # propagating logger (including ``app.logger``) is filtered to it.
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
    """Emit the canonical startup banner exactly once.

    Logs the line ``Server running at http://{HOST}:{PORT}/`` at ``INFO`` level
    through ``app.logger``. With the default configuration this renders as
    ``Server running at http://127.0.0.1:3000/`` -- byte-for-byte identical to
    the legacy Node.js server's ``console.log`` output (``server.js`` line 13),
    including the trailing slash.

    This is the *single* source of truth for the startup message. It is invoked
    by the entrypoints -- ``run.py`` before ``app.run`` in development, and a
    Gunicorn master-process ``on_starting`` hook in production -- so that the
    banner is printed once at startup rather than once per worker (AAP 0.6.3).

    Args:
        app: The Flask application supplying ``config`` (for the ``HOST`` /
            ``PORT`` values) and ``logger`` (the emission channel).
    """
    # Source host/port from configuration, defaulting to the legacy loopback
    # binding (``server.js`` lines 3-4: hostname='127.0.0.1', port=3000) so the
    # banner matches the original server out of the box.
    host = app.config.get('HOST', '127.0.0.1')
    port = app.config.get('PORT', 3000)

    # Use %-style lazy interpolation (the arguments are only formatted if the
    # record is actually emitted). The trailing slash after the port is
    # mandatory for byte-for-byte parity with the legacy line (server.js:L13).
    app.logger.info('Server running at http://%s:%s/', host, port)
