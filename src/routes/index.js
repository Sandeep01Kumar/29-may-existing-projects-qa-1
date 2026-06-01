/**
 * Root router aggregator (FR-4) — the single mount point for ALL application routes.
 *
 * This module composes the application's individual `express.Router()` leaf
 * modules into one mountable router and exports it for `src/app.js` to register
 * with a single `app.use('/', require('./routes'))`. It is the architectural
 * successor to the original single inline `http.createServer` request handler in
 * the root `server.js` [server.js:L6-L10], which answered EVERY request from one
 * place. That monolithic handler has been decomposed into small, single-purpose
 * route modules; this file is the seam that re-assembles them into a coherent
 * route surface (AAP §0.1.3 routing decomposition, FR-4).
 *
 * Consumer contract (verified against the planned `src/app.js`):
 *   `src/app.js` performs `const routes = require('./routes');` — which resolves
 *   to THIS file (`src/routes/index.js`) — and then `app.use('/', routes);`.
 *   Therefore the value exported here MUST be a bare `express.Router()` instance:
 *   a mountable middleware function that exposes `.use()` / `.get()`. It must NOT
 *   be a plain object, a factory function, or any other shape, or the
 *   `app.use('/', routes)` registration would fail.
 *
 * Composition strategy:
 *   Both child routers are mounted at the root path `'/'` so that each leaf
 *   module owns its COMPLETE path (no prefix stripping):
 *     - `helloRoutes`    owns `GET /`            -> `Hello, World!\n` (preserved, FR-2)
 *     - `greetingRoutes` owns `GET /good-evening` -> `Good evening`    (new, FR-3)
 *   Because the two routers expose disjoint paths (`/` vs `/good-evening`), mount
 *   order does not affect correctness; they are siblings that neither shadow nor
 *   alter one another.
 *
 * Integration / mounting chain:
 *   src/routes/helloRoutes.js  (GET /)            \
 *   src/routes/greetingRoutes.js (GET /good-evening) > mounted here at '/'
 *     ^ src/routes/index.js  (this file — the root aggregator router)
 *         ^ src/app.js        via `app.use('/', routes)`
 *
 * Deliberate non-responsibilities (owned elsewhere — do NOT add them here):
 *   - No inline route handlers: routes live exclusively in the leaf modules.
 *   - No catch-all / 404 handler: unmatched paths fall through to the
 *     application-level `notFound` (404) middleware that `src/app.js` registers
 *     AFTER all routers (`src/middleware/errorHandler.js`).
 *   - No `app.listen` / server bootstrap: that is `server.js`'s responsibility.
 *   This file contains NO business logic — it is purely a composition/aggregation
 *   module.
 *
 * Conventions: CommonJS (require / module.exports), 2-space indentation
 * (AAP §0.6.2, §0.7).
 */
const express = require('express');

// Sibling leaf route modules. Each exports a bare `express.Router()` instance as
// its default export. They are required by their exact relative paths within this
// same `src/routes/` directory.
const helloRoutes = require('./helloRoutes');
const greetingRoutes = require('./greetingRoutes');

// The root aggregator router. This is the object exported as the module's default
// export and mounted by `src/app.js` via `app.use('/', routes)`.
const router = express.Router();

// Mount each leaf router at the root path so it owns its full, un-prefixed path.
// `helloRoutes` contributes `GET /` (the preserved legacy response) and
// `greetingRoutes` contributes `GET /good-evening` (the new endpoint).
router.use('/', helloRoutes);
router.use('/', greetingRoutes);

module.exports = router;
