/**
 * Express application factory — the central wiring point of the service
 * (AAP §0.2.3, §0.4.1, §0.5.1 Group 1, §0.5.2).
 *
 * This module builds and exports a fully-configured Express `app`. It is the
 * architectural successor to the server-construction portion of the original
 * root `server.js` [server.js:L1-L14], whose single inline `http.createServer`
 * handler answered EVERY path with `Hello, World!\n`. That monolithic behavior
 * has been decomposed: request handling now lives in dedicated router modules
 * (mounted here), and the raw `http` server creation is replaced by the Express
 * `app`. Consequently, NO `http` module is imported in this file.
 *
 * Separation of concerns — the network bind is deliberately NOT performed here:
 *   This factory assembles the application (middleware + routes + error
 *   handling) and exports the bare `app` object. The socket-binding bootstrap
 *   responsibility (loading config, initializing the logger, binding the port,
 *   graceful shutdown) belongs to the root `server.js`. Exporting the app
 *   WITHOUT binding a network socket is what makes the application independently
 *   exercisable by automated tests, which drive it in-process via `supertest`
 *   without binding a real network socket.
 *
 * Consumer contract (MUST be honored):
 *   - server.js                 -> `const app = require('./src/app');`
 *                                  then binds it to config.PORT / config.HOST
 *   - tests/endpoints.test.js    -> `const app = require('../src/app');`
 *                                  then drives it with `supertest`
 *   Therefore the module's default export MUST be the bare Express `app` — a
 *   callable `(req, res)` request handler that also exposes network-bind /
 *   `.use()` — and that network bind MUST NOT be invoked anywhere in this file.
 *
 * Middleware registration ORDER is functionally significant and fixed:
 *   1. express.json()  — parse JSON request bodies before any handler reads them
 *   2. requestLogger   — morgan HTTP access logging streamed into winston
 *   3. method guard    — enforce the GET-only contract: HEAD and OPTIONS (which
 *                        Express would otherwise auto-answer with 200) are
 *                        funneled to notFound so every non-GET method returns 404
 *   4. routes ('/')    — the aggregated root router (GET /, GET /good-evening)
 *   5. notFound        — 404 for any path that matched no route (after routers)
 *   6. errorHandler    — centralized 4-arg error funnel, registered LAST so
 *                        Express routes all errors to it (Express 5 also
 *                        auto-forwards rejected promises / async errors here)
 *
 * Deliberate non-responsibilities (owned elsewhere — intentionally absent here
 * per AAP §0.3.1, §0.6.2):
 *   - No network bind / server bootstrap (owned by `server.js`).
 *   - No inline route handlers (all routing lives under `src/routes/`).
 *   - No optional hardening middleware (helmet, compression, CORS) — explicitly
 *     out of scope.
 *
 * Conventions: CommonJS (require / module.exports), 2-space indentation
 * (AAP §0.6.2, §0.7); uses only `express` (declared `express@^5.2.1`).
 */
const express = require('express');

// HTTP access-logging middleware: a single morgan('combined') middleware
// function whose output is streamed into the shared winston logger. Its default
// export is the configured middleware function itself.
const requestLogger = require('./middleware/requestLogger');

// Aggregated root router (resolves to `src/routes/index.js`). Its default export
// is an `express.Router()` instance composing `helloRoutes` (GET /) and
// `greetingRoutes` (GET /good-evening), mounted below at '/'.
const routes = require('./routes');

// Centralized request-pipeline terminators. `notFound` (404 for unmatched
// routes) and `errorHandler` (the 4-argument `(err, req, res, next)` error
// funnel) are the two named exports of the error-handling middleware module.
const { notFound, errorHandler } = require('./middleware/errorHandler');

// Instantiate the Express application. An Express `app` is itself a callable
// request handler (a function), which is exactly the shape consumers require.
const app = express();

// 1. Body parsing — register first so downstream middleware and route handlers
//    can rely on `req.body` being populated for JSON payloads. An explicit
//    100kb body-size limit caps request-body memory use and reduces
//    large-payload DoS exposure instead of relying on the framework default.
app.use(express.json({ limit: '100kb' }));

// 2. HTTP access logging (morgan -> winston) — register after body parsing and
//    before the routers so every incoming request is logged once, up front.
app.use(requestLogger);

// 3. Method guard — enforce the application's GET-only contract. Every route in
//    this service is GET-only (GET / and GET /good-evening), so any other HTTP
//    method must be treated as unmatched and answered with 404. Express would
//    otherwise auto-handle two of those methods: it answers HEAD by running the
//    matching GET handler (200, no body) and answers OPTIONS with a 200 + `Allow`
//    header. Intercepting HEAD and OPTIONS here — AFTER the access logger (so
//    they are still logged) and BEFORE the routers (so the router's automatic
//    handling never runs) — and forwarding them to the shared `notFound` handler
//    makes them return a consistent 404, matching POST/PUT/PATCH/DELETE (which
//    already fall through to notFound). ONLY HEAD and OPTIONS are intercepted;
//    every other method proceeds unchanged, so the body parser registered above
//    still governs POST payload handling (malformed-JSON 400, oversized 413).
app.use((req, res, next) => {
  if (req.method === 'HEAD' || req.method === 'OPTIONS') {
    return notFound(req, res, next);
  }
  return next();
});

// 4. Application routes — mount the aggregated root router at '/'. This exposes
//    the preserved `GET /` (-> `Hello, World!\n`) and the new
//    `GET /good-evening` (-> `Good evening`), replacing the original single
//    inline handler that answered all paths [server.js:L6-L10].
app.use('/', routes);

// 5. 404 handler — runs only when no route above matched the request, returning
//    a consistent 404 response for unknown paths.
app.use(notFound);

// 6. Centralized error handler — MUST be registered LAST. Express recognizes
//    error-handling middleware exclusively by its 4-argument arity, so this is
//    where every `next(err)` and (in Express 5) every rejected promise / thrown
//    async error is funneled, logged, and translated into an error response.
app.use(errorHandler);

// Export the configured application WITHOUT binding a network socket. `server.js`
// owns the network bind; tests consume this `app` directly via `supertest`.
module.exports = app;
