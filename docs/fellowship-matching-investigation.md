# Fellowship Matching — Investigation

**Status:** diagnosis only. No code changed. Two reported defects, traced to root
cause with file/line evidence, plus the fix options and the decisions they need.

**Reported:**

1. A postdoctoral fellowship (NSF Postdoctoral Research Fellowship in Biology) is
   recommended to a second-year PhD student.
2. On a lab fellowship card, the "Best suited to" chip reads *66% profile match*
   while its own tooltip says *95% on their own feed*.

Both are real. They are **separate bugs with no shared cause**, and neither is a
model failure — both are the deterministic layer behaving exactly as written.

---

## Part 1 — Why a postdoc fellowship reaches a second-year PhD student

### The short answer

Career stage is a **soft signal**, by explicit design. A stage mismatch does not
remove a fellowship; it downgrades its tier from `qualified` to `conditional` and
subtracts 0.12 from a score that has no floor to fall below. Only three things are
hard gates: citizenship, the Illinois-student restriction, and the Women/Equity
group restrictions.

On top of that, the field that would carry the user's stage is **empty for
essentially every user**, and on lab/project feeds eligibility is **not evaluated
at all**.

There are six independent contributing causes. Each one alone is sufficient to
produce the reported behaviour.

### Cause 1 — stage is soft, not a gate

`web/backend/apps/content/fellowships.py:160-169`

```python
stage_match = (not stage_f) or bool(stage_f & elig.stage_tokens)
field_match = (not field_f) or bool(field_f & set(elig.fields))
...
if gates:            tier = "not_eligible"
elif stage_match and field_match: tier = "qualified"
else:                tier = "conditional"
```

`gates` is built only from citizenship (`:136-148`), the Illinois limit (`:151`),
and Women/Equity (`:155-157`). Stage never enters `gates`. So a stage mismatch can
only ever produce `conditional`, and `match_fellowships` drops only
`tier == "not_eligible"` (`:390`).

The scoring consequence, `fellowships.py:281-291`:

| | qualified | conditional |
|---|---|---|
| tier term (weight 0.45) | 0.45 | 0.2475 |
| stage term (weight 0.12) | 0.12 | 0.00 |

A stage mismatch costs at most **0.32 of a 1.0 rule score** — and the rule score
is then only 35% of the blended `fit` (`_RULE_WEIGHT = 0.35`, `:300`). The
effective penalty on the ranking score is roughly **0.11**. Meanwhile
`FELLOWSHIP_FIT_THRESHOLD` defaults to `0.0` (`config/settings.py:407`), so there
is no floor for the penalised item to fail.

> **Terminology:** *cosine* here means cosine similarity — the angle between two
> embedding vectors (numeric representations of text), reported in `[0, 1]` where
> 1 is identical. The "embedding" is the vector; the "cosine" is how close two of
> them are.

### Cause 2 — the user's stage field is almost always empty

`Elig.stage_tokens` is derived solely from `interests["eligibility"]["stage"]`
(`fellowships.py:101-105`), mapped through `STAGE_MAP` (`:55-60`).

That field is optional everywhere it is offered:

- Onboarding shows an eligibility step only when the Fellowships watch signal is
  on, and the panel says *"You can skip anything — defaults apply"*
  (`web/app/src/components/onboarding/onboarding-flow.tsx:1195-1197`). Nothing
  validates it (`:571-584` gates only on research areas).
- The block is nonetheless always written on finish (`:646-658`), so it exists but
  is blank.
- `eligStage` initialises to `""` (`:248`) and is pre-seeded only by clicking a
  role chip (`stageFromRole`, `:305-309`); the default role is `researcher`, which
  maps to `""`.
- The contract itself defaults it to `""`
  (`web/backend/apps/accounts/interests.py:105-107`).

So the realistic state for a typical user is `stage_tokens = set()`. Combined with
Cause 1, every fellowship that declares any stage facet lands as `conditional` —
for everybody, uniformly. The tier therefore carries **no discriminating
information**, which is why it reads as noise on the feed.

Related, and worth fixing at the same time: the LLM intake agent writes
`eligibility["career_stage"]` from a *different* five-token vocabulary
(`student / postdoc / researcher / pi / staff`,
`web/backend/apps/accounts/intake/agent.py:26, 153-157`). Nothing maps
`career_stage` → `stage`. An intake answer of `"postdoc"` is invisible to
fellowship matching.

