# Mylo lab reporting — four fixes

> **Status: complete (2026-08-02).** All five phases implemented; 776 content /
> integrations / core tests pass and ruff is clean on every changed file. Verified
> on the running stack: the digest link renders as
> `https://mycelium.brendondgr.com/app/daily`, the summary is counts-by-theme only,
> and PULSE Lab's real day renders to a 24-page, 242 KB PDF ("Prepared for PULSE
> Lab", 184/153/164, working table of contents) that the drain uploads to the lab's
> channel as a file. **D7 was revised after the first build** — see the decision.
>
> Four defects reported against the lab-facing half of the daily run: localhost
> links in the Discord post, a starved lab paper feed, gapped article ordering, and
> a channel summary that is neither short nor complete.

## Objective

Make the lab's daily output — the Discord channel post and the lab Research
Papers feed it summarises — correct, complete, and readable:

1. Links Mylo writes into Discord point at the real public origin, never
   `http://localhost:11050`.
2. A lab's paper feed is ranked **per cluster** and carries roughly ten papers
   per cluster instead of the handful it shows today.
3. Articles are delivered in one contiguous, sensible order (no `1 → 2 → 11 →
   12`).
4. The channel post is a clean per-cluster count summary, followed by the lab's
   full written report in the same channel.

## Root causes (verified)

### 1. Localhost link

`lab_digest.digest_embed` builds the embed URL from `settings.DISCORD_APP_BASE_URL`
(`web/backend/apps/content/lab_digest.py:226-228`). That setting falls back to
`PUBLIC_BASE_URL` (`config/settings.py:622`), which itself falls back to
`http://localhost:11050` when `PUBLIC_HOSTNAME` is blank
(`config/settings.py:39-42`). **`.env` line 5 is `PUBLIC_HOSTNAME=`** — blank. So
the whole stack is running in "localhost-only" mode while serving publicly, and
every absolute URL Mylo writes points at the operator's laptop.

This is a configuration miss, but the failure mode is silent and outward-facing:
nothing in the code refuses to publish a loopback URL to a Discord server.

### 2 & 3. Starved, gapped paper feed — one shared cause

Both symptoms come from the same place. In `suggest.generate_suggestions`
(`web/backend/apps/content/suggest.py:177-188`) ranks are assigned `1..N` over the
**whole surfaced set**, *before* the match-percent floor is applied. Then
`pipeline.recommend_for_target` runs `split_by_floor(suggestions,
PAPER_MIN_MATCH_PERCENT)` (`pipeline.py:577-587`), which hides any **LLM-scored**
paper under 60% but never hides an **unscored fallback** paper
(`digest_selection.py:68-74`). `_persist` then writes the original, now-orphaned
rank onto the rows that survive, and `SuggestionCard` renders that number verbatim
(`web/app/src/components/portal/sections/suggestion-card.tsx:80-84`).

Confirmed against the live dev database: `pulse-lab`'s latest run has suggested
ranks `[1..8, 11, 12, …]` — ranks 9 and 10 are the two LLM verdicts that scored 55%
and 50%. The reported `1 → 2 → 11 → 12` is the same mechanism with a harsher model:
ten papers went to the LLM, two cleared 60%, and the fallback tail resumed at 11.

That also explains the count. The visible feed is
`{LLM ≥ 60%} ∪ {unscored fallback tail}`, so with only ~15 candidates surfaced the
lab gets 2 + 5 = 7. Individuals are not starved because their declared areas are
specific keyword-like strings that embed close to the day's papers; a lab's areas
are the broad *theme* names `compose_clusters` produces ("AI for Oceanography"),
which sit further from any single paper, so far fewer clear the absolute
`PAPER_MATCH_THRESHOLD = 0.5` cosine gate. An absolute cosine gate is the wrong
selector for a surface whose vocabulary is deliberately broad.

Naively raising `suggestion_limit` makes this **worse**: more papers get an LLM
verdict, more fall under 60%, and more are hidden. The floor has to be addressed
together with the selection, or the fix reduces the feed.

### 4. The channel post

`digest_embed` (`lab_digest.py:178-230`) lists up to three example items per theme
with title, percent and a `· new` marker, and ends with a footer pointing at the
portal. The examples are what makes it long and unreadable in a channel, and there
is no full report anywhere in Discord — `DailyBriefing.body` for the lab is written
one stage earlier (`generate_daily_briefing`) and only ever read in the portal.

Also, `lab_digest._CATEGORY_TYPE` covers papers/grants/conferences but
`LAB_BRIEFING_CATEGORIES` covers **all four** — fellowships are silently skipped by
the digest even though a lab is scored for them.

