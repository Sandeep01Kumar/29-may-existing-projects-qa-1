/**
 * Structured application logger (FR-7).
 *
 * This is the single, central logging module for the application. It replaces
 * the original server's ad-hoc console.log(...) startup message [server.js:L13]
 * with a structured, level-controlled winston logger that emits JSON lines on a
 * single console transport — a format well suited to PM2 log capture and
 * downstream aggregation (PM2 captures stdout/stderr).
 *
 * The log verbosity is sourced exclusively from the central configuration
 * module (config.LOG_LEVEL, for which the config module always supplies a safe
 * default); it is never hardcoded here, so verbosity can be tuned per
 * environment through the LOG_LEVEL variable without any code change.
 *
 * Consumed by:
 *   - server.js                       -> logger.info(...) for startup / graceful
 *                                        shutdown and logger.error(...) on errors
 *   - src/middleware/requestLogger.js -> bridges morgan HTTP access logs into
 *                                        this logger (stream.write -> logger.info)
 *   - src/middleware/errorHandler.js  -> logger.error(...) for centralized errors
 *
 * Exports a ready-to-use winston Logger INSTANCE (not a factory or class), so
 * callers can immediately invoke logger.info(...) / logger.error(...) on the
 * imported value.
 *
 * Conventions: CommonJS (require / module.exports), 2-space indentation.
 */
const winston = require('winston');
const config = require('../config');

const logger = winston.createLogger({
  level: config.LOG_LEVEL,
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [
    new winston.transports.Console()
  ]
});

module.exports = logger;