### Cause 3 — an empty facet fails open

`(not stage_f)` evaluates to `True`, so a fellowship whose `facets["stage"]` list
is empty matches **everyone**. Roughly 3.5% of the corpus (33 of 946 scraped
records) has an empty stage list, and the two systematic scrape failure modes — a
failed Blazor detail render (`scraper/pivot/fellowships/__init__.py:107`) or a
missed `p.comments` selector — empty *all* facet buckets at once. Such a record
also gets `requires_us_citizenship = False`
(`scraper/pivot/fellowships/parsers.py:94-111`), so it fails open on citizenship
too. A scrape miss currently produces a maximally permissive fellowship rather
than a quarantined one.

### Cause 4 — the real eligibility text is never parsed

The binding constraint on the NSF award is prose, not a facet: *"must have
received the PhD within N months"*. That prose is stored, but only as display and
prompt material:

- Scraped into a list of sentences,
  `scraper/pivot/fellowships/illinois.py:179-191`; stored verbatim at
  `scraper/pivot/records.py:252`.
- 857 of 946 records carry non-empty eligibility text; ~31 lines match an explicit
  time-window pattern (`within N years`, `no more than N years postdoctoral`,
  `received the PhD`).
- Fed to the model as prose (`content/opportunity_llm.py:435-439`) and folded into
  the search document (`scraper/pivot/records.py:53-63`).
- **`evaluate_eligibility` never reads it.** It reads `facets` and `flags` only
  (`content/fellowships.py:115-193`).

Also unparsed: `metadata["note"]` (147/946 non-empty), from `p.logistics`.

Separately, the facet vocabulary is too coarse to express what is needed even when
present. `stage` is multi-valued — 2,218 stage tags across 913 records, a median
of 2–3 per record — and its five tokens (`Master's`, `Early Years of Doctoral
Program`, `Dissertation Research`, `Dissertation Write-Up`,
`Postdoctoral/Post-graduate`) cannot express "PhD conferred, within 24 months".

### Cause 5 — lab and project feeds skip eligibility entirely

`web/backend/apps/content/opportunities.py:961-969`:

```python
ranked = match_fellowships(
    items, None, today_final,
    ...
    skip_eligibility=True,
)
```

This is deliberate and documented (`:915-926`): a lab has no citizenship or career
stage, so its fellowships rank on research fit alone. `fellowships.py:379-386`
then bypasses `evaluate_eligibility` completely, emits `tier = ""`, and ranks on
the raw embedding cosine.

The intended safety valve is that *who* a lab fellowship suits is said in the
recommendation strip. But that strip is built from `member_fit`, which is **pure
cosine over the member's research-interest vector** — it has no stage input at all
(`content/member_fit.py:157-179`, floor `MEMBER_FIT_COSINE_FLOOR = 0.35`,
`config/settings.py:480`). So the lab path is:

```
no eligibility gate  →  rank by topical cosine  →  name members by topical cosine
```

There is no point in that chain where a postdoc-only award and a second-year PhD
student are ever compared. A postdoc fellowship in the student's exact subfield
will score *high* and be recommended to them *confidently*.

The `eligible` basis in `_recommended_for` does not help here. It is opt-in only
(`content/views.py:536-537`, `lab_visible`, default `False`) and it is purely
additive — it annotates a member who was already named, and can never remove one
(`:611-628`).

### Cause 6 — the model is instructed not to re-litigate eligibility, but overwrites the percent

`content/opportunity_llm.py:13-15` states the model "never re-litigates
eligibility". Yet at `:283-284` a usable model percent **replaces**
`match_percent`:

```python
if _usable_percent(enriched.get("match_percent")):
    merged["match_percent"] = enriched["match_percent"]
```

So the number the card shows is the model's research-fit judgement, produced by a
prompt that was told eligibility is already settled. The result is a high,
confident percent on an item the rule engine only ever called `conditional`. The
UI reinforces this: the subtitle promises *"fellowships you're eligible for,
matched to your stage and timeline"*
(`web/app/src/components/portal/sections/fellowships-section.tsx:558-560`).

### Worked example — NSF Postdoctoral Research Fellowship in Biology

Assume the corpus record has `facets["stage"] = ["Postdoctoral/Post-graduate"]`,
`facets["citizenship"]` including US, no Illinois/Women/Equity limit, and a US
second-year PhD student with the default empty eligibility block.

