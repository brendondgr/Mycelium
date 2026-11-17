# Collaboration Matching for Research Systems — Design Summary

> **Source design for the `collaboration-network/` plan series.** Kept verbatim
> as written on 17 September 2026; the plans in this folder cite it by section
> (`design §4`). Where a plan departs from it, the plan says so and why. When
> the series has shipped, the durable parts (the facet and lane model, the hard
> constraints, the prior art) move to `docs/architecture.md` and
> `docs/research/RELATED_WORK.md`, and this file is deleted with the plans.

**Status:** design only, nothing built.
**Date:** 17 September 2026.
**Origin:** worked out for Mycelium (a research intelligence platform that delivers paper, grant, and conference digests to academic labs), but written here to be portable. Section 14 separates the portable design from the host-system specifics.

**How to read this if you are evaluating it for a different system:** Sections 1–7 are the design. Section 8 is the interface. Sections 9–13 are constraints, sequencing, and open decisions. Section 14 tells you which parts assume the host system and which do not.

---

## 1. Goal

> Starting from a project or funding call that a researcher chooses to search from, return two distinct kinds of people: those in the same field who could share the work, and those from other fields who bring something the work is missing.

Two properties of this goal drive the whole design:

1. **It is opportunity-triggered, not directory-browsing.** The search starts from a concrete thing (a grant call, a project) that defines what is needed. It does not start from a blank search box.
2. **It must return near and far matches at once.** These are not two thresholds on one similarity score. They are structurally different queries.

---

## 2. Why the obvious design fails

The obvious design is a graph of `Researcher —[interested in]→ Topic ←[interested in]— Researcher`, matched by embedding similarity. Four problems:

| Problem | Explanation |
|---|---|
| It finds peers, not partners | Two people who both declare "machine learning" are as likely to be competitors as collaborators. Similarity is a filter for whether two people can talk to each other, not a reason for them to work together. |
| It is not really a graph | If clusters are free text and matching is cosine similarity, this is nearest-neighbour search with graph infrastructure attached. A graph only earns its place on multi-hop questions (see §7). |
| It has already been published | See §15 (CM4AI talent knowledge graph, Unlikely Pairs). The naive version is prior art, not a contribution. |
| It is one-sided | Collaborator matching is a *reciprocal recommendation* problem, like job matching or dating: the match only succeeds if both parties want it. Naive ranking concentrates recommendations on a few popular people, exhausting their capacity and lowering the total number of matches. |

### 2.1 The specific failure for cross-field matching

Whole-profile similarity cannot find useful out-of-field people, because:

- Scientific document encoders measure **community**, not conceptual compatibility. SPECTER/SPECTER2 are trained with a triplet loss that pulls citing and cited papers together. OpenAlex topics were built by clustering the citation network into research communities.
- People in different fields rarely cite each other, so a citation-shaped space keeps them far apart by construction.
- General-purpose encoders (e.g. bge-small) are not citation-trained but have the same practical issue: whole-profile vectors are dominated by field vocabulary.

**Consequence:** you cannot find a useful outsider by looking far from the user. Far-from-the-user alone is noise. You find them by looking *close to one specific part of the need* while being *far from the user's field*.

---

## 3. Core design: facet decomposition

Represent both sides of the match — the need and the person — with the same small set of facets.

| Facet | On the need side (project / grant) | On the person side (their papers) |
|---|---|---|
| Problem | What the work is trying to solve | Problems they have worked on |
| Method | Techniques the work requires | Techniques they have used |
| Setting / data | Data, cohort, instrument, field site | Data and settings they work in |
| Offer | — | What an outsider could concretely reuse from their work (a method, dataset, baseline, protocol) |
| Need | Requirements the profile does not cover | — |

Matching is then defined by *which facet must match and which must differ*, rather than by an overall score.

**Precedent:** this is the structure used in computational analogy research. SOLVENT annotates papers by background, purpose, mechanism, and findings and finds more cross-domain analogies than baseline retrieval. Hope et al. learn separate purpose and mechanism vectors and retrieve analogies at better precision and recall than traditional IR. Related work assumes that "same purpose, different method" and "same method, different purpose" pairs are the innovative ones.

---

## 4. The lane model

Each lane is a separate retrieval with its own matching rule. Lanes are **not** merged into one ranked list (see §9.1).

| Lane | Must match | Must differ | What the person is |
|---|---|---|---|
| In-field | Problem + setting | — | A peer who could share the work |
| Method bridge | Method ↔ the need's required method | Setting (field) | Someone who can transfer a technique |
| Problem bridge | Problem | Setting + method | Someone attacking the same problem differently |
| Resource | Their offer ↔ the need's data requirement | — | Someone who holds the data, cohort, or instrument |

