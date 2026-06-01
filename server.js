/**
 * Process entry point — Express application bootstrap.
 *
 * (AAP §0.4.1, §0.5.1 Group 1 [MODIFY], §0.5.2)
 *
 * This file is the architectural successor to the original raw-`http` server
 * [server.js:L1-L14], which created an `http.Server` with a single inline
 * handler that answered EVERY request with `Hello, World!\n`. That monolithic
 * design has been decomposed: request handling now lives in dedicated router
 * modules under `src/routes/`, cross-cutting concerns live in `src/middleware/`,
 * and the fully-assembled Express application is built and exported by the
 * application factory `src/app.js`. The built-in `http` module is therefore no
 * longer imported here.
 *
 * The responsibility of THIS file is deliberately narrow — it is a *thin
 * bootstrap* that wires the process together and nothing more:
 *   1. Load configuration   (which loads `.env` via dotenv, FIRST of all)
 *   2. Initialize the logger (winston, level sourced from config.LOG_LEVEL)
 *   3. Import the Express app (already configured; listen() is NOT called there)
 *   4. Bind the network socket via `app.listen(PORT, HOST, ...)`
 *   5. Register graceful-shutdown + crash-safety handlers for production (PM2)
 *
 * Why the app is imported rather than built here: keeping `app` separate from
 * the listening bootstrap makes the application independently testable —
 * `tests/endpoints.test.js` drives the exported `app` in-process via `supertest`
 * without binding a real network socket.
 *
 * Initialization ORDER MATTERS (see the numbered requires below): `./src/config`
 * MUST be required FIRST so dotenv populates `process.env` before any other
 * module (the logger, the app, or the middleware) reads an environment variable.
 *
 * Process lifecycle: this is the file referenced by `package.json` "main" and by
 * `ecosystem.config.js` (`script: 'server.js'`); PM2 launches it, captures its
 * stdout/stderr (where winston writes), and restarts it if it exits non-zero.
 *
 * Conventions: CommonJS (require / module.exports), 2-space indentation
 * (AAP §0.6.2, §0.7). No ES modules, no TypeScript.
 */

// 1. Configuration FIRST. Requiring this module triggers `dotenv.config()` at
//    load time, populating `process.env` from a local `.env` BEFORE any other
//    module reads an environment variable. It exposes the four defaulted values
//    (PORT, HOST, NODE_ENV, LOG_LEVEL); PORT/HOST are the bind target below.
const config = require('./src/config');

// 2. Logger. The shared winston application logger; its verbosity derives from
//    config.LOG_LEVEL. This replaces the original ad-hoc `console.log` startup
//    message [server.js:L13] with structured, level-controlled logging suitable
//    for PM2 log capture.
const logger = require('./src/utils/logger');

// 3. Express application. The fully-configured `app` (body parsing, request
//    logging, mounted routers, 404 + centralized error handling). `listen()` is
//    intentionally NOT called inside `src/app.js`, so this bootstrap owns it.
const app = require('./src/app');

// Bind the HTTP listener. This preserves the original
// `listen(port, hostname, callback)` contract [server.js:L12-L14], now sourcing
// the port and host from configuration (defaults 3000 / 127.0.0.1) so they are
// overridable per environment without code changes. The startup line is emitted
// through winston (replacing the legacy console.log) while keeping the same
// human-readable URL text.
const server = app.listen(config.PORT, config.HOST, () => {
  logger.info(`Server running at http://${config.HOST}:${config.PORT}/`);
});

/**
 * Gracefully shut the server down in response to a termination signal.
 *
 * Stops accepting new connections and waits for in-flight requests to drain
 * (`server.close`), then exits with code 0 to signal a clean shutdown. PM2 sends
 * SIGINT/SIGTERM on stop/reload/restart (and a terminal delivers SIGINT on
 * Ctrl+C), so honoring these signals lets the process manager cycle the app
 * without dropping in-flight work.
 *
 * @param {string} signal - The received signal name (e.g. 'SIGTERM', 'SIGINT').
 * @returns {void}
 */
const shutdown = (signal) => {
  logger.info(`${signal} received, shutting down gracefully`);
  server.close(() => {
    logger.info('Server closed');
    process.exit(0);
  });
};

// Production process-lifecycle signals. PM2 (and Ctrl+C in a terminal) deliver
// these; both route through the same graceful-shutdown path above.
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

// Crash safety. Log the fatal condition through winston and exit non-zero so the
// process manager (PM2) detects the failure and restarts a clean instance rather
// than leaving the process in an undefined state.
process.on('uncaughtException', (err) => {
  logger.error(`Uncaught exception: ${err && err.stack ? err.stack : err}`);
  process.exit(1);
});

process.on('unhandledRejection', (reason) => {
  logger.error(`Unhandled rejection: ${reason && reason.stack ? reason.stack : reason}`);
  process.exit(1);
});