**Personal feed:**

| step | value |
|---|---|
| citizenship gate | pass |
| Illinois / group gates | pass |
| `stage_f` | `{"Postdoctoral/Post-graduate"}` |
| `elig.stage_tokens` | `set()` (Cause 2) |
| `stage_match` | `False` |
| `tier` | `conditional` — **not dropped** (Cause 1) |
| `rule_fit` | ≈ 0.25–0.45 depending on recency/stipend |
| embedding cosine | high — the abstract is biology, so is the student |
| embed gate (0.40) | pass |
| blended `fit` | 0.65·cosine + 0.35·rule_fit → passes threshold 0.0 |
| LLM overlay | writes a confident percent (Cause 6) |
| card | *Possible fit* badge + high ring percent |

**Lab feed:** eligibility never evaluated (Cause 5); ranked on cosine; the student
is named in "Best suited to" on cosine alone.

### Where the personal path is genuinely correct

Worth stating so a fix does not regress it: hard gates *do* work. An
international-students-only award is dropped for a US applicant and vice versa
(`fellowships.py:136-148`), Illinois-only awards are dropped for outsiders
(`:151`), Women/Equity awards require opt-in (`:155-157`), and closed/suspended
awards are dropped in every mode (`:373-375`). The eligible-but-irrelevant case is
also handled — the `FELLOWSHIP_MATCH_THRESHOLD = 0.4` cosine gate
(`config/settings.py:408`) is what stops an agriculture scholarship reaching a
computer scientist. **Stage is the one dimension with no gate.**

---

## Part 2 — Why the chip says 66% and the tooltip says 95%

### The short answer

They are two different numbers computed from two different pairs of vectors by two
different subsystems, and the UI labels the smaller one "profile match" while
sourcing the larger one from the member's own feed. Neither is wrong; the card
presents them as if they were the same quantity.

### The two quantities

**66% — `member.fit`.** From `member_fit.py:404`:

```python
"fit": round(similarity * 100),
```

where `similarity = cosine(item_vector, candidate.vector)`
(`member_fit.py:174-177`) — the raw cosine between the fellowship's embedding and
the member's *profile* embedding. No LLM, no fusion, no calibration. Raw cosines
between two short text embeddings sit naturally in the 0.4–0.7 band; 0.66 is a
**strong** cosine.

**95% — `member.match_percent`.** From `content/views.py:603, 610`, sourced from
`_interested_members` (`:481-497`), which reads the member's own personal
`RelevanceScore.signals["match_percent"]` — and that value is, for any
LLM-scored row, **the language model's 0–100 fit judgement**
(`opportunity_llm.py:283-284`; serializer note at `serializers.py:110-113`). Only
when the model did not score the row does it fall back to a cosine ×100.

So: **66 is a geometric measurement; 95 is a model's opinion on a 0–100 scale.**
LLMs asked for a percent cluster high and use the 80–100 band freely. The two
scales are not comparable, and a ~30-point gap between them is the expected
steady state, not an anomaly.

### Bug 2a — the label claims they are the same thing

`web/app/src/components/portal/primitives/recommended-for.tsx:112-124`:

```ts
if (typeof member.fit === "number")     parts.push(`${member.fit}% profile match`);
if (member.basis.includes("own_match")) parts.push(`${member.match_percent}% on their own feed`);
```

One tooltip, two incompatible scales, adjacent, separated by a middot. The visible
chip shows only `member.fit` (`:79-81`). `basisNote` repeats the second number
(`:140-142`), and `describeBasis` states it as a bare fact (`:129`). Nothing tells
the reader the numbers measure different things.

Your instinct that 95% is the right number to show is defensible — it is the
member's own calibrated feed value, the one they will see when they open their
personal page, and consistency across surfaces matters more here than which
estimator is technically purer. But note it is only available for members who
cleared `INTEREST_MATCH_THRESHOLD = 70` on their own feed
(`content/views.py:48, 490`); for a `profile_fit`-only member there is no 95 to
show. Any fix has to decide what that member's chip displays.

### Bug 2b — `fit` is polymorphic

This is the sharper defect. `_recommended_for` assigns `fit` from two different
sources depending on which basis created the row:

- `content/views.py:590` — row created from `member_fit` → `fit` = **cosine ×100**
- `content/views.py:603` — row created from `own_match` alone → `fit` = **the LLM
  match_percent**
