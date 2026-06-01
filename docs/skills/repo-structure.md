# Repository Structure Skill

Use this skill when defining, documenting, or enforcing repository layout.
It covers generic repo conventions and decides when a project needs a more
specific structural skill.

## Core Rules

- Keep project documentation in `docs/`.
- Keep reusable shared code in clearly named top-level packages or folders.
- Avoid dumping unrelated files into `misc/`, `utils/`, or `helpers/`.
- Prefer small, purpose-based folders over one oversized generic bucket.
- Use `uv` for Python package and environment management.

## Web and UI Projects

- If the project is a website, dashboard, web app, or API-backed frontend,
  pair this skill with `website-architecture` before generating files.
- Use `ui-frontend` only after the site structure, routes, data flow, and
  frontend/backend boundary are defined.
- All web-specific runtime files should live under the root `web/` directory.

## LangGraph Projects

- LangGraph projects are a first-class case of repository structure, not a
  separate system.
- Keep graph wiring, node behavior, state, tools, prompts, services, tests,
  and deployment files separated.
- Keep the compiled graph thin and explicit.
- Keep agent-specific state apart from shared state.
- Keep prompt text out of node bodies when it can live in its own file.
- Prefer one graph per file and one node per responsibility.

### Recommended Layout

```text
root/
├── langgraph.json
├── pyproject.toml
├── .env.example
├── docs/
├── scripts/
├── tests/
└── src/<package>/
    ├── __init__.py
    ├── main.py
    ├── config.py
    ├── core_state/
    ├── shared_tools/
    ├── services/
    └── agents/
        ├── orchestrator/
        │   ├── graph.py
        │   ├── nodes.py
        │   ├── state.py
        │   └── prompts.py
        └── planner/
            ├── graph.py
            ├── nodes.py
            ├── state.py
            └── prompts.py
```

### LangGraph Validation

- Confirm the repo can answer three questions quickly: where is the state
  defined, where is the graph wired, and where is the tool logic implemented?
- Put experiments in a separate folder, not beside production graph code.
- Keep integration code and observability helpers in their own areas.

## Structure Expectations

- Document the selected layout in `docs/structure.md` when the repo is being
  initialized or reorganized.
- For Python projects, keep lightweight tests in a top-level `tests/`
  directory and split by behavior or subsystem.
