# Orrery

Orrery turns video of an old or broken machine into an editable, simulated mechanism. It infers the parts that are missing, ranks candidate repairs by how well they restore the original motion, and produces true-scale templates to fabricate the replacement.

Built for Kiroween 2026 (Resurrection category). Licensed under Apache-2.0.

## Status

The repository is being built spec by spec, in the order listed in `.kiro/steering/product.md`. What exists today:

- The monorepo toolchain: pnpm workspaces with Turborepo, a Cargo workspace, and a uv workspace, with pinned versions.
- The `toolbox` Docker image that holds every toolchain, and the `Makefile` that runs all commands inside it.
- CI that runs the same checks and tests in the same image.

The application, worker, engine, and the services they depend on land with the next platform-foundation tasks. This README is updated as each one ships.

## Requirements

Docker Engine and Docker Compose v2. Nothing else is installed on the host: Node.js, pnpm, Python, uv, Rust, wasm-pack, FFmpeg, and Playwright's Chromium all live in the toolbox image.

## Setup

```sh
make toolbox   # build the toolbox image with your UID and GID (about 5 GB, once)
make check     # install dependencies, then format, lint, and type checks for TypeScript, Rust, and Python
make test      # unit and integration tests for all languages
make shell     # a shell inside the toolbox, with the repository mounted at /workspace
make help      # every recipe
```

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
