# Global Mycelium Guidance

Use this guidance at the start of every Mycelium session before planning, editing, reviewing, documenting, or running commands.

## Required Reading

- Read `docs/purpose.md` to understand what Mycelium is and why it exists.
- Read `docs/styles.md` before design, frontend, copy, mascot, dashboard, or UX decisions.
- Read `docs/goals.md` before sequencing work, proposing features, or deciding what should come next.
- Read the task-specific skill from `docs/skills/` when the work touches planning, repository structure, website architecture, frontend UI, mobile behavior, or accessibility.

## Project Defaults

- Treat Mycelium as a lab intelligence platform for research teams, not a generic chatbot or paper search tool.
- Keep the product grounded in lab profiles, member profiles, research goals, evidence graphs, literature monitoring, grants, fellowships, reports, and strategic action plans.
- Keep documentation in `docs/` unless a tool-specific entrypoint requires a small pointer file elsewhere.
- Keep implementation boundaries clear: public site, authenticated app, backend API, worker jobs, infrastructure, and data stores have distinct responsibilities.
- Use root-level commands when possible; root scripts delegate into the web workspace.
- Use `uv` for Python backend dependency management, running backend commands, linting, and tests.
- Use semantic design tokens and the Mycelium style direction instead of one-off colors or generic SaaS defaults.
- Preserve object-level authorization, auditability, source grounding, and human review for sensitive lab workflows.

## Working Rules

- Before changing code or docs, check the existing pattern and update the smallest useful surface.
- Do not invent new product direction when the purpose, styles, or goals docs already decide it.
- If product direction is missing, update the canonical docs rather than burying the decision only in code.
- For UI work, account for loading, empty, populated, error, permission denied, job running, stale data, mobile, keyboard, contrast, and reduced-motion states.
- For backend work, keep Django responsible for auth, permissions, business logic, orchestration, admin, audit logs, and API contracts.
- For background work, prefer worker jobs for research scans, opportunity matching, extraction, graph updates, report generation, alerts, and scheduled digests.
- For data ownership, keep durable app records, semantic retrieval, graph relationships, object storage, and queue/cache concerns conceptually separate.

## Validation

- Check that changes remain consistent with the purpose, style, and goals docs.
- Run the narrowest relevant validation command available from the repository root.
- For Python/backend validation, prefer `uv run --project web/backend ...`.
- For docs-only changes, at minimum check Markdown formatting and links when practical.

## Final Steps

- If changes are made to the code, commit to GitHub without accrediting yourself to it.
- Update the change log in `docs/changelog.md` with a brief, non-technical description of the change and its motivation. 