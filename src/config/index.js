/**
 * Central application configuration (FR-6).
 *
 * This is the most foundational module in the `src/` tree. It is required
 * FIRST by `server.js` (the process entry point), which guarantees that any
 * environment variables declared in a local `.env` file are loaded into
 * `process.env` before any other module (logger, app factory, middleware)
 * reads them.
 *
 * `require('dotenv').config()` is intentionally invoked here, at module load
 * time, and MUST remain the very first executable statement in this file. This
 * single, process-wide call is the one intentional place where `.env` is
 * parsed, making those overrides available to every downstream consumer.
 *
 * The exported object exposes exactly four values, each sourced from
 * `process.env` with a safe default. The defaults preserve the original
 * server's previously hard-coded bind values (`127.0.0.1:3000`) while making
 * them overridable via the environment without any code changes:
 *
 *   - PORT      HTTP listen port            (default: 3000)
 *   - HOST      HTTP listen host/interface  (default: '127.0.0.1')
 *   - NODE_ENV  Runtime environment         (default: 'development')
 *   - LOG_LEVEL winston log verbosity       (default: 'info')
 *
 * Consumed by:
 *   - server.js           -> config.PORT, config.HOST (app.listen)
 *   - src/utils/logger.js -> config.LOG_LEVEL (winston level)
 *
 * Conventions: CommonJS (require / module.exports), 2-space indentation.
 */
require('dotenv').config();

module.exports = {
  PORT: process.env.PORT || 3000,
  HOST: process.env.HOST || '127.0.0.1',
  NODE_ENV: process.env.NODE_ENV || 'development',
  LOG_LEVEL: process.env.LOG_LEVEL || 'info'
};
