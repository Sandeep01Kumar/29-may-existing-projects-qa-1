/**
 * PM2 ecosystem configuration — production process definition.
 *
 * (AAP §0.2.3, §0.5.1 Group 3 [CREATE], §0.5.2; FR-8)
 *
 * PM2 is the ONLY deployment mechanism in scope for this project (AAP §0.6.2 —
 * no Docker, Kubernetes, or CI/CD). This file declares HOW the process manager
 * launches, names, and supervises the application in development and production.
 *
 * It is consumed by the `pm2:*` npm scripts declared in `package.json`:
 *   - `npm run pm2:start`  ->  `pm2 start ecosystem.config.js --env production`
 *   - `npm run pm2:stop`   ->  `pm2 stop ecosystem.config.js`
 *   - `npm run pm2:reload` ->  `pm2 reload ecosystem.config.js`
 *
 * The `--env production` flag on `pm2:start` instructs PM2 to apply the
 * `env_production` block below, switching `NODE_ENV` to `production`. The
 * application's configuration module (`src/config/index.js`) and logger
 * (`src/utils/logger.js`) read `NODE_ENV` and `LOG_LEVEL` from `process.env`,
 * which PM2 populates from the selected env block before spawning the process.
 *
 * `script: 'server.js'` ties this config to the application bootstrap — the same
 * file named by `package.json` "main". `server.js` is the thin entry point that
 * loads config, initializes the winston logger, imports the Express `app`, and
 * calls `app.listen(...)`. PM2 launches that file, captures its stdout/stderr
 * (where winston writes), and restarts it according to the options below.
 *
 * Network binding (`PORT` / `HOST`) is declared in the development `env` block,
 * mirroring `.env.example`. `env_production` deliberately declares ONLY the keys
 * that must differ for production (`NODE_ENV`, `LOG_LEVEL`); `PORT`/`HOST` can be
 * supplied per-deployment via real environment variables or a `.env` file, and
 * `src/config/index.js` independently falls back to `127.0.0.1:3000` when they
 * are not provided — so the bind target stays overridable at deploy time.
 *
 * Conventions: CommonJS (`module.exports`), 2-space indentation (AAP §0.6.2,
 * §0.7). No ES modules, no TypeScript. This module exports a plain configuration
 * object and imports no application modules — PM2 reads it purely as data.
 */

module.exports = {
  // PM2 manages every entry in `apps` as an independent process. This small,
  // single-purpose service needs exactly one managed application.
  apps: [
    {
      // Process name shown by `pm2 list` / `pm2 status`, and the handle used by
      // `pm2 stop|reload|delete hello-world`.
      name: 'hello-world',

      // Application entry point PM2 spawns. MUST be the bootstrap that calls
      // `app.listen(...)` — i.e. `server.js` (also `package.json` "main").
      script: 'server.js',

      // Single-instance fork mode. Cluster mode is unnecessary for this tiny,
      // stateless service; `instances: 1` + `exec_mode: 'fork'` keeps exactly
      // one Node process under supervision.
      instances: 1,
      exec_mode: 'fork',

      // Disable PM2's file watcher. In production, restarts are driven by the
      // supervisor and by deploys (`pm2 reload`), never by source-file changes.
      watch: false,

      // Supervision policy: automatically restart on unexpected exit, and
      // recycle the process if its resident memory exceeds the threshold
      // (a defensive guard against slow leaks in a long-lived process).
      autorestart: true,
      max_memory_restart: '200M',

      // Default environment — applied when PM2 starts WITHOUT `--env`.
      // Mirrors the documented defaults in `.env.example`; consumed by
      // `src/config/index.js` (PORT/HOST/NODE_ENV) and `src/utils/logger.js`
      // (LOG_LEVEL).
      env: {
        NODE_ENV: 'development',
        PORT: 3000,
        HOST: '127.0.0.1',
        LOG_LEVEL: 'info'
      },

      // Production environment — applied when started with `--env production`
      // (see the `pm2:start` script). Declares only the values that change for
      // production. PORT/HOST are intentionally not pinned here so they remain
      // overridable via real env vars / `.env`, with `src/config` defaulting to
      // 127.0.0.1:3000 when unset.
      env_production: {
        NODE_ENV: 'production',
        LOG_LEVEL: 'info'
      }
    }
  ]
};
