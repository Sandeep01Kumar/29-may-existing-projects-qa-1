"""Gunicorn configuration for the Flask ``hello_world`` service.

Purpose
-------
This file exists for one reason: to make the **canonical, bare** production
command emit the legacy startup banner exactly once.

    gunicorn wsgi:app -b 127.0.0.1:3000 -w 2

Gunicorn's documented default configuration path is ``./gunicorn.conf.py`` (the
file is read from the directory Gunicorn is launched in). So when Gunicorn is
started with **no** ``-c`` flag from the repository root, it auto-loads *this*
file and runs the :func:`on_starting` hook below in the master (arbiter) process,
before any worker is forked. That reproduces the legacy Node.js server's
single-emission startup line under a multi-worker WSGI server (AAP 0.6.3).

Why this file is needed (the bug it fixes)
------------------------------------------
The startup banner is produced by a Gunicorn ``on_starting`` server hook, and
Gunicorn only invokes that hook from a loaded **configuration file**. Previously
the hook lived solely in ``wsgi.py`` and fired only under the explicit
``gunicorn -c wsgi.py wsgi:app`` form. The bare ``gunicorn wsgi:app`` command
loads ``wsgi.py`` only as the *application module* (to obtain ``wsgi:app``), not
as a config file, so its hook never ran and the bare command emitted **zero**
banners. Providing this auto-loaded ``gunicorn.conf.py`` makes the bare command
emit the banner once, while ``wsgi.py`` retains an equivalent hook as a fallback
for the explicit ``-c wsgi.py`` invocation.

No double-emission
------------------
Gunicorn loads exactly one configuration file per run: the one named by ``-c``
if given, otherwise the auto-discovered ``gunicorn.conf.py``. The two never load
together -- ``gunicorn -c wsgi.py wsgi:app`` ignores this file; bare
``gunicorn wsgi:app`` ignores ``wsgi.py``'s hook -- so the banner is emitted by
exactly one hook and is never duplicated. Both hooks delegate to the same
:func:`app.logging_config.log_startup`, so the wording is identical either way.

Relationship to ``ecosystem.config.js`` (PM2)
----------------------------------------------
The PM2 descriptor launches Gunicorn with ``args: 'wsgi:app -b 127.0.0.1:3000
-w 2'`` (the bare form, per AAP 0.6.5) and ``cwd`` set to the repository root, so
PM2-supervised Gunicorn auto-loads this file and emits the banner exactly as the
bare command does.

This module is a pure logging side effect at startup; it never binds a socket,
serves a request, or alters the frozen HTTP contract (that is owned by
``app/routes.py``). It deliberately sets no bind/worker options here -- those are
passed on the command line (``-b``/``-w``) so the single source of truth for the
deployment topology remains the launch command / ``ecosystem.config.js``.
"""

# Import the fully-configured WSGI application and the canonical banner emitter.
# Importing ``wsgi`` builds the application via ``create_app()`` (which installs
# the logging configuration, including the dedicated startup logger that
# ``log_startup`` emits through) so that, by the time :func:`on_starting` runs in
# the arbiter, the logging pipeline is ready. ``create_app`` has no side effects
# beyond building the app object -- it binds no socket and starts no server -- so
# importing it here in the master process is safe. Workers (forked after
# ``on_starting``) import ``wsgi:app`` independently and never emit the banner.
from wsgi import app
from app.logging_config import log_startup


def on_starting(server):
    """Gunicorn master-process hook: emit the startup banner exactly once.

    Gunicorn calls this hook once in the arbiter (master) process, before any
    worker is forked, when it has auto-loaded this file as its configuration
    (i.e. for the bare ``gunicorn wsgi:app`` command with no ``-c`` flag). It
    delegates to :func:`app.logging_config.log_startup`, the single source of
    truth for the banner, which emits ``Server running at
    http://{HOST}:{PORT}/`` -- byte-for-byte identical to the legacy Node.js
    ``console.log`` output (``server.js`` line 13), trailing slash included --
    through a dedicated, non-propagating bare-formatter logger (so the banner
    carries no structured prefix, unlike the request/response logs).

    Emitting from the master rather than from the per-worker application factory
    guarantees the banner appears exactly once regardless of the worker count
    (AAP 0.6.3).

    Args:
        server: The Gunicorn ``Arbiter`` instance supplied by the framework. It
            is part of the required hook signature but is not needed here -- the
            banner is derived from the application's own configuration -- so it
            is accepted and intentionally left unused.

    Returns:
        None. This hook performs a single logging side effect and returns
        nothing; it never touches the HTTP request/response path or the WSGI
        contract.
    """
    log_startup(app)