- `content/views.py:621` — row created from `eligible` alone → `fit` = **`None`**

So on a single card, two chips labelled identically can be reading from different
estimators. A member with a strong profile cosine but a sub-70 personal match
shows ~66; a member with no stored profile vector (and therefore no `member_fit`
row at all) but a 95 on their own feed shows 95. The lower number is
systematically attached to the members Mylo actually reasoned about.

### Bug 2c — the ordering inherits the mix

`content/views.py:630-633`:

```python
out[cid] = sorted(rows.values(), key=lambda r: (-(r.get("fit") or 0), r["username"]))
```

Sorting a mixed-scale column ranks `own_match`-only members above `profile_fit`
members almost unconditionally, purely because the LLM scale runs hotter. The
member Mylo wrote a rationale for gets pushed down the strip; `RecommendedFor`
then treats `members[0]` as the lead and opens *that* member's reason by default
(`recommended-for.tsx:36-38`). The most-explained recommendation is the least
likely to be shown expanded.

### Bug 2d — a third number on the same card

`fellowships-section.tsx:208` renders the ring from `item.match_percent` — on a
lab feed, the **lab's** score for the item, which on the fellowship path is the
lab-interest cosine ×100 possibly overwritten by the lab-scope LLM percent. So one
lab fellowship card can display three unrelated percentages: the lab ring, the
member cosine chip, and the member's personal LLM percent in the tooltip. Nothing
on the card distinguishes their scopes.

---

## File reference

| Concern | Path | Lines |
|---|---|---|
| Eligibility tiering; stage as soft signal | `web/backend/apps/content/fellowships.py` | 115-193 |
| Rule fit weights | `web/backend/apps/content/fellowships.py` | 281-291 |
| Blend, `match_percent`, drop rules | `web/backend/apps/content/fellowships.py` | 296-460 |
| `Elig` built from profile | `web/backend/apps/content/fellowships.py` | 83-109 |
| Personal fellowship pass | `web/backend/apps/content/opportunities.py` | 294-345, 805+ |
| Lab/project pass (`skip_eligibility=True`) | `web/backend/apps/content/opportunities.py` | 904-1010 |
| LLM overlay; percent overwrite | `web/backend/apps/content/opportunity_llm.py` | 219-300, 283-284 |
| Member cosine + `fit` | `web/backend/apps/content/member_fit.py` | 157-179, 389-410 |
| `_interested_members` (70% floor) | `web/backend/apps/content/views.py` | 470-497 |
| `_consented_eligibility` (opt-in) | `web/backend/apps/content/views.py` | 520-539 |
| `_recommended_for` (basis merge, mixed `fit`) | `web/backend/apps/content/views.py` | 542-634 |
| Feed serializers | `web/backend/apps/content/serializers.py` | 110-120, 217-225 |
| Eligibility contract | `web/backend/apps/accounts/interests.py` | 64-141 |
| Intake writes `career_stage` only | `web/backend/apps/accounts/intake/agent.py` | 26, 153-157 |
| Facet scrape + vocabulary | `web/backend/apps/scraper/pivot/fellowships/parsers.py` | 24-49, 65-91, 94-136 |
| Free-text eligibility capture | `web/backend/apps/scraper/pivot/fellowships/illinois.py` | 179-191, 240-257 |
| Metadata assembly | `web/backend/apps/scraper/pivot/records.py` | 236-261 |
| Chip + tooltip | `web/app/src/components/portal/primitives/recommended-for.tsx` | 79-81, 112-153 |
| Ring + tier badge + subtitle | `web/app/src/components/portal/sections/fellowships-section.tsx` | 114-137, 208, 549-563 |
| Onboarding eligibility step | `web/app/src/components/onboarding/onboarding-flow.tsx` | 154-168, 288-290, 646-658, 1185-1331 |
| Thresholds | `web/backend/config/settings.py` | 407-408, 421, 480-481 |

---

## Fix options

Diagnosis only — nothing below is implemented. Ordered by leverage.

### Part 1 — make stage bind

**F1 · Promote stage to a hard gate, asymmetrically.** *(highest leverage,
smallest diff)*

Not a symmetric gate. "Postdoc-only award, applicant is pre-PhD" is a hard
disqualification; "PhD-student award, applicant is a postdoc" is often merely
odd. Introduce an ordered stage ladder
(`masters < doctoral_early < doctoral_dissertation < postdoc`) and gate only when
the award's *minimum* stage exceeds the user's — i.e. add to `gates` in
`fellowships.py:135-157` when `min(stage_f) > user_stage`. Leaves everything else
soft. This alone kills the reported case on the personal feed.

