# Plan — Unified Search: per-type filters & sticky rail

## Objective

Refine the just-shipped `/app/search` filter rail per user direction:

1. **Remove "Source"** everywhere on the search path — the facet, the filter
   param, and the source line on each result card. Not wanted, not needed.
2. **Sticky filter rail** — the left `Filters` column stays pinned as results
   scroll.
3. **Per-type filters** — Papers, Grants, Fellowships, and Conferences each get
   their own relevant facet, shown contextually when that type is the sole
   active type filter.
4. **Conferences** — completes the set with its own facet (already a type; now
   filterable like the rest).

## Key finding (grounds the design)

Every type carries one clean, low-cardinality scalar in `metadata` that makes a
good facet (confirmed over the live corpus):

| Type | Facet field (`metadata->>…`) | Cardinality note |
| --- | --- | --- |
| paper | `year` | 2 values in corpus — ideal |
| grant | `sponsor` | high, but capped to top-N over the match set |
| fellowship | `award_class` | 5 clean values (fellowship/scholarship/award/…) |
| conference | `country` | ~70, capped to top-N over the match set |

Facets are already computed over the **lexical match set only** (small per
query), so grouping by a JSONB key there is cheap. All four are single scalar
keys → groupable via `KeyTextTransform` and filterable as text (facet value and
filter value are the same `->>` text, so a clicked chip always round-trips).

## Locked decisions

- **F1 — contextual, not all-at-once.** The per-type facet renders only when
  exactly one `type` is selected. No type (or several) selected ⇒ just the Type
  group. This matches "drill into a type, then its filters appear" and keeps the
  API light (compute at most one metadata facet per request).
- **F2 — text-keyed facets + filters.** Backend emits/consumes `->>` text for
  year/sponsor/award_class/country so click-to-filter is exact. Selecting a
  facet naturally scopes to that type (only that type has the key).
- **F3 — standard facet counts.** The Type facet counts ignore the type filter
  (as today); a per-type facet's counts ignore its own selection (so multi-select
  stays legible) but honor query + date + type.
- **F4 — drop `source` from the result payload too.** Nothing else reads it;
  removing it from the serializer + type keeps "we don't need it" honest.

## Phases (each ends green before commit)

### Phase A — Backend search core (`apps/content/search.py`)
- `SearchFilters`: drop `sources`; add `years`, `sponsors`, `award_classes`,
  `countries` tuples.
- `_apply_filters(qs, filters, *, include_type, include_metadata=True)`: drop the
  source filter; add text-equality metadata filters (`year`/`sponsor`/
  `award_class`/`country`) via a `KeyTextTransform` annotation + `__in`.
- `_metadata_facet_counts(base, key, q, *, limit)`: group the lexical match set by
  a JSONB text key, drop blanks, top-N by count.
- `run_search`: build `facets = {"type": …}` and, when exactly one type is
  active, add that type's facet computed over `query+date+type` (its own metadata
  filter excluded). Drop the `source` facet. `_empty_result` → `{"type": []}`.
- **Validate:** `uv run --directory web/backend python -m pytest apps/content/tests/test_search.py` (update source-based cases to the new fields).

### Phase B — Backend view (`apps/content/views.py`)
- Parse `year`/`sponsor`/`award_class`/`country` (repeatable/comma via
  `_multi_param`); drop `source`. Update docstring.
- **Validate:** endpoint tests (shape, type-filter, new facet keys, auth).

### Phase C — Frontend data layer (`types.ts`, `client.ts`, `hooks.ts`)
- `SearchFacets`: `type` + optional `year`/`sponsor`/`award_class`/`country`.
- `SearchResultItem`: drop `source`.
- `SearchParams`/`SearchInput`/`fetchSearch`/`useSearchResults`: drop `sources`;
  add the four per-type arrays; extend the query key.
- **Validate:** `tsc --noEmit`.

### Phase D — Frontend UI (`search-section.tsx`, `search-result-card.tsx`)
- Rail: `lg:sticky lg:top-6 lg:self-start` + capped height/scroll. Keep Type
  group; render the one contextual per-type group when a single type is active.
  Generalize `toggleFacet`/`clearFilters`/URL sync to the new param set.
- Card: remove the `{item.source}` line.
- **Validate:** `tsc`, `eslint`, `next build`; live check via the gateway.

### Phase E — Docs, changelog, commit
- Update `docs/api-contract.md` (search params + facets shape), `docs/repo-map.md`
  if needed, `docs/changelog.md`, memory note. Commit (no push).

## Interfaces that change

- `GET /api/search/`: **remove** `source` param + `facets.source`; **add**
  `year`/`sponsor`/`award_class`/`country` params + contextual `facets.<field>`;
  result objects lose `source`.

## Validation & acceptance

- Content test suite green on a Postgres test DB (full migration chain).
- `tsc`, `eslint`, `next build` clean; live `/app/search` returns per-type facets
  when one type is selected and honors the new filters end-to-end.
- No `source` anywhere on the search path (grep clean).

## Exclusions

- No new metadata indexes (facets run over the already-cheap match set); revisit
  only if a facet field proves hot.
- No multi-facet-per-type (one scalar each) — deferred until asked.
- No changes to the digest/opportunity pages or their own filters.
