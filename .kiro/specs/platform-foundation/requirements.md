# Requirements: Platform foundation

## Introduction

The platform foundation provides the production infrastructure every other spec builds on: monorepo and toolchain, configuration, database and migrations, authentication and authorization, object storage with resumable uploads, background jobs, realtime events, the engine service contract, email, observability, security, the full-stack test harness, CI/CD, deployment, and hackathon compliance. Nothing in this spec is a placeholder. Each capability ships with a user-facing or operator-facing surface and end-to-end tests.

## Glossary

- **Web app**: the TanStack Start application in `apps/web`.
- **Worker**: the pg-boss process in `apps/worker`.
- **Engine**: the Python service in `services/engine`.
- **Specimen**: a user's project representing one machine.
- **Full stack**: web app, worker, engine, Postgres, Garage, and Mailpit running together via Docker Compose.

## Requirements

### Requirement 1: Monorepo and toolchain

**User Story:** As a developer, I want one repository with consistent tooling across TypeScript, Rust, and Python, so that every package builds, lints, and tests with one command.

#### Acceptance Criteria

1. THE repository SHALL use pnpm workspaces and Turborepo for TypeScript packages, a Cargo workspace for Rust crates, and a uv workspace for Python projects.
2. WHEN a developer runs `pnpm check`, THE toolchain SHALL run formatting checks, linting, and type checking for TypeScript, Rust, and Python.
3. WHEN a developer runs `pnpm test`, THE toolchain SHALL run unit and integration tests for all languages.
4. WHEN a developer runs `pnpm dev`, THE toolchain SHALL start the full stack with hot reload for the web app, worker, and engine.
5. THE repository SHALL pin Node.js, pnpm, Python, and Rust versions in committed version files.
6. WHEN generated code (JSON Schema, Rust types, Python models, WASM bindings) is out of date with its source, THE `pnpm check` command SHALL fail and name the stale artifact.

### Requirement 1A: Docker-first development

**User Story:** As a developer or a coding agent, I want every service and toolchain to run in Docker, so that setup is one command and never fails on host packages, versions, or permissions.

#### Acceptance Criteria

1. THE repository SHALL run every stateful and supporting service (Postgres, Garage, Mailpit, OTel Collector, GlitchTip, the engine) only in Docker containers defined in `infra/compose.yaml`. Host installs of these services SHALL NOT be required or documented.
2. THE repository SHALL provide a `toolbox` dev container image with pinned Node.js, pnpm, Python, uv, Rust, wasm-pack, FFmpeg, Playwright browsers, and Blender, and SHALL run `pnpm check`, `pnpm test`, `pnpm codegen`, migrations, and lab commands inside it.
3. THE repository SHALL provide a `Makefile` (or `just` recipes) as the single entry point: `up`, `down`, `reset`, `logs`, `shell`, `migrate`, `db-shell`, `seed-samples`, `check`, `test`, `e2e`, `lab-smoke`. Each recipe SHALL work on a fresh clone with only Docker and Docker Compose installed.
4. THE containers SHALL run as a non-root user whose UID and GID match the host user (passed as build arguments), so files written to bind mounts are owned by the developer.
5. THE Compose stack SHALL use named volumes for database and object data, health checks on every service, and `depends_on` with `condition: service_healthy`, so that `up` returns only when the stack is usable.
6. THE `reset` recipe SHALL destroy and recreate the project's volumes after a confirmation prompt, which can be bypassed with an explicit `CONFIRM=1` for agents and CI.
7. THE Compose project SHALL use a fixed project name and non-default host ports documented in `.env.example`, so it does not collide with other local projects.
8. THE repository SHALL provide `.devcontainer/devcontainer.json` that attaches to the toolbox service.
9. CI SHALL use the same Compose file and toolbox image as local development.

### Requirement 2: Configuration and secrets

**User Story:** As an operator, I want configuration validated at startup, so that misconfiguration fails fast with a clear message instead of failing at runtime.

#### Acceptance Criteria

