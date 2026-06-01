/**
 * HTTP request access-logging middleware (FR-7).
 *
 * This module produces the application's HTTP access log by bridging `morgan`
 * (an HTTP request logger middleware) into the project's central `winston`
 * application logger. Rather than letting `morgan` write directly to
 * `process.stdout`, every formatted access-log line is funneled through the
 * shared `winston` logger so that ALL application output — startup messages,
 * HTTP access lines, and errors — flows through a single, structured logging
 * pipeline. This is the well-established `stream.write` bridge pattern and is
 * what makes the output suitable for PM2 log capture and downstream
 * aggregation (PM2 captures stdout/stderr).
 *
 * Format: the `'combined'` predefined format is used — the standard Apache
 * combined access log (remote address, user, timestamp, request line, status,
 * response size, referrer, and user-agent).
 *
 * Security/privacy constraint: the `'combined'` format records the full request
 * line, which includes the request path AND its query string. The service's
 * endpoints accept no secret or sensitive inputs, and by convention secrets and
 * other sensitive values MUST NOT be placed in URLs or query strings — such
 * values belong in request bodies or headers, which this access log does not
 * capture. Honoring this convention keeps the access log free of sensitive data
 * without any per-request redaction.
 *
 * Bridge detail: `morgan` appends a trailing newline (`\n`) to every line it
 * emits. The `winston` logger adds its own line break when it writes a record,
 * so the incoming message is `.trim()`-ed before being handed to
 * `logger.info(...)`. Without this trim, the structured log output would
 * contain double newlines / blank lines.
 *
 * Consumed by:
 *   - src/app.js -> app.use(require('./middleware/requestLogger'));
 *                   registered AFTER express.json() and BEFORE the routers.
 *
 * Because of that consumption pattern, the module's default export is the
 * configured `morgan` middleware function itself (a single callable with the
 * Express `(req, res, next)` signature) — NOT an object and NOT a factory.
 *
 * Conventions: CommonJS (require / module.exports), 2-space indentation.
 */
const morgan = require('morgan');
const logger = require('../utils/logger');

// Bridge morgan's HTTP access logs into the winston application logger.
// `.trim()` removes morgan's trailing newline so winston does not emit
// double newlines / blank lines in the structured output.
const stream = {
  write: (message) => logger.info(message.trim())
};

// Export the configured morgan middleware function directly so that app.js can
// register it via `app.use(require('./middleware/requestLogger'))`.
module.exports = morgan('combined', { stream });
