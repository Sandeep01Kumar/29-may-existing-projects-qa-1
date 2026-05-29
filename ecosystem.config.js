/**
 * ecosystem.config.js — PM2 process definition for the "hello_world" Flask service.
 *
 * ---------------------------------------------------------------------------
 * WHAT THIS FILE IS
 * ---------------------------------------------------------------------------
 * This is a PM2 "ecosystem" file (CommonJS — PM2 `require()`s it and reads the
 * exported object). It fulfils the user rule's mandate to "prepare for production
 * deployment with PM2" (Technical Specification AAP 0.7.2).
 *
 * The prompt mandates a Python 3 / Flask target, while the rule names the
 * Node-native process manager PM2. Those two facts are reconciled exactly as
 * prescribed in AAP 0.6.5 (PM2-for-Python Operational Details): PM2 does NOT run
 * a Node script here — instead it supervises a **Gunicorn** WSGI server process,
 * and Gunicorn in turn serves the Flask application object exposed by `wsgi.py`
 * as the import target `wsgi:app`.
 *
 * The mechanism that makes PM2 supervise a non-Node binary is `interpreter: 'none'`
 * (see the field comment below). Gunicorn performs the actual request serving;
 * PM2 layers on restart-on-crash, stdout/stderr log capture, and (via the
 * operational commands `pm2 startup` + `pm2 save`) boot persistence.
 *
 * ---------------------------------------------------------------------------
 * HOW TO USE
 * ---------------------------------------------------------------------------
 *   Start (from the repository root, with the virtualenv + deps installed):
 *       pm2 start ecosystem.config.js
 *   Inspect / follow logs / stop:
 *       pm2 list
 *       pm2 logs flask-hello-world
 *       pm2 stop flask-hello-world
 *   Persist across reboots (operational, not encoded in this file):
 *       pm2 startup      # prints the OS-specific boot command to run once
 *       pm2 save         # snapshots the current process list for resurrection
 *
 * ---------------------------------------------------------------------------
 * NOTES
 * ---------------------------------------------------------------------------
 * - PM2 is an OPERATIONAL tool installed globally (`npm install -g pm2`). It is
 *   deliberately NOT a project dependency and therefore does NOT appear in
 *   requirements.txt (AAP 0.5.1).
 * - There is NO legacy source equivalent for this file; it is created net-new
 *   (AAP 0.4.1 marks it "— no source equivalent").
 * - The default bind below (127.0.0.1:3000) preserves the legacy Node server's
 *   loopback-only binding (server.js `hostname`/`port`). To expose the service
 *   beyond loopback in production, override `HOST` (e.g. HOST=0.0.0.0) and/or
 *   `PORT` in the environment — the default encoded here is intentionally left
 *   on loopback to match the original behaviour byte-for-byte.
 */

module.exports = {
  apps: [
    {
      // PM2 process name — how the app is referenced by `pm2 <cmd> flask-hello-world`.
      name: 'flask-hello-world',

      // The binary PM2 launches. Points at the Gunicorn executable installed
      // inside the project virtualenv (created by the setup step). Relative to
      // `cwd` (the repository root), so it resolves to
      // <repo>/venv/bin/gunicorn.
      script: './venv/bin/gunicorn',

      // Arguments passed verbatim to the Gunicorn binary — the BARE form
      // mandated by AAP 0.6.5 (no `-c` flag):
      //   wsgi:app            -> import the `app` object from wsgi.py (the Flask
      //                          WSGI callable produced by create_app()).
      //   -b 127.0.0.1:3000   -> bind loopback interface, port 3000 (legacy default).
      //   -w 2                -> 2 sync worker processes (kept small for this
      //                          stateless fixture, per AAP 0.6.5).
      //
      // Startup banner: the legacy line `Server running at http://127.0.0.1:3000/`
      // is emitted by the `on_starting` master-process hook in `gunicorn.conf.py`,
      // which Gunicorn AUTO-LOADS from the working directory (`cwd` below = repo
      // root) precisely because no `-c` flag is supplied — `./gunicorn.conf.py` is
      // Gunicorn's documented default config path. The hook fires exactly once in
      // the arbiter, before any worker forks (AAP 0.6.3). The explicit
      // `gunicorn -c wsgi.py wsgi:app` form (whose hook lives in wsgi.py) remains
      // supported as a fallback but is intentionally not used here, so the banner
      // is emitted by exactly one hook and never duplicated.
      args: 'wsgi:app -b 127.0.0.1:3000 -w 2',

      // CRITICAL: tells PM2 to exec `script` DIRECTLY as a standalone binary
      // rather than running it through the Node.js interpreter. This is the
      // documented mechanism (AAP 0.6.5) for supervising a non-Node process
      // (here, the Python Gunicorn server) with PM2. Removing this would make
      // PM2 try to parse the Gunicorn launcher as JavaScript and fail.
      interpreter: 'none',

      // Working directory for the spawned process. `__dirname` is the directory
      // containing this config file (the repository root), which guarantees that
      // both `./venv/bin/gunicorn` and the `wsgi:app` import resolve correctly
      // regardless of where `pm2 start` is invoked from.
      cwd: __dirname,

      // Environment exported to the Gunicorn/Flask process. These mirror the
      // keys documented in .env.example. `FLASK_ENV` is 'production' here because
      // this ecosystem file is the PRODUCTION deployment descriptor (the local
      // .env default of 'development' is for the dev launcher, not for PM2).
      // HOST/PORT default to the legacy loopback binding; override HOST=0.0.0.0
      // in the environment to expose the service externally.
      env: {
        HOST: '127.0.0.1',
        PORT: '3000',
        LOG_LEVEL: 'INFO',
        FLASK_ENV: 'production',
      },
    },
  ],
};
