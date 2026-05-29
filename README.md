# hello_world

A minimal **"Hello, World!"** HTTP service implemented in **Python 3** with the **Flask** framework. It is a faithful, behavior-preserving rewrite of the original Node.js implementation: every request — regardless of HTTP method or path — receives the exact same plain-text response, byte-for-byte identical to the legacy server.

- **Version:** `1.0.0`
- **Author:** `hxu`
- **License:** `MIT`

---

## Overview

This project was migrated from a single-file Node.js HTTP server (built on the Node core `http` module) to a production-grade Python 3 Flask application. The migration preserves the original observable behavior exactly while introducing a modular, maintainable structure:

- **Routing** via a Flask Blueprint (a universal catch-all route).
- **Middleware** via `before_request` / `after_request` hooks (request logging and content-type enforcement).
- **Environment configuration** via `python-dotenv` and class-based configuration objects.
- **Logging** via the Python standard `logging` module.
- **Production deployment** via a Gunicorn WSGI server supervised by PM2.

> The public HTTP contract (status, body, and `Content-Type`) is unchanged from the original Node.js server. Only the implementation language and internal structure differ.

---

## HTTP Contract (behavioral parity)

**Every** request — any HTTP method, any path — returns the identical response:

| Property | Value |
|----------|-------|
| Status code | `200` |
| `Content-Type` | `text/plain` (no `charset` suffix) |
| Response body | `Hello, World!\n` (14 bytes, including the trailing newline) |
| `Content-Length` | `14` |
| Accepted methods | All — `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS` |
| Accepted paths | Any — `/`, `/any/random/path`, … (universal catch-all) |

This contract is **byte-for-byte identical** to the original Node.js server; the migration preserves behavior exactly.

Example request and response:

```bash
$ curl -i http://127.0.0.1:3000/any/path
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Length: 14

Hello, World!
```

---

## Technology Stack

| Component | Version | Role |
|-----------|---------|------|
| Python | `>= 3.9` | Language runtime |
| Flask | `3.1.3` | Web framework (application, routing, `Response`) |
| Gunicorn | `26.0.0` | Production WSGI server |
| python-dotenv | `1.2.2` | Loads `.env` into the environment |
| pytest | `9.0.3` | Test runner (development dependency) |
| PM2 | global | Production process manager (supervises Gunicorn) |

Direct runtime dependencies (`Flask`, `gunicorn`, `python-dotenv`) are pinned in `requirements.txt`. `pytest` is a development-only dependency. PM2 is an operational tool installed globally via npm — it is **not** a Python dependency.

---

## Project Structure

```text
hello_world/
├── app/                     # Application package
│   ├── __init__.py          # create_app() application factory
│   ├── config.py            # Env-driven Config classes (HOST / PORT / LOG_LEVEL)
│   ├── routes.py            # Blueprint with the universal catch-all route
│   ├── middleware.py        # before_request / after_request hooks
│   └── logging_config.py    # logging setup + startup-line emission
├── tests/
│   └── test_app.py          # pytest behavioral parity suite
├── wsgi.py                  # WSGI entrypoint (exposes `app` for Gunicorn / PM2)
├── run.py                   # Development launcher (parity with `node server.js`)
├── requirements.txt         # Pinned runtime dependencies
├── pyproject.toml           # Python packaging metadata (name, version, license)
├── ecosystem.config.js      # PM2 process definition (supervises Gunicorn)
├── .env.example             # Documented environment-variable template
├── .env                     # Local environment values (git-ignored)
├── .gitignore               # Ignores venv/, __pycache__/, *.pyc, .env
└── README.md                # This file
```

---

## Installation

1. **Create and activate a virtual environment.**

   POSIX (Linux / macOS):

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

   Windows:

   ```bat
   python -m venv venv
   venv\Scripts\activate
   ```

2. **Install the runtime dependencies.**

   ```bash
   pip install -r requirements.txt
   ```

3. **Create your local environment file** from the template:

   ```bash
   cp .env.example .env
   ```

---

## Running — Development

Start the development server with the dev launcher (the parity equivalent of `node server.js`):

```bash
python run.py
```

The service starts on `http://127.0.0.1:3000/` and logs:

```text
Server running at http://127.0.0.1:3000/
```

Alternatively, run it through the Flask CLI. Flask's `run` command binds to host `127.0.0.1` and port **`5000`** by default, so pass explicit `--host` / `--port` flags to preserve the legacy `127.0.0.1:3000` bind:

```bash
flask --app wsgi run --host 127.0.0.1 --port 3000
# or, equivalently:
FLASK_APP=wsgi flask run --host 127.0.0.1 --port 3000
```

The Flask CLI also honors its own `FLASK_RUN_HOST` / `FLASK_RUN_PORT` environment variables, so you can set those instead of passing flags:

```bash
FLASK_RUN_HOST=127.0.0.1 FLASK_RUN_PORT=3000 flask --app wsgi run
```

After an editable install (`pip install -e .`), the packaged console-script entrypoint is also available:

```bash
hello-world
```

---

## Running — Production

Serve the WSGI application directly with Gunicorn. The leading `-c wsgi.py` loads `wsgi.py` as Gunicorn's configuration file, which activates its `on_starting` master-process hook so the startup line is logged exactly once (in the arbiter, before the workers fork):

```bash
gunicorn -c wsgi.py wsgi:app -b 127.0.0.1:3000 -w 2
```

On startup this logs the same line as the development launcher:

```text
Server running at http://127.0.0.1:3000/
```

Or supervise Gunicorn with **PM2** (per the production-deployment requirement). PM2 is installed globally and runs the Gunicorn binary directly via `interpreter: 'none'`:

```bash
# Install PM2 once, globally (operational tool — not a Python dependency)
npm install -g pm2

# Start the service (PM2 process name: flask-hello-world)
pm2 start ecosystem.config.js

# Inspect, follow logs, and stop
pm2 list
pm2 logs flask-hello-world
pm2 stop flask-hello-world

# Persist across reboots
pm2 startup
pm2 save
```

PM2 supervises the Gunicorn process defined in `ecosystem.config.js`, providing restart-on-crash, log capture, and boot persistence; Gunicorn performs the actual request serving.

---

## Environment Configuration

Configuration is sourced from environment variables, loaded from `.env` via `python-dotenv`. The defaults preserve the legacy loopback-only binding.

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `127.0.0.1` | Interface to bind. Set to `0.0.0.0` to expose the service beyond loopback in production. |
| `PORT` | `3000` | TCP port to listen on. |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `FLASK_ENV` | `development` | Flask environment (`development` or `production`). |

`.env` is **git-ignored** because it holds machine-local values; commit changes to `.env.example` instead. The PM2 production descriptor (`ecosystem.config.js`) sets `FLASK_ENV=production`.

---

## Testing

The behavioral parity suite is written with **pytest**. Install the test dependency and run it:

```bash
pip install pytest==9.0.3
# or install the project together with its development extras:
pip install -e '.[dev]'

pytest
```

The tests assert the full HTTP contract:

- status `200`,
- response body `Hello, World!\n`,
- `Content-Type: text/plain` (no `charset` suffix),
- `Content-Length: 14`, and
- catch-all behavior across HTTP methods and paths.

This real test suite replaces the legacy placeholder npm test, which always exited with code `1`.

---

## License

Released under the **MIT** License. Author: **hxu**.