**Worked example.** Project: detecting coral bleaching in drone imagery.

- In-field → reef ecologists working on bleaching.
- Method bridge → medical-imaging groups doing lesion segmentation in image time series.
- Problem bridge → wildfire or crop early-warning modellers.
- Resource → whoever publishes labelled reef survey data.

**User-facing rollup.** Show two groups, not four lanes:

- **Fills a gap** = method bridge + problem bridge + resource, applied to uncovered requirements.
- **Shares expertise** = in-field, applied to requirements the user already covers.

Each result carries a small label naming the lane it came from.

---

## 5. Expertise representation requirements

What "understanding expertise" has to mean in practice. The requirement is that it be **decomposed**, not deep.

1. **Facets per paper, not per person.** Extract the facets in §3 from each paper once, independent of any reader, and cache. Aggregate to the person at query time.
2. **Document-centric retrieval.** Rank paper-level facets, then credit their authors. In expert-finding research, document-centric methods generally outperform profile-centric ones (a single merged pseudo-document per person). One study also found that elaborate author-position weighting did not improve retrieval, so do not over-engineer contribution weights.
3. **Never average a person into one vector.** People with mixed expertise get flattened into a vector representing none of their areas. Keep per-cluster or per-paper vectors and take the best-matching one.
4. **Evidence tiers on every capability.** Mark each as *declared* (the person said so) or *demonstrated* (their publications show it), with recency. Declared-only claims are cheap to make and should be visibly weaker.
5. **Field-neutral phrasing for cross-field lanes.** "Data assimilation" and "state estimation" overlap mathematically but will not reliably match as text. The extraction step should emit both the field-specific phrasing and an abstracted one ("estimating a hidden state from noisy observations"). Keep both: abstracting too far makes everything match ("uses statistics").
6. **A ruler for "field."** Cosine similarity is continuous and gives no boundary for "outside my field." Use a taxonomy for distance only. OpenAlex provides 4 domains → 26 fields → 252 subfields → 4,516 topics. Topic-level assignment is noisy (one analysis reports average top-1 accuracy near 0.53, rising to about 0.72 when all metadata is present), so use the field or domain level. This measures distance only; it never replaces a user's own labels.

---

## 6. Matching pipeline

```
need (project | grant | typed query)
  → decompose into requirement slots (problem / method / data)
  → mark coverage: which slots the seeker already covers
  → per lane: retrieve candidate papers by facet similarity
  → aggregate papers to authors, with evidence tier and recency
  → filter: consent + audience scope + appearance cap   [hard gate, see §7 and §9]
  → rerank top slice with an LLM verdict + one-line rationale
  → return grouped by lane, never merged into one ranking
```

**Cost shape.** Cheap retrieval over many candidates; expensive per-candidate reasoning only on the shortlist. Facet extraction is one model call per paper, ever, shared across all users and all searches.

**Slots, not prose.** Drive the search from structured requirement slots. Free-text "caveat" or weakness prose written for a human reader is too loose to launch a search from; use it only as a fallback when slot extraction fails.

---

## 7. Consent and availability model

Expertise alone is not enough; you need availability. Two things that sound alike must be kept separate:

- **Who can find me** — set by the candidate, once, in their profile.
- **Where I want to look** — set by the seeker, per search.

A person appears only when both allow it. If a candidate's audience is "my university only," a seeker elsewhere never sees them, even when searching "anywhere."

| Setting | Options | Purpose |
|---|---|---|
| Open to collaboration | Off (default) / On | No one is discoverable without opting in |
| Who can find me | My university / My country / Anywhere | Candidate controls exposure |
| Open to | Co-authoring, grant partner, sharing data, mentoring | Helps seekers of that kind find the person; hides them from no one (see below) |
| Expires | e.g. 6 months, with a renewal prompt | Stale availability flags are how these features rot |

Supporting rules:

- **Verified scope.** Derive university and country from a verified institutional email or affiliation record, not free text, or the scope is trivially spoofable. *As built (2026-09-19):* from the verified email only; a personal address can neither search nor be found, and a seeker's scope never reaches past their own country — "anywhere" is an audience a candidate may choose, never a scope a seeker searches in.
- **Preview.** Show the candidate exactly what a seeker would see about them before they opt in.
- **Honest copy.** State that audience limits reduce exposure without guaranteeing it. LinkedIn's Open to Work help documentation makes the same admission about its recruiter-only setting.
- **Searching does not require being findable.** A seeker need not be open to collaboration themself (maintainer's decision, 2026-11-16; Q-085 in `docs/research/OPEN_QUESTIONS.md`).
- **`Open to` ranks, it does not filter.** A person's *Open to* kinds should raise them for seekers looking for that kind of collaboration without hiding them from anyone else (maintainer's decision, 2026-11-16; Q-086). Not built yet: the matcher does not read it.
- **Appearance cap.** Limit how many distinct seekers can see the same person per week. Without it, the most sought-after people are flooded and switch the setting off — the concentration failure from §2.

