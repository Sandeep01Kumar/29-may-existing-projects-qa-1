"""Production WSGI entrypoint for the Flask ``hello_world`` service.

This module is the **WSGI boundary** -- the single import target a production
WSGI server (Gunicorn, supervised by PM2) loads to obtain the application
callable. It is the Python successor to the legacy Node.js ``server.listen(...)``
call (``server.js`` lines 12-14)::

    server.listen(port, hostname, () => {              // server.js:L12-L14
      console.log(`Server running at http://${hostname}:${port}/`);
    });

but with a deliberate inversion of responsibility: where the Node script
*started* a server, this module merely *exposes* a fully-configured WSGI
application object and lets the external server (Gunicorn) own the socket, the
worker model, and the request loop. That separation is the canonical production
WSGI pattern (AAP 0.3.2 "Production WSGI boundary").

The import target: ``wsgi:app``
-------------------------------
Gunicorn is invoked (by ``ecosystem.config.js`` under PM2) as::

    gunicorn wsgi:app -b 127.0.0.1:3000 -w 2

The ``wsgi:app`` token means "import the module ``wsgi`` and use its module-level
attribute ``app`` as the WSGI application." This module therefore MUST expose a
module-level callable named ``app``; that is the one mandatory contract of the
file (AAP 0.4.1). The default bind ``127.0.0.1:3000`` -- which preserves the
legacy loopback-only behavior (``server.js`` lines 3-4) -- is supplied by
Gunicorn's arguments / configuration, never hard-coded here.

How ``app`` is built
--------------------
``app`` is produced by the application factory :func:`app.create_app` (defined in
``app/__init__.py``), imported with the absolute ``from app import create_app``
convention mandated by AAP 0.4.2. The factory performs *all* construction work --
configuration loading, logging setup, middleware registration, Blueprint
registration, and defensive error handlers -- so this module does no wiring of
its own. Calling it at import time yields a ready-to-serve :class:`flask.Flask`
instance that answers every request with the frozen contract (``200`` /
``text/plain`` / ``Hello, World!\\n``).

The legacy ``const http = require('http')`` has no counterpart here: the
Flask/Werkzeug stack (driven by Gunicorn) supplies the server, so no
core-``http``-style import is needed.

Worker safety (AAP 0.6.3)
-------------------------
Under Gunicorn's default ``preload_app = False``, ``wsgi:app`` is imported once
per worker process, so ``create_app()`` runs once per worker. This is safe
because the factory builds an application that holds **no shared mutable
state** -- every request returns the same constant response with no I/O and no
cross-request bookkeeping. This module deliberately introduces no module-level
mutable state of its own (only the immutable ``app`` reference), preserving that
guarantee across any number of workers.

Startup banner (optional, AAP 0.6.3)
------------------------------------
The legacy server logged ``Server running at http://127.0.0.1:3000/`` exactly
once, when ``server.listen`` fired. The application factory intentionally does
**not** emit that banner (doing so would duplicate it once per worker), so under
Gunicorn the single-emission behavior is reproduced by the optional
:func:`on_starting` master-process hook below. See that function's docstring for
its precise activation conditions; the hook is a pure logging side effect and
never alters the WSGI contract.

Public symbols
--------------
* :data:`app` -- the WSGI application callable loaded as ``wsgi:app`` by
  Gunicorn/PM2. **This is the mandatory export.**
* :func:`on_starting` -- optional Gunicorn server hook that logs the startup
  banner once in the master process (active only when this module is passed to
  Gunicorn as a config file; see its docstring).
"""

# --- Internal package import (absolute, per AAP 0.4.2) ------------------------
# ``create_app`` is the application factory -- the Python successor to the legacy
# ``http.createServer(...)`` callback. The absolute ``from app import ...`` form
# keeps the import unambiguous regardless of how this module is loaded
# (``gunicorn wsgi:app``, ``python -c "import wsgi"``, or pytest). Per the file's
# dependency contract this is the module's *only* import: nothing from
# ``app.config`` / ``app.routes`` / ``app.middleware`` / ``app.logging_config`` is
# imported directly here.
from app import create_app

# --- The mandatory WSGI application object (export: ``app``) -------------------
# Build the fully-configured application eagerly at import time so that the
# ``wsgi:app`` import target resolves to a ready-to-serve WSGI callable the moment
# Gunicorn imports this module. ``create_app()`` is called with no arguments so it
# resolves its configuration from the environment (``FLASK_ENV``), defaulting to
# the legacy loopback settings (``127.0.0.1:3000``). This single assignment is the
# entire mandatory contract of the module; everything below it is optional,
# side-effect-free tooling. No socket is bound and no server is started by this
# line -- Gunicorn (in production) or ``run.py`` (in development) owns serving.
app = create_app()


def on_starting(server):
    """Gunicorn *master-process* server hook: emit the startup banner once.

    Logs ``Server running at http://{HOST}:{PORT}/`` -- byte-for-byte identical to
    the legacy Node.js ``console.log`` output (``server.js`` line 13), trailing
    slash included -- exactly **once**, in the Gunicorn master (arbiter) process,
    before any worker is forked. This reproduces the legacy server's
    single-emission startup behavior under a multi-worker WSGI server
    (AAP 0.6.3): because the line is emitted from the master rather than from the
    per-worker application factory, it is never duplicated across workers.

    Activation
    ----------
    Gunicorn invokes ``on_starting`` only when it loads a **configuration file**
    that defines it, i.e. when started as::

        gunicorn -c wsgi.py wsgi:app

    The default production invocation in ``ecosystem.config.js`` is
    ``gunicorn wsgi:app -b 127.0.0.1:3000 -w 2`` (no ``-c``), under which this
    hook lies dormant and the banner is simply not printed -- exactly as if the
    hook were absent. It is provided so that operators who prefer the config-file
    form get the legacy startup banner for free, with no other change. Defining
    this function has **no effect** on the ``wsgi:app`` import target: it is an
    ordinary module-level callable that Gunicorn discovers *by name* only when
    this module is used as its config file.

    The banner wording is emitted inline here (rather than delegating to
    ``app/logging_config.py``) to keep this module's import surface limited to the
    application factory, mirroring the identical inline emission already used by
    the development launcher ``run.py``. Host/port are read from the live
    application's configuration, defaulting to the legacy loopback ``127.0.0.1``
    and ``3000`` (``server.js`` lines 3-4).

    Args:
        server: The Gunicorn ``Arbiter`` instance supplied by the framework. It is
            part of the required hook signature but is not needed here -- the
            banner is derived from the application's own configuration -- so it is
            accepted and intentionally left unused.

    Returns:
        None. This hook performs a single logging side effect and returns nothing;
        it never touches the HTTP request/response path or the WSGI contract.
    """
    # Resolve host/port from the live application's configuration, falling back to
    # the legacy loopback defaults (server.js:L3-L4) so the banner matches the
    # original byte-for-byte even if the keys were somehow absent.
    host = app.config.get('HOST', '127.0.0.1')
    port = app.config.get('PORT', 3000)

    # Emit through the application's configured logger (installed by create_app via
    # ``app/logging_config.configure_logging``). %-style lazy interpolation defers
    # formatting until the record is actually emitted; the trailing slash after the
    # port is mandatory for byte-for-byte parity with server.js:L13.
    app.logger.info('Server running at http://%s:%s/', host, port)
