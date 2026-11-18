# EXP-2026-11-023 — Protocol

Written 2026-11-18, before any paper was imported into the copy and before the
first search. This is the first run of collaborator search on real people. It
uses the "would you contact this person?" measure registered in
`EXP-2026-09-012` (measure 5) and leaves that experiment's own protocol as it
is: 09-012 is about seekers judging their own live searches over weeks; this is
one department, searched once, judged by one person who knows everyone in it.
That is a different design, so it gets its own folder rather than an amendment.

## Question

For each faculty member of one real department (FSU Department of Scientific
Computing, 14 core faculty), what does Mycelium's collaborator matcher suggest
when they ask who in the department to work with on their own research — and,
once rated, what share of those suggestions would that person contact?

The demo paper says collaborator search "was tested on invented people only; we
do not know whether it suggests people a researcher would contact". This run
produces the suggestions and the rating sheet. The rating itself is a later
amendment.

## Hypothesis

Exploratory — no prior hypothesis on the rating. Two structural expectations,
stated now because they follow from the code, not from the data:

1. A person with no read papers cannot be suggested at all: the in-field and
   problem-bridge lanes need demonstrated `works_on` concepts or work facets,
   and the method bridge needs a known OpenAlex field (`apps/collab/matcher.py`
   `_work_hits`, `_concept_hits`). Students whose papers are not imported, and
   the one existing open account (declared profile only), will never appear.
2. Lab-mates and existing co-authors are excluded by design
   (`eligible_candidates`), so a faculty member's own students and their
   existing collaborators in the department will not be suggested.

## Setup

- **System under test:** `apps/collab/matcher.py` at the commit recorded in
  `manifest.yaml` (code frozen with `git archive` for the run), through the
  product entry points: `matcher.query_for_text(seeker, text)` (the slot reader
  reads the typed text into requirement slots) then `matcher.search(seeker,
  query)` (gate, four lanes, shortlist of 8 per lane, model rerank that can drop
  but never add, 3 shown per lane). Settings as deployed except the in-process
  changes listed below.
- **Database:** `mycelium_sandbox_fsusc`, a `pg_dump | pg_restore` copy of the
  live database taken 2026-11-18 inside the postgres container. The live
  database is only read (by the dump). Every write below goes to the copy. The
  sandbox guard (`sandbox/collab/bootstrap.py`) refuses any other database name.
- **In-process changes (harness only, no product code changed):**
  - the department's stand-in accounts have the email domain
    `fsu-sc.mycelium.invalid`, which the institution directory does not know; the
    harness makes `affiliation.resolve_email` resolve that domain to the
    directory entry for `fsu.edu`, so they are placed where their real addresses
    would place them;
  - `COLLAB_SEARCH_ENABLED` on (it is off on the instance), billing enforcement
    off;
  - the weekly appearance cap (10) and the daily search limit (20) raised to
    effectively unlimited, so each seeker is searched as if they were the first
    seeker of the week. The cap exists to protect candidates in live use; here
    it would only make the 14th seeker's list depend on the order of the run;
  - `WRITEUP_LLM_CONCURRENCY` = 4 and searches four seekers at a time: at most
    four model requests in flight.
- **Model:** the instance model on relay endpoint `default-model` (Gemma 4 31B
  according to the maintainer; its self-report is recorded at run time), shared
  with live use, at most 4 requests in flight. Used for three things only:
  reading each imported paper into facets (`apps/knowledge/works.py`), reading
  the typed query into slots (`apps/collab/slots.py`), and the rerank. The
  decision server is never called. Temperature as deployed (0.2).
- **Container:** a one-off `docker compose run --rm --no-deps` backend container
  as the host user, `docs/research` and a private directory outside the
  repository mounted writable.

## Data

**People.** The 14 core faculty listed in the maintainer's private reference
document on the department (compiled 2026-11-12 from public department and
personal pages). 13 already have stand-in accounts in the live department
(seeded 2026-11-15 from the same document, profiles drafted by Mylo's intake
synthesis, declared edges only, no papers). The 14th has an existing account
that predates the stand-ins and is unverified; existing accounts are not
modified, so the harness makes a **copy-only stand-in** for that person in the
same lab, with the existing account's declared interests copied (read) into it.
10 PhD-student stand-ins exist; they are candidates, never seekers. One other
account in the department was already open to collaboration before this run; it
is left exactly as it is.

