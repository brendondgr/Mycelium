# Vendored: llmkit

`apps/core/llmkit/` is the `llmkit` package from the `llm-integration` skill
(`bdgrClaudeSkills/llm-integration/templates/llmkit/`, llmkit `__version__`
1.0.0, files dated 2026-08-19), copied on 2026-11-09. The skill folder is not
a git repository, so the copy is identified by that version and date.

What was copied: `__init__`, `base`, `config`, `discovery`, `errors`, `params`,
`registry`, `retry`, `types` and `providers/*`, plus the skill's
`scripts/selftest.py` and `scripts/probe.py` as `selftest.py` and `probe.py`.

What was not: `agent.py` (Mycelium runs its own agent loop in `tools/agent/`),
`providers.yaml` and `requirements.txt` (servers come from `mycelium.toml`;
the dependencies are in `web/backend/pyproject.toml`).

Local changes, and nothing else:

- `__init__.py` does not import or export the agent loop (`run_tools`,
  `stream_tools`, `AgentRun`, `AgentStep`); its docstring says so.
- `selftest.py` and `probe.py` import `apps.core.llmkit` instead of putting the
  skill's `templates/` on `sys.path`. `selftest.py` drops its agent-loop suite
  (12 checks, since `agent.py` is not here) and its `main()` takes `argv`, so
  `apps/core/test_llmkit.py` can run it inside `make test`.

- `providers/anthropic_provider.py` converts the model's `created_at` to epoch
  seconds when the SDK hands back a `datetime` (it does in `anthropic` 0.125);
  upstream only converted strings, so `sort_models()` raised `TypeError` and
  discovery of every Anthropic server failed. Found by
  `apps/core/test_llm_servers.py` against the mock Anthropic server.

The folder is excluded from ruff (`[tool.ruff] extend-exclude`) so a re-vendor
is a plain diff against the skill. Mycelium code reaches it through
`apps/core/llm_servers.py` and `apps/core/llm_bridge.py` only.