---

## 8. Triggers and interface

### 8.1 Trigger design

Three entry points, one matcher:

| Entry point | What is pre-filled |
|---|---|
| From a grant or funding call | Requirement slots, with covered/uncovered marked |
| From a project | The project's own facets |
| Manual search | Nothing; the user types the need |

All three produce the same editable query object: `{slots, lanes, scope}`. The user edits it and runs it.

**Rejected alternative — manual search as the primary path.** A blank box makes the user do the hardest part: describing what they lack, in another field's vocabulary. It is also what university research networking systems (Profiles, VIVO, Pure Experts) already offer; their literature reports obstacles around privacy, data quality, and unclear return on investment, and a usage study of one found some visits produced research outcomes but could not measure the scale.

**Rejected alternative — fully automatic matching.** Running candidate searches for every opportunity and every user spends compute on opportunities nobody will pursue, produces alert fatigue if the results are pushed, and goes stale as availability changes.

**Chosen pattern — pre-filled, user-run.** The cheap deterministic part (slot extraction, coverage marking) is precomputed and shown passively. The expensive part runs on click.

### 8.2 Interface placement

- **Opportunity card:** a one-line team-fit summary (which requirements you cover, which are gaps) plus a "Find collaborators" action.
- **Team-internal first:** where the system knows a group (a lab), show which requirements existing members cover before offering an outside search.
- **Search panel:** a side panel, not a new page, so the opportunity stays visible. Each result shows name, affiliation, the single matching facet, an evidence tag (declared / demonstrated), and Save / Not relevant controls.
- **Project page:** a "Collaborators" tab opening the same panel, pre-filled from the project's facets.
- **Settings:** a "Collaboration" tab holding the four settings in §7 plus the preview.
- **Feedback:** "Not relevant" is the training signal that eventually teaches the system what a good match is. Capture it from day one.

---

## 9. Hard constraints

### 9.1 No merged ranking

Out-of-field candidates match on fewer facets and will lose to in-field candidates in any single ranking. Lanes must have guaranteed slots.

### 9.2 Project secrecy

The project drives the seeker's search but never becomes part of anyone's discoverable profile. Anything that derives a public or shared embedding from project content violates this.

### 9.3 No search notifications to candidates

Candidates are never told that someone searched for them. "Someone looked for ocean-data expertise for this NSF call" leaks the seeker's plans to a potential competitor.

### 9.4 Coarse pointer disclosure

A result discloses enough to identify and look someone up (name, affiliation, the matching facet), not a dossier.

---

## 10. Where a graph database is actually justified

Vector search handles every lane in §4. A graph layer earns its place only on multi-hop questions:

- **Introduction paths.** "Who can introduce me?" via co-authorship, from a bibliographic source such as OpenAlex.
- **Exclusion.** Filtering out people already collaborating with the seeker.
- **Team coverage.** When an opportunity needs three disciplines, this is the *team formation* problem: choose a set of people who jointly cover every required skill while being close enough in the network to work together, sometimes with a minimum number of people per skill. The algorithms are well studied.

Until those features are wanted, keep the whole thing in a vector store plus a relational database.

---

## 11. Build sequence

1. **Requirement-slot extraction** from opportunity text. Fits inside whatever extraction step already reads opportunity descriptions.
2. **Team-fit line on opportunity cards.** No other people are involved, so slot quality can be validated with real users at zero privacy risk.
3. **Facet extraction over candidate papers.** Requires retaining candidate publications rather than reducing them to keywords.
4. **Consent settings and preview.**
5. **Panel and matcher**, launched at the narrowest scope only (single institution).
6. **Wider scopes**, then graph features from §10.

---

## 12. Evaluation

The two lane groups need different tests, and this choice should be made before building:

| Objective | Test | Weakness |
|---|---|---|
| Predict likely collaborations | Hide collaborations after a cutoff date, check whether the system predicted them | Rewards recommending collaborations that would have happened anyway; network-structure methods mostly reinforce already well-connected researchers |
| Surface valuable unlikely ones | Human judgment from researchers on their own real projects | Expensive, small samples; spontaneous materialization rates are tiny (see §15) |

---

## 13. Open questions