## Assumptions and decisions

- **D1 — Public origin.** `PUBLIC_HOSTNAME` is set to `mycelium.brendondgr.com` in
  `.env` (the real fix), *and* the code stops publishing loopback URLs outward: a
  new `PUBLIC_FALLBACK_HOSTNAME` setting (defaulting to `mycelium.brendondgr.com`)
  backs `DISCORD_APP_BASE_URL` whenever the resolved origin is a loopback host. A
  misconfigured host then degrades to the right public domain instead of leaking
  `localhost` into a Discord server. Local development is unaffected — only links
  written *into Discord* use the fallback.
- **D2 — Per-cluster selection is additive, not a replacement.** For an
  institutional target (lab / lab project) declaring **≥ 2 clusters**, each cluster
  contributes its own top `PAPER_CLUSTER_TOP_N` (default 10) papers ranked by *that
  cluster's* combined score. The union is the **Mylo slate**. The existing
  threshold-passing set is still surfaced, so a lab whose feed is already generous
  never shrinks; the slate only ever adds.
- **D3 — The slate is never hidden by the match-percent floor.** A paper the
  pipeline deliberately chose as one of a cluster's ten best is shown with Mylo's
  honest percent. The floor still hides model-rejected papers *outside* the slate,
  exactly as today. Without this, D2 would shrink the feed rather than grow it.
- **D4 — One LLM call per cluster.** Ten papers per call keeps the prompt inside
  `LLM_MAX_TOKENS`, gives Mylo cluster-focused context, and means one cluster's
  model failure degrades only that cluster. Carry-forward is honoured first, so an
  already-scored paper never consumes a slot.
- **D5 — Ordering.** The surfaced list stays in global best-first score order (the
  existing, least-surprising semantic); ranks are renumbered `1..N` over the
  **visible** set only, so the numbers are contiguous. This applies to *every*
  paper feed, personal included — it is a display-integrity fix, not a lab
  behaviour change.
- **D6 — Personal feeds are untouched** by D2/D3/D4. `recommend_for_user` keeps its
  current selection and floor behaviour.
- **D7 — The full report is an attached PDF.** *(Revised after the first build.)*
  It was first shipped as chunked plain-text messages, on the reading that "posted
  into the same chat" meant readable in place. In practice a day's report is
  thousands of words and the channel became something to mute. It is now the same
  PDF a member already receives by DM, compiled for the lab
  (`daily_report.compile_report_for_lab` → the unchanged `render_report_pdf`) and
  attached to a one-line message under the summary. `enqueue_channel` gained the
  `attachment_path`/`attachment_filename` kwargs the model and `deliver_one` already
  supported.
- **D8 — Fellowships join the digest counts.** They are already scored to the lab
  and already in its written report; excluding them from the summary is a bug.

## Open questions

None blocking. One judgement worth flagging to the operator: `PAPER_CLUSTER_TOP_N`
is a placeholder default of 10 (the number in the request). It is a setting, so it
can be tuned without a code change once the first real run is observed.

## Implementation phases

### Phase 1 — public origin (defect 1)

Files: `.env`, `.env.example`, `web/backend/config/settings.py`,
`web/backend/apps/integrations/tests/test_views.py` (already pins the localhost
case — check it still holds).

1. Set `PUBLIC_HOSTNAME=mycelium.brendondgr.com` in `.env`.
2. Add `PUBLIC_FALLBACK_HOSTNAME` (env-overridable, default
   `mycelium.brendondgr.com`) and a small `_outbound_base_url()` helper in
   `settings.py`: if the resolved `DISCORD_APP_BASE_URL` host is a loopback
   (`localhost`, `127.*`, `::1`, `0.0.0.0`), use the fallback instead.
   `DISCORD_APP_BASE_URL` keeps honouring an explicit env pin above everything.
3. Document the knob in `.env.example` next to `PUBLIC_HOSTNAME`.

**Validation:** a settings test asserting that with `PUBLIC_HOSTNAME` blank and no
explicit pin, `DISCORD_APP_BASE_URL` is the public fallback, not `localhost`; and
that an explicit `DISCORD_APP_BASE_URL` still wins. Then
`compile_lab_digest` + `digest_embed` for a live lab shows the real host.

### Phase 2 — contiguous ranks (defect 3)

Files: `web/backend/apps/content/digest_selection.py`,
`web/backend/apps/content/pipeline.py`.

1. Add `renumber(suggestions) -> list[dict]` to `digest_selection.py` — assign
   `rank = 1..N` in list order. Pure, one line of logic, one place.
