# Recommendation

Ranking and filtering of the grounded corpus against the profiles of people,
labs, departments and projects. Every night it ranks the **whole corpus** for
every target, takes each target's per-theme slate (papers 25 per theme, grants
and conferences 10, fellowships 5), marks what entered the Top-25, and writes
model verdicts only for what entered. On a sign-up or a profile edit it refits
on demand.

| | |
|---|---|
| Depends on | `retrieval` |
| Core | yes — the delivery code and profile pages read slates on every request |
| Django app label | `recommendation`; its tables keep their `content_*` names |
| Exports | `read`, `service`, `events`, plus the modules the delivery code still imports directly (listed in `tool.py`) |
| Config | `[tools.recommendation]` in `mycelium.toml`; `make config ARGS="explain tools.recommendation"`. Model-call budgets stay universal under `[nightly]` |
| Nightly stages | `run_daily_suggestions`, `run_daily_opportunities --no-prune` (phase `rank`) |
| Beat | `recompute-project-profiles` (nightly team-profile recompute) |
| API | none of its own; the delivery code serves the feeds |

## What is in here

| Area | Path |
|---|---|
| The paper pipeline and its pool construction | `pipeline.py` |
| Fusion, ranking, rerank, admission, clustering | `fusion.py`, `ranking.py`, `reranking.py`, `typesafe_rerank.py`, `admission.py`, `clustering.py`, `explorations.py` |
| Slates, Top-25, per-theme write-ups, verdicts | `slates.py`, `top_feed.py`, `theme_run.py`, `cluster_fit.py`, `comprehension.py`, `verdicts.py` |
| Grants, conferences and fellowships | `opportunities.py`, `opportunity_llm.py`, `fellowships.py`, `fellowship_bands.py` |
| Targets and nightly target selection | `targets.py`, `tasks.py` |
| Who an item is for, team profiles, profile vectors | `member_fit.py`, `team_profile.py`, `vectors.py` |
| Refits, sign-up matching, suggestions | `refitting.py`, `onboarding_match.py`, `suggest.py`, `scan_status.py` |
| Models | `models.py` — `RelevanceScore`, `ItemComprehension`, `ProjectProfile`, `RelevanceEvent` |
| Commands | `run_daily_suggestions`, `run_daily_opportunities`, `run_refitting`, `recompute_project_profiles`, `annotate_member_fit`, `backfill_slate_size`, `rerank_device` |

## Doors

- `read.py` — the models, slates and the Top-25, targets, profile vectors.
- `service.py` — the nightly runs, refits, project seeding, target selection,
  and `register_department_source`: departments have no feed of their own, so
  they are scored only for whatever registers them (the announcements do).
  Recommendation never imports that code.
- `handlers.py` — repoints scores and engagement events when retrieval merges
  two duplicate items (`retrieval.items_merging`).

## Rules that hold here

- The nightly run ranks the whole corpus and never narrows what is *ranked* to
  save cost; the model is the scarce resource, and write-ups are reused unless
  something about the item, the theme or the rubric changed.
- "New" means entered a target's Top-25 slate, never "arrived today".
- A ranking change (`pipeline.py`'s pool, `fusion.py`, `ranking.py`) needs the
  evaluation-harness re-run in `docs/evaluation.md`.

```bash
uv run --directory web/backend pytest -c pyproject.toml ../../tools/recommendation
```