**F2 · Require stage before the fellowship feed is trusted.** Cause 2 makes F1
inert without this. Options: make the onboarding eligibility step mandatory when
Fellowships is on; derive `stage` from `academic_title` / `career_stage` (a real
mapping, not the current no-op); or gate the fellowship feed behind a "set your
stage" empty state rather than showing an ungated feed. **This is a product
decision, not just an engineering one** — it trades onboarding friction for feed
correctness.

**F3 · Parse the free-text eligibility into structured constraints.** One LLM
extraction pass at ingest over `metadata["eligibility"]` → a
`metadata["constraints"]` block (`{min_stage, max_years_post_phd, degree_required,
...}`), then gate on it. Handles the NSF "within N months of PhD" class that no
facet can express. Higher cost, and the highest-fidelity fix.

**F4 · Fail closed on a scrape miss.** Mark a record whose facet buckets are
entirely empty as `facets_incomplete` and either withhold it or tier it
`unverified` rather than letting it match everyone (Cause 3).

**F5 · Gate the lab-side recommendation, not the lab feed.** Keep
`skip_eligibility=True` for the lab *feed* — a lab genuinely has no stage — but
run each named member's own eligibility inside `member_fit` / `_recommended_for`
and **drop** members who hard-fail. This inverts today's opt-in `eligible`
annotation from additive to subtractive. Note the D-11 privacy constraint: today
eligibility is disclosed only with `lab_visible` consent. Silently *omitting* an
ineligible member leaks less than naming them, so this is likely compatible — but
it needs an explicit privacy call.

**F6 · Let the model see eligibility, or stop letting it overwrite the percent.**
Either include the stage verdict in the fellowship prompt so the reason and percent
reflect it, or clamp `match_percent` on a `conditional` row (`opportunity_llm.py:283-284`).
Cheap; prevents a confident number on a hedged item.

**F7 · Fix the copy.** *"fellowships you're eligible for, matched to your stage"*
(`fellowships-section.tsx:558-563`) is not true while stage is soft and usually
unset. Fix it whether or not F1–F6 ship.

### Part 2 — make the percentages coherent

**F8 · Pick one scale per label and name its scope.** The core fix. Decide whether
the chip shows the calibrated personal feed percent (your preference — consistent
with what the member sees on their own page) or the profile cosine, then use it
for *every* member on the strip and label it with its scope: *"95% on their feed"*
vs *"66% profile fit"*. Never present both as an undifferentiated middot list
(`recommended-for.tsx:112-124`).

**F9 · Stop overloading `fit`.** Emit two explicit fields from
`_recommended_for` — `profile_cosine` and `own_feed_percent` — instead of one
polymorphic `fit` (`views.py:590, 603, 621`). Fixes 2b, and makes 2c fixable.

**F10 · Sort on one scale.** Rank the strip on whichever field F8 selects, with a
defined tiebreak for members missing it (`views.py:630-633`), so the member Mylo
explained is not demoted by scale mismatch.

**F11 · Disambiguate the ring on lab cards.** Label the ring's scope on a lab feed
("matched to *lab name*") so the lab-scope percent is not read as a personal one
(`fellowships-section.tsx:208`).

---

## Decisions needed before implementing

1. **Is stage a hard gate, and in which direction?** F1's asymmetric ladder, or a
   symmetric gate, or soft-but-heavily-penalised?
2. **Is setting stage mandatory when Fellowships is on?** Determines whether F1
   does anything for real users.
3. **Which percent does the chip show?** You favour the 95 (own-feed) value —
   confirm, and decide what a `profile_fit`-only member with no own-feed score
   displays.
4. **Does D-11 permit silently dropping an ineligible member from "Best suited
   to" without their `lab_visible` consent?** F5 depends on it.
5. **Is an ingest-time LLM extraction pass (F3) in scope,** or is facet-level
   gating sufficient for now?

Per `docs/skills/global.md`, whichever of these ship must also audit
`manual_all.py` — the nightly chain scores only that day's new items and appends,
so a gating change alters new rows only. Existing wrongly-surfaced rows persist
until an on-demand refit (`run_refitting`), which is sign-up/profile-edit only and
must not be scheduled into the daily chain.
