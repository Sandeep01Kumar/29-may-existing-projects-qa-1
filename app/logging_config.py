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
  (formatter + console handler + root logger level) sourced from
  ``app.config['LOG_LEVEL']``. It deliberately does **not** emit the startup
  banner (see below).
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
            ``LOG_LEVEL`` value. Only ``app.config`` is read; the application
            object itself is not mutated.
    """
    # Resolve the desired verbosity from configuration, falling back to the same
    # 'INFO' default declared in ``app/config.py`` so the two modules agree even
    # when this helper is exercised in isolation.
    log_level = app.config.get('LOG_LEVEL', 'INFO')

    # Normalize string level names to upper case so that an otherwise-valid but
    # differently-cased value (e.g. 'info') is still accepted. ``dictConfig``
    # expects canonical names such as 'INFO'/'WARNING'; an unexpected case would
    # otherwise raise ``ValueError``. Non-string levels (e.g. a numeric
    # ``logging.INFO``) are passed through untouched, since ``dictConfig`` also
    # accepts integer levels. This satisfies the "do not raise on a valid level
    # string" requirement without altering behavior for the canonical inputs.
    if isinstance(log_level, str):
        log_level = log_level.upper()

    logging.config.dictConfig({
        'version': 1,
        # Preserve loggers that already exist when this runs (Flask's
        # ``app.logger``, Werkzeug's logger, any third-party loggers); we only
        # (re)configure the formatter, handler, and root level below.
        'disable_existing_loggers': False,
        'formatters': {
            'default': {
                # Conventional Flask-style development format: timestamp, level,
                # originating module, then the message itself.
                'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
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
