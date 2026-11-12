# Tasks: Platform foundation

## Build order

Task numbers are stable references (other specs cite them). Work them in this order, which brings the web app, worker, and engine up as soon as each has a real job:

1. 1.x, 2.0, 2.1 (services). The web, worker, and engine Compose services are added by the tasks that create them.
2. 2.2 env validation.
3. 3.1–3.3 database.
4. 4.1 Better Auth. Creates `apps/web` and adds the `web` Compose service.
5. 7.1 pg-boss core. Creates `apps/worker` and adds the `worker` Compose service. Moved ahead of 4.2 because the `email.send` queue needs it.
6. 4.2–4.4 email and account screens.
7. 6.x uploads and probing. 6.3 creates `services/engine` and adds the `engine` Compose service with the production CPU and memory limits.
8. 5.x, then 7.2–7.6, 8.x, 9.x, 10.x, 11.x in numeric order. Testing infrastructure from 9.1–9.3 is set up by the first task that needs it, not deferred to 9.

- [ ] 1. Repository and toolchain
  - [x] 1.1 Initialize pnpm workspace, Turborepo pipeline, Cargo workspace, uv workspace, and version files (`.nvmrc`, `packageManager`, `.python-version`, `rust-toolchain.toml`).
    - _Requirements: 1.1, 1.5_
  - [ ] 1.2 Configure Biome, `tsc` project references, ruff, pyright strict, clippy, and rustfmt. Wire `pnpm check`, `pnpm test`, and `pnpm dev`.
    - _Requirements: 1.2, 1.3, 1.4_
  - [ ] 1.3 Add codegen pipeline (`pnpm codegen`) and a stale-artifact check in `pnpm check`.
    - _Requirements: 1.6_
  - [x] 1.4 Add `LICENSE` (Apache-2.0), `README.md` with setup and architecture, `THIRD_PARTY_MODELS.md`, and a CI step that fails if `.kiro` is missing or ignored.
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

- [ ] 2. Local full stack (Docker-first)
  - [ ] 2.0 Build the `toolbox` image with pinned toolchains and host-matched UID/GID, the `Makefile` entry points, health-checked Compose services with named volumes and a fixed project name, `.devcontainer/devcontainer.json`, and a CI job that runs `make up check test` on a clean runner.
    - _Requirements: 1A.1–1A.9_
  - [ ] 2.1 Write `infra/compose.yaml` with Postgres 18, Garage (single node, with bucket, key, and CORS bootstrap), Mailpit, OTel collector, web, worker, and engine. The engine image is CPU-only and runs with the same CPU and memory limits as production.
    - _Requirements: 1.4, 13.2_
  - [ ] 2.2 Add typed env schemas for web, worker, and engine with redacted error output. Add `.env.example`.
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [ ] 3. Database
  - [ ] 3.1 Create `packages/db` with Drizzle client, UUIDv7 helper, core tables from the design, and the first generated migration.
    - _Requirements: 3.1, 3.4_
  - [ ] 3.2 Implement the migrate command and `assertMigrationsApplied()` boot check.
    - _Requirements: 3.2, 3.3_
  - [ ] 3.3 Implement typed query modules for specimens, footage, upload sessions, share links, domain events, notifications, and object deletions, with Testcontainers integration tests.
    - _Requirements: 3.6_
  - [ ] 3.4 Add the `jsonb` mechanism-graph validation helper using `packages/schema` (lands with mechanism-core task 1).
    - _Requirements: 3.5_

- [ ] 4. Authentication and account
  - [ ] 4.1 Configure Better Auth with the Drizzle adapter, email and password with verification, GitHub, Google, passkeys, database rate limiting, and the TanStack Start cookie plugin. Generate the auth schema and migration.
    - _Requirements: 4.1, 4.2, 4.4, 4.5_
  - [ ] 4.2 Build the email package with React Email templates (verification, reset, new sign-in alert, analysis complete) and the `email.send` queue.
    - _Requirements: 4.2, 4.3, 10.1, 10.2_
  - [ ] 4.3 Build sign-up, sign-in, verify, reset, and account settings screens (sessions, linked methods, passkeys, email preferences, delete account) to the design language. Coordinate visuals with workbench task 2.
    - _Requirements: 4.6, 4.7, 4.8, 10.3_
  - [ ] 4.4 End-to-end tests: sign-up with Mailpit verification, unverified upload blocked, reset flow, passkey via virtual authenticator, session revocation, account deletion removes objects.
    - _Requirements: 4.1–4.8, 13.3_

- [ ] 5. Authorization and sharing
  - [ ] 5.1 Implement `policy.ts` and the `authed()` server-function wrapper with typed domain errors.
    - _Requirements: 5.1, 5.2, 12.2_
  - [ ] 5.2 Implement share links (create, list, revoke, resolve) with hashed tokens and rate limiting, plus the share management UI.
    - _Requirements: 5.3, 12.3_
  - [ ] 5.3 Add a generated cross-user authorization test that enumerates every registered server function and route (property 1).
    - _Requirements: 5.4_

