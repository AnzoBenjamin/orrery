---
inclusion: always
---

# Quality bar

These rules override convenience. If a task cannot meet them, stop and raise it instead of working around them.

## No demos, mockups, or placeholder scaffolding

- Never ship mock data, fake API responses, hard-coded sample results, placeholder pages, "coming soon" states, lorem ipsum, or TODO-driven stubs.
- Never write code with the intent of "we'll fix this later." Write the production version the first time, or do not write it yet.
- Never stub out an engine stage to make the UI look complete. A feature exists when it works on real input end to end.
- Sample content shipped to users (for example example footage that judges can try) must be real footage processed by the real pipeline, stored and served like any user's data.
- Feature flags are allowed only for gradual rollout of finished work, never to hide unfinished work.

## Production-grade libraries over hand-rolled or minimal ones

Pick the established, well-maintained tool built for the job. Examples of the standard expected:

- Database access through Drizzle ORM with generated, committed migrations. No raw `pg` queries in application code.
- Authentication through Better Auth. No hand-rolled JWT or session code.
- Validation through Zod 4 at every trust boundary (HTTP, webhooks, env, file contents, engine events).
- Resumable uploads through Uppy with S3 multipart. No single-request large uploads.
- Background work through pg-boss. No `setTimeout` loops or in-memory queues.
- DXF generation through `ezdxf`. Linear algebra through `faer`. Collision through `parry`.

Before adding a dependency, check that it is actively maintained, has a compatible license, and is the community standard for the job. Record any non-obvious choice in `tech.md`.

## Vertical slice definition of done

A change that touches persistence is done only when all layers ship together:

1. Drizzle schema change plus generated migration.
2. Server function or server route with Zod-validated input and output and an authorization check.
3. Frontend UI that represents the data properly: loading, empty, error, and success states, designed to the design language.
4. Tests:
   - Integration test of the server layer against a real Postgres (Testcontainers).
   - Playwright end-to-end test that drives the feature through the real UI against the full running stack.
5. No table, column, or endpoint exists without a user-facing or operator-facing representation.

## Testing rules

- Tests run against real dependencies: Postgres via Testcontainers, object storage via Garage, email via Mailpit, the real engine service. Do not mock our own services or the database.
- Mocking is permitted only for third-party services we cannot run (OAuth providers), and only at the network boundary.
- Kinematics and vision logic carry property-based tests: `proptest` (Rust), `hypothesis` (Python), `fast-check` (TypeScript). Properties are listed in each spec's design under "Correctness properties".
- Accuracy-sensitive code is gated by the synthetic-lab regression suite. A change that lowers any tracked metric beyond its tolerance fails CI.
- Every bug fix adds a test that fails before the fix.

## Code standards

- TypeScript strict mode, no `any`, no non-null assertions without a comment explaining the invariant.
- Python fully typed, passing `pyright` in strict mode and `ruff`.
- Rust passes `clippy -D warnings` and `rustfmt`.
- Errors are typed and handled at the layer that can act on them. User-facing errors explain what happened and what to do next.
- Units are SI everywhere in data and code (meters, radians, seconds). Convert only at the display layer.
