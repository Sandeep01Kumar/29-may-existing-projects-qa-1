/**
 * Greeting routes — the NEW `GET /good-evening` endpoint (FR-3).
 *
 * This module satisfies the user's explicit request to "add another endpoint
 * that returns the response of 'Good evening'". It is implemented as a
 * self-contained `express.Router()` instance so the application's route surface
 * is decomposed into small, single-purpose modules rather than inlined into one
 * handler (AAP §0.1.3 routing decomposition, FR-4).
 *
 * Behavior is purely ADDITIVE: this router introduces a brand-new path and in
 * no way affects, replaces, or alters the preserved root endpoint owned by
 * `helloRoutes.js` (`GET /` -> `Hello, World!\n`). The two routers are siblings
 * mounted side-by-side by the aggregating root router.
 *
 * Response contract (EXACT — AAP §0.1.2, §0.7):
 *   - Method / path : GET /good-evening
 *   - Status        : 200
 *   - Body          : the literal 12 characters `Good evening`
 *                     (NO trailing newline, NO JSON wrapping, no extra whitespace)
 *   - Content-Type  : text/plain (set explicitly for a clean plain-text response,
 *                     consistent with the existing `GET /` endpoint)
 *
 * Mounting / integration:
 *   src/routes/greetingRoutes.js   (this file — owns the relative path `/good-evening`)
 *     ^ mounted by src/routes/index.js  via `router.use('/', greetingRoutes)`
 *         ^ mounted by src/app.js        via `app.use('/', routes)`
 *   Because every layer mounts at `/`, this module owns the FULL path
 *   `/good-evening`. Unknown/unmatched paths are intentionally NOT handled here;
 *   they fall through to the application-level `notFound` (404) middleware that
 *   `src/app.js` registers AFTER all routers.
 *
 * Conventions: CommonJS (require / module.exports), 2-space indentation.
 */
const express = require('express');

// Leaf router instance. This is the object exported as the module's default
// export and consumed (mounted) by the aggregating router in src/routes/index.js.
const router = express.Router();

/**
 * GET /good-evening
 *
 * Replies with the exact plain-text greeting `Good evening` at HTTP 200.
 *
 * `res.type('text/plain')` sets `Content-Type` to `text/plain; charset=utf-8`,
 * and `res.send(...)` writes the string body verbatim — Express does not append
 * a trailing newline to string responses, so the emitted body is exactly the
 * 12 characters mandated by the contract. The call chain also fixes the status
 * code at 200 explicitly so the response is unambiguous and self-documenting.
 *
 * @param {object} req - The incoming HTTP request (unused by this handler).
 * @param {object} res - The Express HTTP response used to send the reply.
 * @returns {void}
 */
router.get('/good-evening', (req, res) => {
  res.type('text/plain').status(200).send('Good evening');
});

module.exports = router;
