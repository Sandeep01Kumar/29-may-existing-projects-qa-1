"""Development launcher for the Flask ``hello_world`` service.

This module is the development-time entrypoint -- the faithful Python
equivalent of running ``node server.js`` against the legacy implementation.
It builds the application through the factory and starts Flask's built-in
development server on the loopback interface, reproducing the legacy startup
behavior (including the canonical startup log line) exactly.

Legacy reference (``server.js`` lines 3-4 and 12-14)::

    const hostname = '127.0.0.1';                                  // L3
    const port = 3000;                                             // L4
    ...
    server.listen(port, hostname, () => {                          // L12-L14
      console.log(`Server running at http://${hostname}:${port}/`);
    });

Specification authority: AAP sections 0.4.1 (file-by-file plan) and 0.6.3
(startup logging parity).

Two entrypoints, one factory
----------------------------
The application is built exactly once by :func:`app.create_app`. Two thin
launchers consume it, each appropriate to a different runtime:

* ``run.py`` (this module) -- the **development** launcher. It starts Flask's
  built-in Werkzeug server via :meth:`flask.Flask.run`, mirroring the
  single-process ``node server.js`` developer experience.
* ``wsgi.py`` -- the **production** entrypoint. It exposes ``app`` for Gunicorn
  (supervised by PM2), which serves the same WSGI callable under multiple
  worker processes.

Neither launcher reimplements any application behavior; both merely *serve* the
app the factory returns, so the frozen HTTP contract (``200`` / ``text/plain``
/ ``Hello, World!\\n``) is identical no matter how the app is launched.

The startup banner (AAP 0.6.3)
------------------------------
The legacy server prints ``Server running at http://127.0.0.1:3000/`` exactly
once, when ``server.listen`` fires. The application factory deliberately does
**not** emit this banner (so it is not duplicated once per Gunicorn worker);
emitting it is the entrypoint's responsibility. This module therefore logs the
line -- byte-for-byte identical to the legacy output, trailing slash included --
through the configured ``app.logger`` immediately before handing control to the
development server.

Usage
-----
Run the development server directly (parity with ``node server.js``)::

    python run.py
    ./venv/bin/python run.py

Or via the console script declared in ``pyproject.toml``
(``[project.scripts] hello-world = "run:main"``)::

    hello-world

Both forms invoke :func:`main`, bind to ``HOST`` / ``PORT`` (defaulting to the
legacy ``127.0.0.1:3000``), and serve until interrupted. The bind address is
overridable through the environment (e.g. ``HOST=0.0.0.0 PORT=8080``) with no
code change, courtesy of :class:`app.config.Config`.

Public symbols
--------------
* :func:`main` -- the console-script / direct-invocation entrypoint that builds
  the app, logs the startup banner, and starts the development server.
"""

# --- Internal package imports (absolute, per AAP 0.4.2) -----------------------
# ``create_app`` is the application factory -- the Python successor to the legacy
# ``http.createServer(...)`` call. ``Config`` supplies the loopback-preserving
# HOST/PORT defaults (127.0.0.1:3000) that this launcher falls back to when
# resolving the bind address. Both use the absolute ``from app...`` convention
# so the import graph is unambiguous regardless of how the launcher is started.
from app import create_app
from app.config import Config


def main():
    """Build the application and start the development server.

    This is the development-time entrypoint, equivalent to ``node server.js``.
    It is exposed as the ``hello-world`` console script in ``pyproject.toml``
    (``[project.scripts] hello-world = "run:main"``) and is also invoked by the
    ``if __name__ == '__main__'`` guard below when the module is run directly.

    Behavior, step by step:

    1. **Build the app** via :func:`app.create_app`. The zero-argument call
       returns a fully-configured :class:`flask.Flask` instance with
       configuration loaded, logging initialized, and the catch-all routes,
       middleware, and defensive error handlers all registered.
    2. **Resolve the bind address** from the loaded configuration. ``HOST`` and
       ``PORT`` are read from ``app.config`` -- populated from the environment
       via :class:`app.config.Config` -- with the class attributes
       :attr:`app.config.Config.HOST` / :attr:`app.config.Config.PORT` supplied
       as explicit fallbacks so a sensible loopback default (``127.0.0.1:3000``)
       always applies even if the keys were somehow absent. ``PORT`` is coerced
       to :class:`int` because environment variables arrive as strings while
       :meth:`flask.Flask.run` requires an integer port.
    3. **Emit the startup banner** ``Server running at http://{host}:{port}/``
       through the configured ``app.logger`` at ``INFO`` level. With the default
       configuration this renders as ``Server running at http://127.0.0.1:3000/``
       -- byte-for-byte identical to the legacy ``console.log`` output
       (``server.js`` line 13), trailing slash included. The factory does not
       emit this line, so logging it here produces exactly one banner per
       development launch (AAP 0.6.3).
    4. **Start the development server** via :meth:`flask.Flask.run`, binding to
       the resolved host and port. This is a blocking call that serves requests
       until the process is interrupted (e.g. Ctrl-C), mirroring the legacy
       ``server.listen`` behavior. Whether the auto-reloader/debugger is active
       follows ``app.config['DEBUG']`` (enabled by ``DevelopmentConfig``); the
       HTTP response contract is unaffected either way.

    Returns:
        None. The call blocks inside :meth:`flask.Flask.run` for the lifetime of
        the development server and returns only after the server shuts down.
    """
    # Step 1 -- build the fully-configured application via the factory. This is
    # the Python successor to the legacy ``http.createServer(...)`` call; no
    # socket is bound yet.
    app = create_app()

    # Step 2 -- resolve the bind address from configuration. ``app.config`` was
    # populated from the environment (with the legacy 127.0.0.1:3000 defaults);
    # ``Config.HOST`` / ``Config.PORT`` are passed as explicit fallbacks so a
    # valid loopback default always applies. ``PORT`` is coerced to ``int``
    # because environment variables are strings and ``Flask.run`` needs an int.
    host = app.config.get('HOST', Config.HOST)
    port = int(app.config.get('PORT', Config.PORT))

    # Step 3 -- emit the canonical startup banner exactly once, before serving.
    # The wording (and mandatory trailing slash) matches the legacy line
    # byte-for-byte (``server.js`` line 13). %-style lazy interpolation defers
    # string formatting until the record is actually emitted.
    app.logger.info('Server running at http://%s:%s/', host, port)

    # Step 4 -- start Flask's built-in development server. This blocks, serving
    # requests until interrupted -- the parity equivalent of ``server.listen``.
    app.run(host=host, port=port)


# Standard Python entrypoint guard: invoke ``main()`` only when this module is
# executed directly (``python run.py``), never when it is imported (e.g. by the
# test suite, or when the ``hello-world`` console script resolves ``run:main``).
if __name__ == '__main__':
    main()