- [ ] 6. Uploads and storage
  - [ ] 6.1 Implement multipart server functions and the S3 client configured for Garage.
    - _Requirements: 6.1, 6.4_
  - [ ] 6.2 Build the upload component on Uppy core with `@uppy/aws-s3` multipart and Golden Retriever, with a custom UI.
    - _Requirements: 6.1, 6.2_
  - [ ] 6.3 Implement the `footage.probe` job and engine `/v1/probe` endpoint with size, duration, and codec validation.
    - _Requirements: 6.3_
  - [ ] 6.4 Implement `objects.delete` and `uploads.reap` jobs.
    - _Requirements: 6.5, 6.6_
  - [ ] 6.5 End-to-end tests: resumable upload across a forced offline period, rejection of a renamed non-video file, deletion cleanup.
    - _Requirements: 6.1–6.6_

- [ ] 7. Jobs, realtime, and engine contract
  - [ ] 7.1 Create `apps/worker` with pg-boss, typed queue definitions, and the `enqueue` helper. Runs before 4.2 (see Build order).
    - _Requirements: 7.1, 7.2_
  - [ ] 7.2 Implement failure handling that marks domain records failed and creates notifications. Build the notification tray UI.
    - _Requirements: 7.3_
  - [ ] 7.3 Build the admin operator page (queue depth, running, failures, retry, cancel) with an admin role check.
    - _Requirements: 7.4_
  - [ ] 7.4 Implement `domain_event` writes with `NOTIFY`, the SSE route with replay and heartbeats, and the `useSpecimenEvents` client hook. Integration test for property 4.
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - [ ] 7.5 Define `packages/engine-contract`, generate Pydantic models, implement HMAC signing in the engine and verification plus idempotent ingestion in the web app. Property tests 2 and 3.
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6_
  - [ ] 7.6 Implement dispatch retries with backoff and the "engine waking up" queue state in the UI.
    - _Requirements: 9.5_

- [ ] 8. Observability and security
  - [ ] 8.1 Add OpenTelemetry to web, worker, and engine with `traceparent` propagation through job payloads and callbacks. Add GlitchTip error reporting through the Sentry SDKs. Add structured logs.
    - _Requirements: 11.1, 11.2, 11.3_
  - [ ] 8.2 Add health endpoints and a status section on the admin page.
    - _Requirements: 11.4_
  - [ ] 8.3 Add security headers with CSP nonces, engine service-token auth, and the engine egress allowlist.
    - _Requirements: 12.1, 12.4_

- [ ] 9. Testing infrastructure
  - [ ] 9.1 Set up Vitest with Testcontainers global setup for Postgres and Garage.
    - _Requirements: 13.1_
  - [ ] 9.2 Set up Playwright against the Compose stack with a Mailpit client, axe checks on every visited page, and failure artifacts.
    - _Requirements: 13.2, 13.3, 13.5, 13.6_
  - [ ] 9.3 Add test helpers that create users and specimens through the product's server functions only.
    - _Requirements: 13.4_
  - [ ] 9.4 Commit short synthetic clips with ground truth to `e2e/fixtures` (produced by synthetic-lab task 6).
    - _Requirements: 13.7_

- [ ] 10. CI/CD and deployment
  - [ ] 10.1 GitHub Actions: checks, unit, integration, end-to-end, lab smoke suite, Lighthouse CI, dependency scanning.
    - _Requirements: 14.1, 12.5_
  - [ ] 10.2 Engine workflow on GitHub-hosted runners with the engine limited to 4 CPUs and 8 GB, for engine, crates, and lab changes. Nightly `core` suite run with results ingested into the Proving Ground.
    - _Requirements: 14.2_
  - [ ] 10.3 Deploy pipeline with Kamal 2: migrate, deploy the `web`, `worker`, and `engine` roles with zero-downtime rollout and `kamal rollback`, then run the post-deploy production smoke test.
    - _Requirements: 14.3, 14.4, 14.5_
  - [ ] 10.4 Provision the VPS: hardened OS, UFW, unattended upgrades, Docker, and Kamal accessories for the CNCF Distribution registry, PostgreSQL 18, Garage, Postfix with OpenDKIM, GlitchTip with Valkey, OTel Collector, OpenObserve, and Gatus. Apply the container limits from `tech.md`, the swap file, the `oom_score_adj` settings, and an 80% disk-use alert. Configure DNS (SPF, DKIM, DMARC, reverse DNS) for Postfix.
    - _Requirements: 14.6, 14.8, 14.9, 10.1, 11.2_
  - [ ] 10.5 Configure pgBackRest with the local Garage repository and the off-VPS SFTP repository, the nightly rclone mirror of Garage buckets, and a daily restore check that alerts on failure.
    - _Requirements: 14.7_
  - [ ] 10.6 Add the contention load test: run an analysis at full engine quota while k6 drives page loads and server functions, and fail CI if p95 exceeds 300 ms.
    - _Requirements: 14.9, 14.10_
  - [ ] 10.7 Implement the per-user storage quota check at upload creation and show usage in account settings. Integration and end-to-end tests.
    - _Requirements: 6.7_

- [ ] 11. Kiro hooks
  - [ ] 11.1 Add the vertical-slice reminder hook for schema files, the codegen hook for contract packages, the lab smoke-suite hook for solver and engine changes, and the placeholder-marker commit guard.
    - _Requirements: 16.1, 16.2, 16.3, 16.4_
