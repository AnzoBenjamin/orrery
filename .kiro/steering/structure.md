---
inclusion: always
---

# Repository structure and conventions

```
orrery/
├── .kiro/                    steering, specs, hooks (committed, never ignored)
├── apps/
│   ├── web/                  TanStack Start app: UI, server functions, server routes
│   └── worker/               pg-boss worker: engine dispatch, event ingestion
├── packages/
│   ├── schema/               Zod mechanism graph (source of truth) + JSON Schema emit
│   ├── engine-contract/      Zod engine job and event contract + JSON Schema emit
│   ├── db/                   Drizzle schema, migrations, typed query modules
│   ├── ui/                   design tokens, components, engraving renderer
│   └── kinematics-wasm/      built WASM package + typed Web Worker client
├── crates/
│   ├── kinematics/           Rust solver, fitter, analysis
│   ├── kinematics-wasm/      wasm-bindgen bindings
│   └── kinematics-py/        PyO3 bindings
├── services/
│   └── engine/               Python vision and reconstruction service
├── tools/
│   └── lab/                  synthetic mechanism generator, renderers, evaluation
├── e2e/                      Playwright tests against the full stack
├── infra/                    docker compose, Kamal deploy config, host provisioning
├── fixtures/golden/          cross-language golden mechanism files
├── LICENSE                   Apache-2.0
├── THIRD_PARTY_MODELS.md
└── README.md
```

## Docker-first rule (applies to humans and agents)

- Never install or run Postgres, Garage, Mailpit, or other services on the host. Use `make up`.
- Run project commands inside the toolbox: `make shell`, or `docker compose -f infra/compose.yaml run --rm toolbox <command>`. Prefer the `make` recipes.
- Database access: `make db-shell` for psql, `make migrate` for migrations. Never `sudo`, never edit host Postgres config, never change file permissions to work around container ownership. If ownership is wrong, fix the UID/GID build arguments.
- To get a clean state, run `CONFIRM=1 make reset`. Do not delete volumes by hand.
- If a command needs a tool the toolbox lacks, add it to the toolbox Dockerfile with a pinned version. Do not install it on the host.

## Contracts flow one way

`packages/schema` and `packages/engine-contract` (Zod) → JSON Schema → generated Rust types (`typify`) and Python models (`datamodel-code-generator`). Generated code is committed and CI fails if regeneration produces a diff.

## Coordinate frames and units

Frame bugs are the most likely class of defect. Follow these exactly.

- All stored geometry is SI: meters, radians, seconds.
- `world`: right-handed 3D frame fixed to the ground body. Z is the normal of the primary plane for planar mechanisms.
- `plane:<id>`: 2D frame embedded in world by origin, x-axis, and normal.
- `body:<id>`: local frame of a body. Local point coordinates never change over time.
- `image`: pixels, origin top-left, x right, y down, per footage at its normalized resolution.
- `stabilized`: image frame after removing camera motion, aligned to the ground body.
- Every function that accepts or returns coordinates names the frame in the parameter or type name (for example `pointsImagePx`, `poseWorld`).
- Angles are counter-clockwise positive about the plane normal, in radians.

## Naming

- Database: `snake_case` tables and columns, singular table names.
- TypeScript: `camelCase` values, `PascalCase` types and components, kebab-case file names.
- Python: PEP 8. Rust: standard Rust naming.
- Domain terms are fixed: specimen (project), footage, analysis, body, joint, driver, mechanism, revision, resurrection run, candidate, tie group, cognate, verification.
