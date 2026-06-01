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
const express = require('express');

// The Express `app` exported by the application factory. Imported with a bare
// module specifier (no `.js` extension) per Node/CommonJS convention and passed
// straight into supertest — never started with `app.listen`.
const app = require('../src/app');

// The centralized error handler, imported directly for the security regression
// tests below. The production `app` deliberately has no error-producing route,
// so those tests build throwaway in-process Express apps that wire `errorHandler`
// exactly as `src/app.js` does (registered LAST) and drive them with supertest.
const { errorHandler } = require('../src/middleware/errorHandler');

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

// Test 4 — SECURITY regression (information disclosure). When a route throws an
// unexpected server-side error, the centralized `errorHandler` MUST respond 500
// with a FIXED, generic body and MUST NOT echo the internal error message back
// to the client (which could leak stack fragments, database/dependency errors,
// file paths, or other operational data). The production `app` has no
// error-producing route, so a throwaway Express app is built in-process and
// wired exactly like `src/app.js` registers the real handler (mounted LAST),
// then driven with supertest. This proves the 500 internals are not returned.
test('errorHandler returns a generic 500 body and never leaks internal error details', async () => {
  const sensitive = 'sensitive internal database failure on shard 7';
  const failingApp = express();
  failingApp.get('/boom', (req, res, next) => {
    next(new Error(sensitive));
  });
  failingApp.use(errorHandler);

  const response = await request(failingApp).get('/boom');

  assert.strictEqual(response.status, 500);
  assert.deepStrictEqual(response.body, { error: 'Internal Server Error' });
  assert.ok(
    !response.text.includes(sensitive),
    'the internal error message must not appear anywhere in the 500 response body'
  );
});

// Test 5 — Controlled client errors (4xx) still surface their intentional, safe
// message, so legitimate API error feedback is preserved while only server-side
// (5xx) internals are suppressed. This guards against the fix over-correcting
// into a blanket message suppression.
test('errorHandler passes through controlled 4xx client error messages', async () => {
  const clientMessage = 'Invalid query parameter: id';
  const clientErrApp = express();
  clientErrApp.get('/bad-request', (req, res, next) => {
    const err = new Error(clientMessage);
    err.status = 400;
    next(err);
  });
  clientErrApp.use(errorHandler);

  const response = await request(clientErrApp).get('/bad-request');

  assert.strictEqual(response.status, 400);
  assert.strictEqual(response.body.error, clientMessage);
});
