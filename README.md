# Orrery

Orrery turns video of an old or broken machine into an editable, simulated mechanism. It infers the parts that are missing, ranks candidate repairs by how well they restore the original motion, and produces true-scale templates to fabricate the replacement.

Built for Kiroween 2026 (Resurrection category). Licensed under Apache-2.0.

## Status

The repository is being built spec by spec, in the order listed in `.kiro/steering/product.md`. What exists today:

- The monorepo toolchain: pnpm workspaces with Turborepo, a Cargo workspace, and a uv workspace, with pinned versions.
- The `toolbox` Docker image that holds every toolchain, and the `Makefile` that runs all commands inside it.
- The local service stack: PostgreSQL 18, Garage (S3 API, bootstrapped with a bucket, an application key, and CORS for browser uploads), Mailpit, and the OpenTelemetry Collector.
- `packages/config`: validated environment for the web app and worker.
- `packages/db`: the Drizzle schema, committed migrations, typed query modules, and a Testcontainers harness for integration tests against real Postgres 18.
- CI that starts the same stack and runs the same checks and tests in the same image.

The web app, worker, and engine land with the next platform-foundation tasks and join the stack then. This README is updated as each one ships.

## Requirements

Docker Engine and Docker Compose v2. Nothing else is installed on the host: Node.js, pnpm, Python, uv, Rust, wasm-pack, FFmpeg, and Playwright's Chromium all live in the toolbox image.

## Setup

```sh
make up        # start the service stack; returns once every service is healthy
make migrate   # apply database migrations to the local Postgres
make toolbox   # build the toolbox image with your UID and GID (about 5 GB, once)
make check     # install dependencies, then format, lint, and type checks for TypeScript, Rust, and Python
make test      # unit and integration tests for all languages
make shell     # a shell inside the toolbox, with the repository mounted at /workspace
make help      # every recipe
```

The first `make` run creates `.env` from `.env.example` and fills every secret with a random value generated on your machine. New keys added to `.env.example` later are appended to your `.env` without touching existing values.

### Local services

All ports bind to `127.0.0.1` and use non-default numbers so they do not collide with other projects.

| Service          | Host port     | Notes                                                   |
| ---------------- | ------------- | ------------------------------------------------------- |
| PostgreSQL 18    | 55432         | `make db-shell` opens psql                              |
| Garage S3 API    | 53900         | bucket `orrery`, path-style addressing, region `garage` |
| Garage admin API | 53903         | bearer token `GARAGE_ADMIN_TOKEN`                       |
| Mailpit inbox    | 58025         | open `http://localhost:58025` to read sent mail         |
| Mailpit SMTP     | 51025         | accepts any credentials                                 |
| OTLP gRPC / HTTP | 54317 / 54318 | traces appear in `make logs s=otel-collector`           |

`make down` stops the stack and keeps data. `make reset` deletes and recreates the Postgres and Garage volumes after a typed confirmation (`CONFIRM=1 make reset` skips it). Dependency caches survive a reset.

Files written inside the toolbox belong to your host user, because the image is built with your UID and GID. Rebuild with `make toolbox` after changing `infra/toolbox/Dockerfile`.

The repository also includes `.devcontainer/devcontainer.json`, which attaches an editor to the same toolbox container.

## Pinned versions

| Tool       | Version       | Pinned in                           |
| ---------- | ------------- | ----------------------------------- |
| Node.js    | 26.13.1 (LTS) | `.nvmrc`, toolbox base image digest |
| pnpm       | 12.18.0       | `package.json` `packageManager`     |
| Python     | 3.13.18       | `.python-version`                   |
| uv         | 0.13.8        | `pyproject.toml` `required-version` |
| Rust       | 1.100.0       | `rust-toolchain.toml`               |
| wasm-pack  | 0.15.1        | toolbox Dockerfile                  |
| Playwright | 1.65.0        | toolbox Dockerfile                  |

## Repository layout

```
.kiro/        steering, specs, and hooks for Kiro (committed, never ignored)
apps/         web app (TanStack Start) and worker (pg-boss)
packages/     shared TypeScript packages: schema, engine contract, db, ui, kinematics-wasm
crates/       Rust kinematics solver and its WebAssembly and Python bindings
services/     Python vision and reconstruction engine
tools/        synthetic lab
infra/        Docker Compose stack, toolbox image, deploy configuration
scripts/      check and test runners used by `pnpm check` and `pnpm test`
```

## Architecture

Orrery runs on one CPU-only server. The web app owns all persistence. A pg-boss worker dispatches jobs to a stateless Python engine, which reads footage through presigned URLs and reports progress through signed callbacks. Progress reaches the browser over Server-Sent Events fed by Postgres `LISTEN/NOTIFY`. One Rust kinematics solver runs in both the browser (WebAssembly) and the engine (Python bindings). The full design is in `.kiro/specs/platform-foundation/design.md`.

## Kiro workflow

Product context, technology decisions, the quality bar, repository conventions, and the design language are steering files in `.kiro/steering/`. Each capability is a spec in `.kiro/specs/<name>/` with requirements, a design with correctness properties, and a task list. Work proceeds task by task in spec order, and `make check` fails if `.kiro` is missing or ignored by git or Docker.