**Anonymous ids.** Faculty are F01–F14 and students S01–S11, assigned by a
seeded random shuffle (not alphabetical, not by account order). The id → person
mapping, the stand-in emails and the OpenAlex ids are kept outside the
repository with the maintainer. Nothing in this folder names a person, gives an
identifier such as an ORCID, or quotes a paper title.

**Opt-in.** In the copy only, every stand-in (14 faculty, 10 students) is opted
in with `consent.update(user, open=True, audience="institution", open_to=[])`.
In live use each person would choose this themselves; nobody real has.

**Papers.** Each person's works come in through the product's own import path,
as an operator provisioning an account from an author id does
(`apps/accounts/provisioning.py`): `intake.import_author(<OpenAlex author id>,
"openalex")` (the 50 most-cited works of that author record), the profile's
`openalex_id` set, `author_works.store_author_works(user, draft,
source="openalex", verified=True)`, then `knowledge.papers.refresh_person(user)`
— the body of the `facet_user_works` task an import queues (field lookups,
facet reading by the model, vectors, demonstrated edges). Then the
co-authorship graph is rebuilt (`coauthorship.rebuild`).

**Choosing the author record** (done before this protocol, recorded privately
for the maintainer to confirm):
- ORCID from the reference document first; otherwise an OpenAlex author search
  on the name filtered to the institution, then without the filter;
- a record is accepted when works the reference document lists for the person
  (by DOI or title) resolve to it; when several records exist, the one holding
  the listed works and the most works is used, and the others are noted;
- a record that also holds other people's papers (a conflated record) is still
  imported as it is — that is what the product would do with it — and flagged
  for the maintainer;
- **students** are imported only when a record has the institution (or a
  partner national lab) as an affiliation **and** at least one work on a topic
  the reference document lists for them; otherwise not imported and noted.
  Students of the lab whose accounts predate the stand-ins are not touched.
- OpenAlex is called with the instance's API key and a generic user agent; no
  contact address is sent.

**Judgments.** None yet. The rating is done later by **one rater, the
maintainer, who knows every person in the department personally**. It is not
blind: the rater knows who the seeker and each candidate are, and knows the
department's existing collaborations. The rater judges on the seeker's behalf
("would F0x contact this person about this?"), which is a proxy for the
seeker's own judgment, not the seeker's own judgment.

## Query rule

One query per faculty member, fixed before the run:

> Who in the department should I collaborate with on `<the "Research areas"
> line of their entry in the reference document, verbatim>`?

The slot reader turns this into at most six slots (exactly one `problem`).
Only one query per person, even for people with clearly distinct areas, so no
per-person judgment enters the query; that limitation is reported.

## Procedure

1. Copy the database (done once; never `CREATE DATABASE … TEMPLATE`, which
   fails while live connections are open).