2. In `recommend_for_user` and `recommend_for_target`, call it on `visible`
   immediately after `split_by_floor`, before `_persist`. Hidden rows keep their
   stale rank; they are `suggested=False` and never read.

**Validation:** new tests in `apps/content/tests/test_pipeline.py` — with a stub
`complete` that scores some papers below the floor, every persisted
`suggested=True` row has a contiguous rank starting at 1, and the relative order is
unchanged. Re-run `test_suggest.py` (it asserts the pre-floor numbering inside
`generate_suggestions`, which is deliberately unchanged).

### Phase 3 — per-cluster paper selection for labs (defect 2)

Files: `web/backend/apps/content/fusion.py`, `pipeline.py`, `suggest.py`,
`config/settings.py`.

1. **`fusion.py`** — add `top_per_cluster(clustered, *, limit) ->
   dict[str, list[ClusteredHit]]`: for each cluster id present in any hit's
   `per_cluster`, rank every candidate by that cluster's own score and return its
   top `limit`. Pure, DB-free, sits beside `cap_clusters`.
2. **`pipeline.fuse_clusters_pool`** — return a third element alongside
   `pairs`/`rows`: `slate_groups: list[list[Hit]]`, one group per cluster in
   cluster order, each already ranked by that cluster's score. Surfacing itself is
   unchanged (threshold set ∪ slate, deduped, still sorted by `final_score`), so a
   lab that already sees a wide feed keeps it. `_cluster_row` is reused for any
   slate member that was not in the threshold set.
3. **`suggest.generate_suggestions`** — add an optional
   `llm_groups: Sequence[Sequence[Hit]] | None`. When given, the model is called
   once per group (each capped at `llm_limit`) instead of once over the global top
   `llm_limit`; carry-forward filtering happens per group first. When `None`,
   behaviour is byte-identical to today.
4. **`pipeline.recommend_for_target`** — pass the slate groups through, with
   `llm_limit = PAPER_CLUSTER_TOP_N`. After `split_by_floor`, move any hidden
   suggestion whose content id is in the slate back into `visible` (D3), then
   renumber (Phase 2). `recommend_for_user` passes nothing and is untouched.
5. **`settings.py`** — `PAPER_CLUSTER_TOP_N = env.int("PAPER_CLUSTER_TOP_N",
   default=10)`, documented next to the other paper-feed knobs.

**Validation:** new `apps/content/tests/test_lab_cluster_papers.py` —
- a three-cluster lab surfaces ~10 papers per cluster where the old path surfaced
  a handful (fusion-level, no DB embedder needed for the pure helper);
- a slate member scored below the floor is still `suggested=True`, while a
  non-slate LLM paper below the floor is not;
- one LLM call per cluster (count invocations of the injected `complete`);
- a clusterless / single-cluster lab is byte-identical to today;
- a **user** target is byte-identical to today.
Plus the existing `test_fusion.py`, `test_pipeline.py`,
`test_opportunity_clusters.py`, `test_briefing_clusters.py`.

Note the fusion tests' single-item gotcha: a lone candidate min-max normalises to
1.0 in every interest, so cluster-attribution tests need competing papers.

### Phase 4 — clean digest + full report in the channel (defect 4)

Files: `web/backend/apps/content/lab_digest.py`,
`web/backend/apps/content/management/commands/send_lab_digests.py`,
`web/backend/apps/integrations/services/outbox.py` (only if a length clamp is
added there).

1. **`_CATEGORY_TYPE`** gains `fellowships` (D8); `_NOUN` gains its singular.
2. **`compile_lab_digest`** stops collecting example rows. `ThemeBlock` keeps
   `label` + `counts`; `items` is dropped. `MAX_THEMES` stays (a cluster ceiling),
   `ITEMS_PER_THEME` goes. Ungrouped items collapse to a single "Other" count row
   rather than a titled list.
3. **`digest_embed`** becomes: title `"<Lab> — what Mylo found today"`, description
   the overall tally, one field per cluster whose **name is the cluster label** and
   whose **value is only that cluster's counts**, and a closing line
   `See the full report below.` The portal URL stays on the embed.
