# hao-backprop-test

A minimal Node.js HTTP server built with the [Express.js](https://expressjs.com/)
framework. The project has grown from a single-file `http`-module server into a
small, modular application enhanced with routing, middleware, environment-based
configuration, structured logging, and PM2 production deployment.

## Requirements

- **Node.js 18 or newer.** Express 5 requires Node 18+; the verified runtime is
  Node.js v22.
- **npm** (bundled with Node.js).

## Installation

```bash
npm install
```

## Endpoints

| Method | Path            | Status | Response body     | Notes                                                       |
| ------ | --------------- | ------ | ----------------- | ----------------------------------------------------------- |
| `GET`  | `/`             | `200`  | `Hello, World!\n` | Original behavior, preserved. Sent as `Content-Type: text/plain`. |
| `GET`  | `/good-evening` | `200`  | `Good evening`    | New endpoint.                                               |

In the table above, `\n` denotes the literal trailing newline character that the
`GET /` response includes; this reproduces the original server's response body
byte-for-byte.

## Environment variables

All variables are optional; when a value is not provided the application falls
back to the defaults listed below (defined in `src/config/index.js`). Copy the
committed template to a local, git-ignored `.env` file and adjust values as
needed:

```bash
cp .env.example .env
```

| Variable     | Default       | Description                                                                                   |
| ------------ | ------------- | --------------------------------------------------------------------------------------------- |
| `PORT`       | `3000`        | Port the HTTP server binds to.                                                                |
| `HOST`       | `127.0.0.1`   | Host / network interface the HTTP server binds to.                                            |
| `NODE_ENV`   | `development` | Runtime environment: `development`, `production`, or `test`.                                  |
| `LOG_LEVEL`  | `info`        | Application log verbosity (winston levels: `error`, `warn`, `info`, `http`, `verbose`, `debug`, `silly`). |

## npm scripts

| Script               | Runs                                             | Description                                       |
| -------------------- | ------------------------------------------------ | ------------------------------------------------- |
| `npm start`          | `node server.js`                                 | Start the server.                                 |
| `npm run dev`        | `nodemon server.js`                              | Start with automatic reload during development.   |
| `npm test`           | `node --test`                                    | Run the smoke tests in `tests/`.                  |
| `npm run pm2:start`  | `pm2 start ecosystem.config.js --env production` | Start the app under PM2 in production mode.       |
| `npm run pm2:stop`   | `pm2 stop ecosystem.config.js`                   | Stop the PM2-managed process.                     |
| `npm run pm2:reload` | `pm2 reload ecosystem.config.js`                 | Zero-downtime reload of the PM2-managed process.  |

## Production deployment with PM2

Install PM2 globally (or use the local `devDependency` already declared in
`package.json`):

```bash
npm install pm2 -g
```

Start the service under PM2 using the committed ecosystem file:

```bash
pm2 start ecosystem.config.js --env production
```

`ecosystem.config.js` defines the process (`name: hello-world`,
`script: server.js`, fork mode); PM2 manages restarts and log aggregation. The
equivalent npm shortcuts are also available: `npm run pm2:start`,
`npm run pm2:stop`, and `npm run pm2:reload`.

## Project structure

```text
.
├── server.js              # Bootstrap: loads config + logger, starts the Express app, handles graceful shutdown
├── ecosystem.config.js    # PM2 process definition
├── .env.example           # Environment variable template
├── package.json           # Manifest: dependencies and npm scripts
├── src/
│   ├── app.js             # Express application factory (registers middleware, mounts routers)
│   ├── config/
│   │   └── index.js       # Environment configuration (PORT, HOST, NODE_ENV, LOG_LEVEL)
│   ├── routes/            # Route modules: GET / and GET /good-evening
│   ├── middleware/        # Request logging, 404, and centralized error handling
│   └── utils/
│       └── logger.js      # winston application logger
└── tests/                 # Endpoint smoke tests (node:test + supertest)
```
