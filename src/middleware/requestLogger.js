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
 * Security/privacy — query-string redaction: the `'combined'` format records the
 * full request line, which includes the request path AND its query string.
 * Although sensitive values SHOULD never be placed in URLs, a client can still
 * send them (e.g. `?token=...&password=...`), and logging those verbatim would
 * leak secrets into the access log. To prevent this, the built-in morgan `:url`
 * token is overridden below with a redacting variant: the request path is
 * preserved unchanged, and the VALUE of any query parameter whose name matches a
 * known sensitive key (token, password, secret, authorization, api_key, and
 * common variants) is replaced with `[REDACTED]`. Non-sensitive parameters are
 * still logged verbatim. The Authorization (and every other) request header is
 * not part of the `'combined'` format, so headers are never logged either.
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

// --- Sensitive query-parameter redaction -----------------------------------
// Query-parameter names whose VALUES must never be written to the access log.
// Matched case-insensitively, both as an exact name and (via the substring set
// below) as a fragment, so variants such as `access_token`, `user_password`,
// and `client_secret` are caught as well.
const SENSITIVE_EXACT = new Set([
  'token', 'password', 'passwd', 'pwd', 'secret', 'authorization', 'auth',
  'api_key', 'apikey', 'access_token', 'refresh_token', 'session', 'sessionid',
  'credential', 'credentials'
]);
const SENSITIVE_SUBSTRINGS = ['token', 'password', 'passwd', 'secret', 'apikey', 'api_key'];

// Decide whether a query-parameter name is sensitive. The comparison is done on
// the decoded, lowercased key so percent-encoded names are evaluated correctly.
const isSensitiveKey = (key) => {
  const normalized = key.toLowerCase();
  if (SENSITIVE_EXACT.has(normalized)) {
    return true;
  }
  return SENSITIVE_SUBSTRINGS.some((fragment) => normalized.includes(fragment));
};

// Return the request URL with the VALUES of any sensitive query parameters
// replaced by `[REDACTED]`. The path, the original key text, and every
// non-sensitive parameter are preserved verbatim so the access log stays
// useful. A URL with no query string is returned unchanged.
const redactUrl = (url) => {
  const queryStart = url.indexOf('?');
  if (queryStart === -1) {
    return url;
  }

  const path = url.slice(0, queryStart);
  const query = url.slice(queryStart + 1);

  const redactedQuery = query
    .split('&')
    .map((pair) => {
      const eq = pair.indexOf('=');
      const rawKey = eq === -1 ? pair : pair.slice(0, eq);
      let decodedKey;
      try {
        decodedKey = decodeURIComponent(rawKey);
      } catch (err) {
        // Malformed percent-encoding: fall back to the raw key for the check.
        decodedKey = rawKey;
      }
      if (isSensitiveKey(decodedKey)) {
        return `${rawKey}=[REDACTED]`;
      }
      return pair;
    })
    .join('&');

  return `${path}?${redactedQuery}`;
};

// Override morgan's built-in `:url` token with the redacting variant. This keeps
// the standard `'combined'` format string intact (the access-log layout is
// unchanged) while guaranteeing no sensitive query value is ever emitted. The
// default token returns `req.originalUrl || req.url`; this version mirrors that
// and then redacts.
morgan.token('url', (req) => redactUrl(req.originalUrl || req.url || ''));

// Export the configured morgan middleware function directly so that app.js can
// register it via `app.use(require('./middleware/requestLogger'))`.
module.exports = morgan('combined', { stream });
