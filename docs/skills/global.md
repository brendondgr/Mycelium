# Global Mycelium Guidance

Use this guidance at the start of every Mycelium session before planning, editing, reviewing, documenting, or running commands.

## Required Reading

- Read `docs/purpose.md` to understand what Mycelium is and why it exists.
- Read `docs/styles.md` before design, frontend, copy, mascot, dashboard, or UX decisions.
- Read `docs/goals.md` before sequencing work, proposing features, or deciding what should come next.
- Read the task-specific skill from `docs/skills/` when the work touches planning, repository structure, website architecture, frontend UI, mobile behavior, accessibility, or the Discord bot. `docs/skills/index.md` is the registry.
- Read `docs/repo-map.md` to locate code by path before searching the tree; keep it updated when top-level areas move.
- Read `docs/architecture.md` for service boundaries and configuration, and `docs/api-contract.md` before changing anything the web app consumes.
- Read `docs/research/AGENT_INSTRUCTIONS.md` before running any experiment, benchmark, ablation, or evaluation. `docs/research/` is the only place a research finding is allowed to live.

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
- For data ownership, keep durable app records, semantic retrieval, and queue/cache concerns conceptually separate — even though Postgres physically holds the first two. Neo4j and MinIO run in Compose but no code uses them; do not describe them as working infrastructure or build a dependency on either without building the phase that needs it.
- Keep documentation accurate over comprehensive. A claim that is no longer true of the code is worse than no claim. When a change makes a doc wrong, fix the doc in the same commit.
- Implementation plans are working documents. Delete a plan once its work has shipped and record the outcome in `docs/changelog.md` plus whichever canonical doc it affects.
- When changing ranking logic — `retrieval.py`, `lexical.py`, `fusion.py`, `ranking.py`, or `pipeline.py`'s pool construction — re-run the evaluation harness and put the before/after numbers in the changelog entry. It is one command (`uv run --project eval eval/run.py --config eval/configs/<arm>.toml`) precisely so this is never skipped; see `docs/evaluation.md`. Relevance is a regression suite now, not a matter of opinion.
- Record every experiment, benchmark, baseline, ablation, or evaluation run in `docs/research/experiments/`, following `docs/research/AGENT_INSTRUCTIONS.md`. Scaffold with `make new-experiment SLUG=<slug>`, fill `PROTOCOL.md` before running, and check with `make validate-research`. Never report a metric in chat or a commit message without also writing it into the experiment's `manifest.yaml` and `RESULTS.md`; never hardcode a number into a plotting script; never delete a failed run. `docs/research/CLAIMS.md` is the ledger of what the project can actually claim — update it when an experiment changes a claim's status.
- When changing recommendation-pipeline logic (papers, opportunities, fellowships, refitting, briefing), audit the daily orchestrator in the same change: `manual_all.py` (run nightly by `mylo-daily.timer`) chains those stages, so confirm its stage list and each stage's semantics still match the intended split — the daily run scores only that day's new items and appends, never rewriting or deleting recommendations Mylo already wrote; whole-corpus replace passes (refitting) are on-demand only (sign-up / profile edits) and must never be scheduled into the daily chain.

## Validation

- Check that changes remain consistent with the purpose, style, and goals docs.
- Run the narrowest relevant validation command available from the repository root.
- For Python/backend validation, prefer `uv run --project web/backend ...`.
- For docs-only changes, at minimum check Markdown formatting and links when practical.

## Change Log Rules

- Update `docs/changelog.md` whenever a session changes tracked project files.
- Use the active log format version declared in the changelog header.
- Add entries only under `## Entries`; do not edit or delete previous entries.
- Keep entries general and outcome-focused. Describe the purpose or result, not line-by-line edits.
- Use exactly one controlled action type: `CREATED`, `MODIFIED`, `DELETED`, `REVIEWED`, `EXECUTED`, `RENAMED`, `MOVED`, `CORRECTED`, or `SUMMARIZED`.
- Use a correlation ID in the form `YYYYMMDD-topic-slug`, where the date is the local session date and the slug briefly names the task.
- Use UTC timestamps in ISO 8601 format, such as `2026-06-01T15:58:33Z`.
- If a prior entry needs correction, append a new `CORRECTED` entry that names the prior entry ID or correlation ID.
- When the entries become noisy, add a `SUMMARIZED` digest entry for the period and archive or move raw historical detail only when the user explicitly requests it.

Required entry schema:

```markdown
| Timestamp | Action | Correlation ID | Summary |
| --- | --- | --- | --- |
| 2026-06-01T15:58:33Z | MODIFIED | 20260601-global-changelog-schema | Added structured changelog rules for consistent agent updates. |
```

## Final Steps

- Update the change log using the schema above.
- Create a git commit for every completed change set, no matter how small.
- Commit documentation, configuration, tests, code, and rule updates; do not skip commits for small or docs-only changes.
- Keep commits focused on the current task and avoid staging unrelated user changes.
- Use a concise human-authored commit message without AI attribution, assistant signatures, or co-author trailers.