1. **Contact model.** Does contact stay outside the system (the seeker looks the person up), or does "open to collaboration" come with an in-app intro request? The first is a filter; the second is a messaging system needing spam controls, blocking, and rate limits.
2. **Candidate pool and cold start.** A pool of opted-in users is empty until many users occupy overlapping fields. A second pool of public bibliographic authors (publication evidence only, no availability claim) fixes coverage but changes the consent posture.
3. **Which facet to abstract first.** Field-neutral phrasing for methods (method transfer) or for problems (problem transfer)?
4. **Whether "open to collaboration" is one switch or a set of types.** Affects settings UI and result labelling.
5. **Opt-in or opt-out discovery.** The maintainer leans towards everyone being discoverable by default, showing only research area and declared interests, with an opt-out (2026-11-16; Q-089). §7 above still says opt-in; undecided.

---

## 14. Porting notes

**Portable, assumes nothing about the host system:**

- The facet decomposition (§3) and lane model (§4).
- The separation of candidate audience from seeker scope (§7).
- The pre-filled-then-run trigger pattern (§8.1).
- The hard constraints (§9) and the graph-justification test (§10).

**Assumes the host system has these; substitute your own equivalents:**

| Assumed capability | Why it matters | Mycelium's version |
|---|---|---|
| A per-item structured extraction, cached and reader-independent | Supplies the facets without per-search cost | `ItemComprehension`: problem, method, setting, claim, limitations, reusable |
| A stream of opportunities with machine-readable text | Supplies the triggers and the requirement slots | Grant/CFP scraper + LLM extraction loop |
| Per-person interest clusters plus vectors | Supplies the person side | Profile interest clusters (free text, per entity) |
| An intra-group fit layer | Lets you check internal coverage before external search | `member_fit` / `RecommendedFor` strip |
| An existing consent pattern with opt-in defaults | Template for the collaboration consent | Opt-in eligibility visibility, default off |
| A project or workspace object with private content | The search context that must stay secret | Project state model (problem, method, data, needs) |

**If the host system lacks a live opportunity stream**, the trigger collapses to project-based and manual search only. The design still works, but it loses its main differentiator over a browsable expert directory.

---

## 15. Prior art

| Work | What it does | Relevance |
|---|---|---|
| CM4AI talent knowledge graph (arXiv 2508.19489) | ~28,000 experts; clusters each author's papers into multiple expertise embeddings; recommends the 30 most similar unconnected researchers; LLM-written justifications; an expertise-gap agent; shortest co-authorship path for introductions | Closest prior system. The naive design is already published; differentiate or cite |
| Unlikely Pairs (Information, 2026) | Recommends semantically close but unconnected researcher pairs from bibliographic data; reports spontaneous materialization rates between roughly 0.06% and 0.5%; argues topology-driven prediction reinforces already well-connected authors | Sets realistic expectations and motivates the evaluation split in §12 |
| SOLVENT / Analogy Search Engine | Annotates papers by background, purpose, mechanism, findings; finds cross-domain analogies beyond baseline IR | Foundation for §3 |
| Hope et al., Accelerating Innovation Through Analogy Mining (KDD 2017) | Learns purpose and mechanism vectors; better analogy precision and recall than traditional IR | Foundation for §3 |
| SPECTER / SPECTER2 (Cohan et al. 2020; Singh et al. 2022) | Citation-informed document embeddings via triplet loss | Explains the cross-field weakness in §2.1 |
| OpenAlex topic hierarchy | 4 domains / 26 fields / 252 subfields / 4,516 topics, built by clustering the citation network | The field-distance ruler in §5 |
| Expertise retrieval literature (Balog et al.) | Document-centric vs profile-centric expert finding | §5, items 2–3 |
| Team formation literature (Lappas et al. and successors) | Cover a set of required skills while minimising communication cost | §10 |
| Reciprocal recommender literature | Two-sided preference, capacity, concentration effects | §2, §7 |
| Research networking systems (Profiles, VIVO, Pure Experts) | Institution-scoped searchable expertise directories | The baseline this must beat; §8.1 |
| LinkedIn Open to Work | Availability flag with audience choice and explicit non-guarantee of privacy | Consumer analogue for §7 |

---

## 16. Glossary

- **Facet** — one dimension of a piece of work or a person's expertise (problem, method, setting, offer, need). Matching compares facets separately rather than comparing whole profiles.
- **Lane** — a retrieval defined by which facets must match and which must differ. Lanes are ranked separately and never merged.
- **Requirement slot** — one distinct kind of expertise an opportunity asks for, extracted from its text.
- **Coverage** — whether the seeker (or their group) already satisfies a slot.
- **Evidence tier** — whether a capability is declared by the person or demonstrated by their publications.
- **Audience** — the set of seekers a candidate has agreed to be discoverable by.
- **Coarse pointer** — a disclosure limited to what is needed to identify and look someone up.
- **Reciprocal recommendation** — a recommendation problem where a match requires interest from both sides and each side has limited capacity.