4. **`queue_lab_report(lab, *, on, workdir=None)`** — new. Compiles the lab's day
   (`daily_report.compile_report_for_lab`), renders it with the existing
   `render_report_pdf`, writes it into `DISCORD_OUTBOX_ATTACHMENT_DIR` through a
   `.part` file plus `os.replace` (the path is deterministic per lab/day, so a
   re-render must never truncate a file the drain is mid-read on), and queues one
   `outbox.enqueue_channel` row with `dedupe_key=f"lab_report:{lab.id}:{on}"`,
   `kind="lab_report"`, and the attachment. Enqueued **after** the digest row, and
   `claim_outbox_batch` orders by `(next_attempt_at, id)` while `drain` delivers
   sequentially, so the channel reads summary-then-file.
5. **`outbox.enqueue_channel`** gains `attachment_path` / `attachment_filename`,
   forwarded to `resolve.enqueue_outbox`, which already accepted them —
   `deliver_one` branches on the path, not the target type, so a channel attachment
   takes the same multipart upload a DM attachment does.
6. **`send_lab_digests`** calls `queue_lab_report` after `queue_lab_digest`, per
   lab, inside the same per-lab `try` so one lab never sinks the run. `--dry-run`
   prints the filename it would attach.
7. `outbox._on_permanent` maps a channel `lab_digest` kind onto the guild link's
   `updates` health flag — extend that mapping to `lab_report` so a broken channel
   is reported the same way.

**Validation:** extend `apps/content/tests/test_lab_digest.py` —
- the embed contains cluster names and counts and **no item titles**;
- fellowship counts appear;
- the report row carries a real PDF on disk and a one-line body, not the report
  text;
- `compile_report_for_lab` carries the lab's own matches and written briefing;
- draining actually uploads it: `POST /channels/<updates>/messages` as multipart,
  with `allowed_mentions.parse == []` intact;
- re-running the command queues nothing new (idempotency, the load-bearing
  guarantee of this module) and leaves no staging file behind;
- a lab with nothing to report posts the summary and no file;
- an empty day still posts nothing at all.

### Phase 5 — docs, changelog, and a real run

1. Update `docs/repo-map.md` rows for `lab_digest`, the paper pipeline
   (per-cluster slate), and the settings knobs.
2. Append one `MODIFIED` entry to `docs/changelog.md` with correlation ID
   `20260802-mylo-lab-reporting-fixes`.
3. Refresh the affected lab data on the running stack with `run_refitting` (the
   whole-corpus replace pass — the daily run only appends), then re-render a digest
   with `send_lab_digests --dry-run` and read it.

## Interfaces that change

| Surface | Change |
|---|---|
| `settings.PUBLIC_FALLBACK_HOSTNAME` | new (env `PUBLIC_FALLBACK_HOSTNAME`) |
| `settings.PAPER_CLUSTER_TOP_N` | new (env `PAPER_CLUSTER_TOP_N`, default 10) |
| `fusion.top_per_cluster` | new pure helper |
| `pipeline.fuse_clusters_pool` | returns a 4th element (slate groups) |
| `suggest.generate_suggestions` | new optional `llm_groups` kwarg |
| `digest_selection.renumber` | new pure helper |
| `lab_digest.ThemeBlock` | loses `items` |
| `lab_digest.queue_lab_report` | new (attaches a PDF) |
| `daily_report.compile_report_for_lab` | new (twin of `compile_report_for_user`) |
| `outbox.enqueue_channel` | new `attachment_path` / `attachment_filename` kwargs |
| `RelevanceScore.signals["rank"]` | now contiguous across `suggested` rows |
| `GET /api/labs/<slug>/recommendations/` | same shape; more papers, contiguous `rank` |

No migrations. No new endpoints. No frontend change is required — `SuggestionCard`
already renders whatever `rank` it is given, and the extra papers flow through the
existing feed.

## Security and permissions

Untouched: `eligible_labs` still re-checks `Feature.BOT_SERVER`, guild state, and
the bound channel at delivery time; the report chunks go to the same
already-verified `updates_channel_id` as the digest and carry
`allowed_mentions.parse == []` (enforced in `discord_api.create_message`), so a
report quoting a member's name can never ping them. `LabRecommendationsView` keeps
its `user_has_lab_access` gate. The written report is lab-scoped content posted to
the lab's own server — the same audience that can already read it in the portal.

## Explicit exclusions

- No change to grants / conferences / fellowships **matching**; only their counts
  appear in the new summary.
- No change to the personal daily PDF report or its DM path.
- No cluster-aware selection for the personal paper feed (D6).
- No new Discord command; no separate lab report *design* — it is deliberately the
  same PDF a person receives, not a second document to maintain (D7).
- No re-tuning of `PAPER_MATCH_THRESHOLD` or `PAPER_MIN_MATCH_PERCENT`; the
  per-cluster slate sidesteps them rather than moving them for everyone.
