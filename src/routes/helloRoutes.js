/**
 * Hello routes — the PRESERVED root `GET /` endpoint (FR-2).
 *
 * This module is the architectural successor to the single inline
 * `http.createServer` request handler in the original root `server.js`
 * [server.js:L6-L10], which answered EVERY request with `Hello, World!\n`.
 * That exact behavior now lives here as a dedicated Express route for `GET /`,
 * decomposing the application's route surface into small, single-purpose
 * `express.Router()` modules rather than one inline handler (AAP §0.1.3 routing
 * decomposition, FR-4).
 *
 * Backward compatibility is NON-NEGOTIABLE (AAP §0.1.2, §0.7): the externally
 * observable contract of `GET /` must remain byte-for-byte identical after the
 * migration from the raw `http` server to Express. This is the single most
 * important correctness requirement for this file.
 *
 * Response contract (EXACT — reproduces server.js L6-L10 byte-for-byte):
 *   - Method / path : GET /
 *   - Status        : 200
 *   - Body          : the literal 14 characters `Hello, World!\n` INCLUDING the
 *                     trailing newline (`\n`). The newline is part of the
 *                     original response (`res.end('Hello, World!\n')`) and MUST
 *                     be preserved — do not omit it, do not add extra
 *                     whitespace, and do not JSON-wrap the body.
 *   - Content-Type  : text/plain (matches the original
 *                     `res.setHeader('Content-Type', 'text/plain')`)
 *
 * Relationship to the new endpoint: this router carries ONLY the preserved
 * legacy behavior. The additive `GET /good-evening` endpoint lives in the
 * sibling module `greetingRoutes.js`; the two routers are mounted side-by-side
 * and neither one affects, replaces, or alters the other.
 *
 * Mounting / integration:
 *   src/routes/helloRoutes.js   (this file — owns the relative path `/`)
 *     ^ mounted by src/routes/index.js  via `router.use('/', helloRoutes)`
 *         ^ mounted by src/app.js        via `app.use('/', routes)`
 *   Because every layer mounts at `/`, this module owns the FULL path `/`
 *   (no prefix stripping). Unknown/unmatched paths are intentionally NOT handled
 *   here; they fall through to the application-level `notFound` (404) middleware
 *   that `src/app.js` registers AFTER all routers (src/middleware/errorHandler.js).
 *
 * Conventions: CommonJS (require / module.exports), 2-space indentation.
 */
const express = require('express');

// Leaf router instance. This is the object exported as the module's default
// export and consumed (mounted) by the aggregating router in src/routes/index.js.
const router = express.Router();

/**
 * GET /
 *
 * Replies with the exact plain-text body `Hello, World!\n` at HTTP 200,
 * reproducing the original raw-`http` handler [server.js:L6-L10] byte-for-byte.
 *
 * `res.type('text/plain')` sets `Content-Type` to `text/plain; charset=utf-8`,
 * `res.status(200)` fixes the status code explicitly, and `res.send(...)` writes
 * the string body verbatim. Express neither appends to nor strips characters
 * from a string response, so the emitted body is exactly `Hello, World!\n` —
 * the trailing newline is included intentionally as the final byte to match the
 * legacy contract.
 *
 * @param {object} req - The incoming HTTP request (unused by this handler).
 * @param {object} res - The Express HTTP response used to send the reply.
 * @returns {void}
 */
router.get('/', (req, res) => {
  res.type('text/plain').status(200).send('Hello, World!\n');
});

module.exports = router;