1. THE web app, worker, and engine SHALL validate all environment variables at startup against a typed schema.
2. IF a required variable is missing or invalid, THEN THE process SHALL exit with a non-zero code and name each invalid variable without printing secret values.
3. THE repository SHALL contain an `.env.example` documenting every variable, and SHALL NOT contain real secrets.
4. THE web app SHALL expose to the browser only variables explicitly marked public in the schema.

### Requirement 3: Database and migrations

**User Story:** As a developer, I want a typed schema with reviewed migrations, so that data changes are safe and reproducible.

#### Acceptance Criteria

1. THE system SHALL define all tables in Drizzle ORM in `packages/db` and generate SQL migrations with drizzle-kit.
2. WHEN the web app or worker starts in production, THE system SHALL refuse to run if the database has unapplied migrations.
3. THE system SHALL apply migrations through a dedicated migrate command that runs once per deployment before new processes start.
4. THE system SHALL use UUIDv7 primary keys, `timestamptz` timestamps, and foreign keys with explicit `on delete` behavior.
5. WHEN a mechanism graph is written to a `jsonb` column, THE system SHALL validate it against the shared schema and reject invalid graphs.
6. THE system SHALL expose data access only through typed query modules in `packages/db`. Application code SHALL NOT issue raw SQL strings.

### Requirement 4: Authentication

**User Story:** As a user, I want to create an account and sign in securely, so that my specimens and footage are private.

#### Acceptance Criteria

1. THE system SHALL support sign-up and sign-in with email and password, GitHub OAuth, Google OAuth, and passkeys through Better Auth.
2. WHEN a user signs up with email and password, THE system SHALL send a verification email and SHALL NOT allow uploads until the email is verified.
3. WHEN a user requests a password reset, THE system SHALL send a single-use reset link that expires after 60 minutes.
4. THE system SHALL rate-limit sign-in, sign-up, and reset requests per IP address and per account.
5. THE system SHALL store sessions in Postgres with HTTP-only, Secure, SameSite=Lax cookies.
6. WHEN a user signs out, THE system SHALL revoke the session server-side.
7. THE system SHALL let a signed-in user view and revoke their active sessions and linked sign-in methods from an account settings page.
8. THE system SHALL let a user delete their account, which deletes their specimens, footage objects, and derived artifacts.

### Requirement 5: Authorization

**User Story:** As a user, I want only me and people I share with to see my specimens, so that my data stays private.

#### Acceptance Criteria

1. THE system SHALL enforce authorization in a single policy module used by every server function and server route.
2. WHEN a request references a resource the caller does not own and has no valid share grant for, THE system SHALL respond with not found, without revealing that the resource exists.
3. THE system SHALL support read-only share links per specimen, stored as hashed tokens, with optional expiry and revocation.
4. THE system SHALL have an automated test for every server function and route proving that a second user cannot read or modify the first user's resources.

### Requirement 6: Object storage and resumable uploads

**User Story:** As a user filming on a phone over a weak connection, I want uploads that resume after interruption, so that long footage uploads succeed.

#### Acceptance Criteria

1. THE system SHALL upload footage directly from the browser to object storage using S3 multipart uploads coordinated by Uppy, with server-signed part URLs.
2. WHEN an upload is interrupted, THE client SHALL resume from the last completed part.
3. THE system SHALL reject uploads larger than 1 GB or longer than 5 minutes, and SHALL reject files whose probed container and codec are not a supported video format, regardless of the declared MIME type.
4. THE system SHALL store objects under keys scoped by user and specimen, and SHALL serve them only through short-lived presigned GET URLs after an authorization check.
5. WHEN a specimen, footage item, or account is deleted, THE system SHALL delete the associated objects through a background job and SHALL retry failures.
6. THE system SHALL abort and clean up incomplete multipart uploads older than 24 hours.
7. THE system SHALL enforce a per-user storage quota (default 5 GB), checked when an upload is created, and SHALL show usage and the quota in account settings.

### Requirement 7: Background jobs

