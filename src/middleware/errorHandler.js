/**
 * 404 + centralized error-handling middleware (FR-5).
 *
 * The original server was a single raw `http` handler that returned
 * `Hello, World!\n` for EVERY path and method [server.js:L6-L10], so it had no
 * concept of an "unmatched route" (404) and no place to funnel errors. As part
 * of the Express refactor this module introduces, for the first time, the two
 * cross-cutting handlers that close out the request pipeline:
 *
 *   1. `notFound`     — terminal middleware for requests that matched no route.
 *                       Registered AFTER all routers, so it only runs when
 *                       nothing else handled the request, and replies 404.
 *   2. `errorHandler` — the single, centralized error funnel. Any error passed
 *                       to `next(err)` — or thrown / rejected inside a route
 *                       handler (Express 5 forwards rejected promises and async
 *                       errors here automatically) — lands in this one place,
 *                       where it is logged via the shared `winston` logger and
 *                       translated into a JSON error response.
 *
 * Both handlers emit a consistent `{ error: <message> }` JSON body so the API
 * surface stays predictable for every failure mode.
 *
 * Express recognises error-handling middleware EXCLUSIVELY by its arity: a
 * function declared with exactly four parameters `(err, req, res, next)` is
 * treated as an error handler, while any other arity is treated as ordinary
 * middleware. For that reason `errorHandler` MUST keep all four parameters even
 * though `next` is unused — dropping it would silently break error routing.
 *
 * Consumed by:
 *   - src/app.js -> const { notFound, errorHandler } = require('./middleware/errorHandler');
 *                   registered LAST, in this order:
 *                     app.use(notFound);      // after every router
 *                     app.use(errorHandler);  // very last, so all errors reach it
 *
 * This module imports nothing except the shared application logger; the
 * `req`/`res`/`next` arguments are supplied by Express at call time, so the
 * framework object itself is never required here.
 *
 * Conventions: CommonJS (require / module.exports), 2-space indentation.
 */
const logger = require('../utils/logger');

/**
 * 404 handler for unmatched routes.
 *
 * Registered by `src/app.js` AFTER all routers (`app.use(notFound)`), this only
 * fires when no route matched the incoming request. It terminates the request
 * with a 404 and a consistent JSON body. No logging is performed here: a 404 on
 * an unknown path is normal traffic and is already captured by the HTTP request
 * logger (morgan -> winston), so logging again would only add noise.
 *
 * The `next` parameter is part of the standard middleware signature and is left
 * intentionally unused — this handler terminates the response and does not pass
 * control onward.
 *
 * @param {import('express').Request}  req  Incoming Express request.
 * @param {import('express').Response} res  Express response used to reply 404.
 * @param {import('express').NextFunction} next  Unused; present for signature parity.
 * @returns {void}
 */
function notFound(req, res, next) {
  res.status(404).json({ error: 'Not Found' });
}

/**
 * Centralized error handler — the single funnel for ALL pipeline errors.
 *
 * The four-parameter signature `(err, req, res, next)` is MANDATORY: Express
 * identifies error-handling middleware solely by an arity of 4. The trailing
 * `next` is intentionally unused (kept only to preserve the arity that Express
 * requires), hence the eslint-disable directive.
 *
 * Behavior:
 *   1. Log the failure through the shared `winston` logger FIRST so nothing is
 *      lost even if writing the response fails. The lookup is defensive because
 *      `err` may be a proper Error (use `.stack`), a plain object with only a
 *      `.message`, or even a primitive string (fall back to `String(err)`).
 *   2. Derive the HTTP status from the error when it carries one
 *      (`err.status` or `err.statusCode`, as set by libraries such as
 *      http-errors), defaulting to 500 for unclassified failures.
 *   3. Respond with that status and a consistent `{ error: <message> }` JSON
 *      body, mirroring the shape used by `notFound`. Only the message is
 *      exposed; internal details such as the stack are logged but never sent to
 *      the client.
 *
 * @param {*} err  The error forwarded by Express (Error, object, or string).
 * @param {import('express').Request}  req  Incoming Express request.
 * @param {import('express').Response} res  Express response used to reply.
 * @param {import('express').NextFunction} next  Unused; required for arity 4.
 * @returns {void}
 */
function errorHandler(err, req, res, next) { // eslint-disable-line no-unused-vars
  logger.error(err.stack || err.message || String(err));
  const status = err.status || err.statusCode || 500;
  res.status(status).json({ error: err.message || 'Internal Server Error' });
}

module.exports = { notFound, errorHandler };
