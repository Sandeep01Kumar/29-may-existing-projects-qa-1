/**
 * HTTP endpoint smoke tests (AAP §0.2.3, §0.5.1 Group 4, §0.5.2, §0.6.1).
 *
 * This is the project's first and only automated test file. It exercises the
 * externally observable contract of the Express application's two endpoints
 * plus its 404 behavior, using ONLY the Node.js built-in test runner
 * (`node:test`) with `node:assert` and the `supertest` HTTP assertion library.
 * No third-party test framework (Jest/Mocha/Chai) and no config file are
 * introduced — `node --test` discovers and runs this file directly, which also
 * remediates the previously broken placeholder `test` script (§1.4.3): combined
 * with the new `package.json` `"test": "node --test"`, `npm test` now runs these
 * tests and exits cleanly.
 *
 * Application under test:
 *   The Express app factory at `src/app.js` exports the fully-configured `app`
 *   via `module.exports = app` and deliberately does NOT call `app.listen`. That
 *   makes the app a bare, callable `(req, res)` request handler that `supertest`
 *   can drive in-process — supertest binds an ephemeral port internally, so the
 *   suite needs no running server, no hardcoded port, and produces no network
 *   side effects.
 *
 * Coverage (exactly three smoke assertions, one per externally visible contract):
 *   1. GET /             -> preserves the original `Hello, World!\n` response
 *                           byte-for-byte (HTTP 200, text/plain). This is the
 *                           backward-compatibility contract (FR-2) and the single
 *                           most important assertion in the file.
 *   2. GET /good-evening -> the new greeting endpoint returns `Good evening`
 *                           at HTTP 200 (FR-3).
 *   3. GET /does-not-exist -> an unmatched path returns HTTP 404, exercising the
 *                           application's `notFound` middleware.
 *
 * Conventions: CommonJS (require), 2-space indentation (matches the repo's JS
 * convention [server.js:L1]); CommonJS-only, no ES modules and no TypeScript
 * (AAP §0.6.2, §0.7).
 */
const { test } = require('node:test');
const assert = require('node:assert');
const request = require('supertest');

// The Express `app` exported by the application factory. Imported with a bare
// module specifier (no `.js` extension) per Node/CommonJS convention and passed
// straight into supertest — never started with `app.listen`.
const app = require('../src/app');

// Test 1 — Backward-compatibility contract (FR-2). The original raw-`http`
// handler [server.js:L6-L10] answered with `Hello, World!\n` (HTTP 200,
// text/plain); the migrated `GET /` route MUST reproduce that byte-for-byte,
// including the trailing newline. Content-Type is matched with a regex because
// Express emits `text/plain; charset=utf-8` — asserting the full header string
// would be brittle, so a `match` on `text/plain` is the correct, robust check.
test('GET / returns the original "Hello, World!" response (HTTP 200, text/plain)', async () => {
  const response = await request(app).get('/');

  assert.strictEqual(response.status, 200);
  assert.match(response.headers['content-type'], /text\/plain/);
  assert.strictEqual(response.text, 'Hello, World!\n');
});

// Test 2 — New greeting endpoint (FR-3). Only HTTP 200 and the exact body
// `Good evening` (no trailing newline, no punctuation) are contractually
// required, so Content-Type is intentionally NOT asserted here.
test('GET /good-evening returns the "Good evening" response (HTTP 200)', async () => {
  const response = await request(app).get('/good-evening');

  assert.strictEqual(response.status, 200);
  assert.strictEqual(response.text, 'Good evening');
});

// Test 3 — Unknown route exercises the `notFound` middleware. Only the 404
// status is part of the contract; the error-body shape is not fixed, so it is
// intentionally left unasserted.
test('GET /does-not-exist returns HTTP 404 for an unknown route', async () => {
  const response = await request(app).get('/does-not-exist');

  assert.strictEqual(response.status, 404);
});