**User Story:** As an operator, I want long-running work in a durable queue, so that restarts and failures never lose or duplicate work.

#### Acceptance Criteria

1. THE system SHALL run all long-running and retryable work through pg-boss queues processed by the worker.
2. THE system SHALL define each job type with a Zod payload schema, a retry policy, a timeout, and an idempotency key.
3. WHEN a job exhausts its retries, THE system SHALL mark the related domain record as failed with a user-readable reason and notify the user in the UI.
4. THE system SHALL provide an operator page, restricted to admin users, listing queue depth, running jobs, and recent failures, with retry and cancel actions.

### Requirement 8: Realtime events

**User Story:** As a user, I want to watch analysis progress live, so that I know what the engine is doing and when it needs me.

#### Acceptance Criteria

1. THE web app SHALL stream domain events to authorized clients over Server-Sent Events, fed by Postgres `LISTEN/NOTIFY`.
2. WHEN a client reconnects with a `Last-Event-ID`, THE system SHALL replay missed events from the persisted event log.
3. THE system SHALL send a heartbeat at least every 20 seconds on open streams.
4. THE system SHALL authorize each stream subscription against the specimen policy.

### Requirement 9: Engine service contract

**User Story:** As a developer, I want a strict contract between the worker and the engine, so that either side can change without silent breakage.

#### Acceptance Criteria

1. THE engine contract SHALL be defined in Zod in `packages/engine-contract` and generated into Pydantic models for the engine.
2. WHEN the worker dispatches a job, THE worker SHALL send presigned input URLs, scoped artifact upload grants, a callback URL, and a per-job HMAC secret.
3. THE engine SHALL sign every callback with HMAC-SHA256 over the timestamp and body. THE web app SHALL reject callbacks with invalid signatures or timestamps older than 5 minutes.
4. THE web app SHALL process callbacks idempotently using the event sequence number.
5. WHEN the engine is unreachable, THE worker SHALL retry dispatch with exponential backoff and surface the delay to the user as a queue state.
6. THE contract SHALL carry a version. WHEN versions are incompatible, THE engine SHALL reject the job with a typed error.

### Requirement 10: Email

**User Story:** As a user, I want clear, on-brand emails for account actions and finished analyses, so that I can return when work completes.

#### Acceptance Criteria

1. THE system SHALL send email through Nodemailer over SMTP with templates built in React Email that follow the design language.
2. THE system SHALL send verification, password reset, sign-in alert for new devices, and analysis-complete emails.
3. THE system SHALL let users turn off analysis-complete emails in account settings.

### Requirement 11: Observability

**User Story:** As an operator, I want to trace one user action across web, worker, and engine, so that I can diagnose failures quickly.

#### Acceptance Criteria

1. THE web app, worker, and engine SHALL emit OpenTelemetry traces and propagate `traceparent` across HTTP calls, job payloads, and engine callbacks.
2. THE system SHALL report unhandled errors to self-hosted GlitchTip through Sentry-compatible SDKs, with release and environment tags and without personal data beyond user ID.
3. THE system SHALL emit structured JSON logs with trace IDs.
4. THE web app and engine SHALL expose health endpoints reporting dependency status.

### Requirement 12: Security hardening

**User Story:** As a user, I want the app to be secure by default, so that my footage and account are safe.

#### Acceptance Criteria

1. THE web app SHALL send a Content Security Policy with nonces, HSTS, `X-Content-Type-Options`, `Referrer-Policy`, and `Permissions-Policy` headers.
2. THE web app SHALL validate every server function and route input with Zod and reject unknown fields.
3. THE system SHALL rate-limit upload signing, analysis creation, and share-link access.
4. THE engine SHALL accept requests only from the worker, authenticated with a service token, and SHALL fetch only from object-storage hosts on an allowlist.
5. THE CI pipeline SHALL run dependency vulnerability scanning and fail on high-severity issues with available fixes.

### Requirement 13: Testing infrastructure

**User Story:** As a developer, I want end-to-end tests against the real stack, so that a passing suite means the product works.

#### Acceptance Criteria