2. `run023.py check` — confirm the copy, the roster, zero searches.
3. `run023.py prepare` — copy-only stand-in, opt-in, imports and paper reading.
4. `run023.py search` — per faculty seeker: the gate diagnostic (who is open,
   who is excluded as a lab-mate or co-author), `query_for_text`, then
   `search` with the rerank on. The harness wraps `matcher._rerank` to record
   each lane's full shortlist (retrieval order, before the model) and the
   model's keep/drop and reason per candidate. **The no-model retrieval order
   is the shortlist as recorded:** with no model the product shows the first 3
   of each lane's shortlist, so it is read off the same search rather than from
   a second search with the same slots (which the day's cache would answer).
   One retry, pre-registered: if a search comes back unexplained (the rerank
   unavailable), that seeker's search log and appearances in the copy are
   cleared and the search run once more; both attempts are kept.
5. `run023.py export` — the private rating rows (`ratings_input.json`: per
   seeker, every candidate shown with the model, plus any candidate the model
   dropped that the no-model order would have shown, flagged as such; evidence
   as paper titles or declared terms; the model's reason) and the anonymised
   public logs (counts, lanes, tiers, ids).

```bash
docker compose exec -T postgres sh -c 'createdb -U mycelium mycelium_sandbox_fsusc && pg_dump -U mycelium -Fc mycelium | pg_restore -U mycelium -d mycelium_sandbox_fsusc --no-owner'
git archive <commit> tools web/backend | tar -x -C <frozen>
R="docker compose run --rm --no-deps -T --user $(id -u):$(id -g) -e HOME=/tmp \
   -e SANDBOX_DB=mycelium_sandbox_fsusc -e LLM_MODEL=default-model \
   -v <frozen>/tools:/app/tools:ro -v <frozen>/web/backend:/app/web/backend:ro \
   -v $PWD/web/backend/media:/app/web/backend/media \
   -v $PWD/docs/research:/app/docs/research -v <private dir>:/private backend \
   uv run --no-sync --project web/backend python \
   docs/research/experiments/EXP-2026-11-023-collab-live-fsu-sc/code/run023.py"
$R check && $R prepare && $R search && $R export
```

## Metrics

Now (no judgments): per seeker, slots read, candidates the gate let through,
exclusions by reason, suggestions shown per lane and in total, seekers with
zero suggestions and why, the rerank's drops, and works imported and read per
person. Counts only; no rate is a quality measure until rated.

After rating (the later amendment), from `EXP-2026-09-012` measure 5:

- **Primary:** would-contact rate = share of shown suggestions rated **yes**,
  with **yes or maybe** reported beside it; per lane, with n, and pooled with a
  Wilson 95% interval. Unit: one (seeker, candidate) suggestion.
- The same rates for candidates the model dropped that the no-model order would
  have shown — whether the rerank's drops were right.
- Per seeker: whether at least one suggestion was rated yes.

## Baselines

The no-model retrieval order (the first 3 of each lane's shortlist) against the
model-reranked list, on the same search. No other system is compared.

## What would falsify this

Registered now for the rating amendment: the matcher is read as suggesting
people a researcher would contact if at least half of shown suggestions are
rated yes or maybe; as not doing so if fewer than a quarter are; between the
two, as unresolved at this n. Separately, `EXP-2026-09-012`'s bar stands: a
bridge lane whose yes rate is not above the in-field lane's counts against the
design's claim that the bridges add value. One rater who knows the people is a
single, non-blind judgment; a result either way is reported as that.

## Deviation 1 — a second query arm (written 2026-11-18 at 17:39Z, after the first search, before the second)

**What happened.** The pre-registered query (arm `product`, the typed text read
by the slot reader) ran for all 14 seekers at 17:36–17:37Z. For **7 of 14** the
slot reader returned **no slots**, so those searches had nothing to match and
showed nobody. A diagnostic rerun of the reader alone (`code/diag_slots.py`,
same 14 texts, raw replies kept privately) gave the same 7: the model answered
`{"slots": [], "thin": false}` each time — the reader's prompt asks it to read a
*funding call*, and for half the faculty it decided the typed question names
nothing a call would ask for. For the other 7, every slot read was one the
seeker already covers, so only the in-field lane ran and 1–3 people were shown
(bridges need an uncovered slot). Arm `product` is kept and reported exactly as
it ran; it is the honest answer to "what does the product show today".

**Arm `manual`, added.** To give every seeker a rating sheet, each seeker is
searched a second time with slots built mechanically from the same "Research
areas" line, skipping the slot reader (the entry the brief allowed:
`matcher.Query("manual", matcher._with_vectors(slots),
need_fields=matcher._fields_of([seeker]))`):

- the line is split on `;`; each area, stripped, becomes **two** slots with the
  same text — one `problem`, one `method` — both `required: false`. No area is
  classified by hand: an area that is a problem can then be answered as a
  problem, one that is a technique as a method, and the gate and lanes decide
  the rest (covered areas feed the in-field lane; uncovered ones the bridges);
- everything else as in the original procedure (`matcher.search`, rerank on,
  shortlist recorded, one retry if unexplained).

The rating sheet merges both arms per seeker: every candidate shown in either
arm, plus candidates the model dropped that the no-model order would have
shown, each tagged with the arm(s), lane and whether the model showed it. Lane
shortlist positions 4–8 (never shown by the product) are included separately as
optional extras, flagged, so the rater can choose to rate deeper. Rates are
reported per arm and pooled, never mixed silently.
