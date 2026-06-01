# Website Architecture Skill

Use this skill when planning or scaffolding a website, dashboard, web app, or
API-backed frontend before any UI code is generated.

## Core Rules

- All site code, assets, routes, and runtime files belong under `web/`.
- All repository documentation belongs under `docs/`.
- Define structure before generating pages or components.

## Required Planning Artifact

Before implementation, define:

1. Application mode.
2. User roles and auth boundaries.
3. Route map.
4. Data-flow map.
5. Frontend/backend boundary.
6. Repository layout.
7. Required documentation files.
8. Build, run, and test commands.

## What Each Route Must Include

- Path.
- Purpose.
- Required auth level.
- Data dependencies.
- Primary page, layout, or component ownership.
- Backend endpoints used, if any.

## Backend and API Contracts

- If a backend exists, define request and response ownership, validation
  boundaries, and shared schema locations.
- Create `docs/api-contract.md` when the frontend depends on an explicit API
  contract.

## Validation

- Confirm the route map and data flow before UI generation.
- Confirm the final layout is concrete enough that another agent can scaffold
  the project without guessing.