1. THE repository SHALL provide integration tests that run against real Postgres and Garage via Testcontainers.
2. THE repository SHALL provide Playwright end-to-end tests that run against the full stack started by Docker Compose, including the real engine.
3. THE end-to-end suite SHALL read verification and reset emails from Mailpit's API instead of bypassing verification.
4. THE end-to-end suite SHALL create its data through the product's own flows or server functions, never through direct database inserts.
5. THE end-to-end suite SHALL run automated accessibility checks with axe on every page it visits and fail on serious or critical violations.
6. THE end-to-end suite SHALL capture traces, video, and screenshots on failure as CI artifacts.
7. WHEN a test needs footage, THE suite SHALL use short real clips produced by the synthetic lab and committed under `e2e/fixtures` with their ground truth.

### Requirement 14: CI/CD and deployment

**User Story:** As a team, I want every change verified and deployed automatically, so that the hosted app judges see is always working.

#### Acceptance Criteria

1. WHEN a pull request is opened, THE CI pipeline SHALL run checks, unit tests, integration tests, end-to-end tests, the synthetic-lab smoke suite, and Lighthouse CI against the performance budgets.
2. THE CI pipeline SHALL run the full engine suite on GitHub-hosted runners, with the engine container limited to the reference VPS profile (4 CPUs, 8 GB), for changes under `services/engine`, `crates/`, or `tools/lab`. The lab `core` suite SHALL run nightly the same way.
3. WHEN the main branch passes CI, THE pipeline SHALL run migrations and deploy the web app, worker, and engine roles to the VPS with Kamal.
4. THE deployment SHALL keep the previous release available for one-command rollback.
5. THE deployment SHALL run a post-deploy smoke test against production that signs in a dedicated test account and opens a sample specimen.
6. THE production stack SHALL consist only of free and open-source software as listed in `tech.md`, self-hosted on one CPU-only VPS the team controls.
7. THE system SHALL back up Postgres continuously with pgBackRest to a local Garage repository and to an off-VPS repository over SFTP, SHALL mirror object storage off the VPS nightly, and SHALL verify a restore daily.
8. THE system SHALL collect metrics, logs, and traces in self-hosted OpenObserve, and SHALL run Gatus uptime checks against the public endpoints.
9. THE deployment SHALL set CPU and memory limits on every container as listed in `tech.md`, so that a running analysis cannot starve the web app.
10. WHILE the engine runs an analysis at full quota, THE web app SHALL keep p95 server response time under 300 ms for page loads and server functions, verified by a load test in CI.

### Requirement 15: Hackathon compliance

**User Story:** As the team, I want the repository to meet every Kiroween submission rule, so that the project is not disqualified.

#### Acceptance Criteria

1. THE repository SHALL include an Apache-2.0 `LICENSE` file detectable by GitHub.
2. THE repository SHALL commit the `.kiro` directory at the root and SHALL NOT list it or its subfolders in any ignore file.
3. THE CI pipeline SHALL fail if `.kiro` is missing or ignored.
4. THE README SHALL document setup, the architecture, how to run the full stack, and the Kiro workflow used.
5. THE repository SHALL include `THIRD_PARTY_MODELS.md` listing each model, its source, version, and license.

### Requirement 16: Kiro workflow

**User Story:** As the team, I want Kiro hooks that enforce our quality bar, so that the rules in steering are applied on every change.

#### Acceptance Criteria

1. THE repository SHALL include a hook that, when a file under `packages/db/src/schema` is saved, reminds the agent to generate the migration and complete the vertical slice (server, UI, integration test, end-to-end test).
2. THE repository SHALL include a hook that runs the synthetic-lab smoke suite when files under `crates/kinematics` or `services/engine/src` change, and reports metric regressions.
3. THE repository SHALL include a hook that regenerates cross-language types when files under `packages/schema` or `packages/engine-contract` change.
4. THE repository SHALL include a hook that blocks commits containing placeholder markers (`TODO`, `FIXME`, `lorem`, `mock` outside test directories).
