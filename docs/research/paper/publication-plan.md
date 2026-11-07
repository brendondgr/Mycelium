# Publication Plan, 2026–2028

Four submissions are committed, and each goes ahead whether or not the grant is
funded:

1. The software, to the **Journal of Open Source Software (JOSS)**.
2. An engineering experience paper, to **US-RSE'27**.
3. A user study of the hypothesis engine, to **ACM IUI 2028**.
4. A demo of Mycelium's language and knowledge-graph layer, to the **NAACL 2027
   System Demonstrations** track.

A fifth slot is an **open choice**: at **ACM SIGIR 2027**, either a demo (as the
fallback if NAACL rejects) or a short paper on the reranking negative results.
See section 5.

As of 2026-11-07. On that date the NAACL demo replaced the SIGIR demo as the
committed demo, because the project's research direction is NLP and knowledge
graphs. Dates for 2027 and 2028 are **expected**, projected from the previous
edition, unless marked confirmed. Check each official call before relying on a
date.

This plan sits beside [`OUTLINE.md`](OUTLINE.md) and does not replace it. Path A
(eligibility-constrained recommendation) is still a separate candidate, blocked
on the W5 judgments. The pilot-lab ratings collected for these papers could
supply some of those judgments.

## At a glance

| Output | Venue | Rank (ICORE2026) | Contribution | Submit | Present | Review |
|---|---|---|---|---|---|---|
| Software paper | JOSS | Journal; CORE does not rank journals | A citable record of the software | Rolling; earliest is six months after the repository goes public | — | Open, on GitHub |
| Experience paper | US-RSE'27, Papers track | Not ranked | Lessons from building and running an open, laptop-scale AI research tool for a real department | Mid-April 2027 (tentative) | October 25–27, 2027, Ann Arbor | Peer-reviewed; the call does not say whether it is anonymous |
| Research paper | ACM IUI 2028 | **A** | Whether a researcher-steered hypothesis engine with topic memory produces more useful directions than the same engine running on its own | ~August 2027 (IUI 2027's was August 20, 2026; nothing published for 2028 yet) | ~February–March 2028 | Double-blind |
| Demo paper | NAACL 2027, System Demonstrations | **A** | Mycelium's grounding layer: language read into a consented knowledge graph, each observation tied to its evidence and confirmed or retracted by the person, with citations checked by code | **December 4, 2026** (confirmed) | June 1–5, 2027, San Francisco (confirmed) | Single-blind in earlier editions, so the system can be named |
| *Open:* demo **or** short paper | ACM SIGIR 2027 | **A\*** | Either the demo, reworked toward retrieval (only if NAACL rejects), or a short paper on why recommended rerankers fail on profile-shaped queries | Demo: abstract February 4, paper February 11, 2027 (confirmed). Short paper: TBD (prev. February 12) | July 18–24, 2027, San Jose (confirmed) | Demo single-anonymous; short paper double-anonymous |

Every other venue that fits, and what each accepts, is in
[`venue-tracks.md`](venue-tracks.md).

## 1. JOSS: the software

**JOSS's hard requirements** (checked on its
[submission page](https://joss.readthedocs.io/en/latest/submitting.html),
2026-10-23):

- The repository must have been public for more than six months before
  submission, with active development across that period.
- There must be evidence that the software is used for research.
- A web-based tool is in scope if it either exposes a core library through
  the web interface, or shows a high level of rigour in domain modelling and
  testing. JOSS's own example of the second is an MVC app built with a
  framework such as Django, which is what Mycelium is. Reviewers must be able
  to run it on their own machines.
- The submission must carry an AI-usage disclosure: the tools used, the nature
  of the assistance, and confirmation of human review.
- Related publications must be declared, whether published, in review or about
  to be submitted.
- The paper is 750–1,750 words, with sections for: Summary, Statement of need,
  State of the field, Software design, Research impact statement, and the
  AI-usage disclosure ([paper format](https://joss.readthedocs.io/en/latest/paper.html)).
  Since January 2026 JOSS judges research impact and open-source practice
  rather than developer time, and wants the human work shown.

**What Mycelium needs:**

- **Go public by November 15, 2026.** The repository is private (created
  2026-05-31), so the six-month clock has not started. November 15 makes the
  earliest submission about May 16, 2027. Waiting until February would push
  JOSS to August, into the IUI deadline. JOSS
  checks how commits are spread over time, so develop steadily in public, not
  in bursts.
- **Rigour or a core library.** Either show rigorous domain modelling and tests
  in the Django app, or package the recommendation, extraction and briefing
  tools as a library under it. The first needs less restructuring.
- **Open-source practice.** Tests that run on a CPU with small fixtures,
  continuous integration, tagged releases, a changelog, and public issues and
  pull requests.
- **Evidence of research use.** Two months in one department is thin. Document
  the Department of Scientific Computing pilot, and aim for at least one lab
  outside it running Mycelium by May 2027. The NAACL demo and US-RSE papers
  will also count.
- **The AI-usage disclosure.** JOSS treats an incomplete disclosure as a
  possible ethical breach and looks hard at rapid AI-assisted code, so keep an
  AI-use log from now on.
- **Don't submit early.** A desk rejection is public and comes with advice to
  wait six months before resubmitting.

**How it differs from the other two papers:** a JOSS paper describes the
software and must not report research results, so it does not overlap with
either paper.

## 2. US-RSE'27: the experience paper

**The venue** (USRSE'26 rules, from its
[participation page](https://us-rse.org/usrse26/participate/); expected to
carry over to 2027):

- Up to 10 pages excluding references, in the IEEE template.
- Peer-reviewed for "quality, relevance, and novelty".
- Published in the conference proceedings on Zenodo.
- Papers and talks may be extended into a special issue of *Future Generation
  Computer Systems* afterwards, with 40% new content.
- It must be original work, not published elsewhere.
- USRSE'27 is in Ann Arbor, October 25–27, 2027, with papers, talks, notebooks,
  birds-of-a-feather sessions, workshops and tutorials due mid-April 2027
  (tentative, [dates page](https://us-rse.org/usrse27/about/dates/)).

**What it is:** lessons from building and running an open, laptop-scale AI
research tool for a real department. It is a community paper, not a CS research
paper: it reaches the research software engineers and labs who would contribute
and host, but carries little weight on a CS publication record.

**Outline:**

1. The problem: the paid, closed, remotely hosted AI services that steer what
   researchers read and fund.
2. Designing for small hardware: BM25 with compact embeddings, decision models,
   and a mixture-of-experts model with about 3B parameters active.
3. Engineering for trust: deterministic checks, citations generated by code,
   and profile changes proposed rather than made.
4. Open data, tracked in full: every deadline, round and update of each
   listing.
5. What the department pilot taught us, including what broke.
6. Installation by an AI agent, so no specialist knowledge is needed.
7. Lessons for other research software engineers building AI tools for labs.

**Evidence to collect now:** pilot usage numbers (with consent) and run times on
each class of hardware. Under the research record's rules these are recorded as
an experiment ([`../AGENT_INSTRUCTIONS.md`](../AGENT_INSTRUCTIONS.md)) before
they appear in the paper.

**Timeline:** draft February–April 2027, submit mid-April (tentative), present
October 25–27, 2027 in Ann Arbor.

## 3. IUI 2028: the hypothesis engine study

**Research question:** do researchers get more useful research directions when
they steer a hypothesis engine that keeps a memory of their exploration,
compared with the same engine generating directions on its own?

**The system**, a new Mycelium tool:

- It starts from the researcher's Mycelium profile, their own papers, and the
  literature.
- Each round, it proposes candidate research topics, each with cited evidence.
- The researcher responds in their own words: accept, reject, refine, ask
  "why", or redirect.
- The agent keeps a **memory report for each topic**: what has been explored,
  the sources, the dead ends, and the researcher's insights. That memory steers
  the next round of literature review, so topics build up over time.
- It runs on local hardware with small models. The paper reports whether it
  responds fast enough to use interactively on a laptop.

**The study:**

| Part | Plan |
|---|---|
| Participants | About 16–24 researchers from the Department of Scientific Computing and the pilot labs, each exploring an area of their own research |
| Conditions | Each participant tries both, in a balanced order: **(A)** steering with memory, the full system; **(B)** autonomous generation by the same model, with no feedback. Optional **(C)**: steering without memory, to show what the memory contributes |
| Format | Two or three sessions across a week, so the value of memory can show |
| Outcome measures | Each direction rated for novelty, feasibility, relevance and "would I pursue this?"; a blind rating by a second domain expert; a check of whether each direction is already published |
| Experience measures | Standard questionnaires on workload, sense of ownership, trust and usability |
| Behaviour | Logs of how topics changed under steering |
| Qualitative | Short semi-structured interviews, analysed by theme |
| Privacy | Participants' unpublished ideas never leave the machine, because the models are local |

**Claims the paper would make:**

1. The design of a researcher-steered hypothesis engine with topic memory, on
   local models.
2. An empirical comparison of collaborative and autonomous generation.
3. Design lessons for mixed-initiative research tools.

**Timeline:**

| When | What |
|---|---|
| Nov 2026 – Jan 2027 | Build the prototype on Mycelium. Both authors complete CITI human-subjects training and FSU conflict-of-interest disclosures (CAMS) |
| Dec 2026 | Ask FSU's Office for Human Subjects Protection (OHSP) for a pre-submission consultation: exempt category 3, or expedited because of screen and log recording? |
| By ~Jan 15, 2027 | Submit to the IRB through RAMP, using FSU's templates (an information sheet rather than full consent if exempt) |
| Feb – early Mar 2027 | Approval. FSU's figures: exempt clearance often within 2 weeks, expedited within 4. Approval cannot be retroactive, so even the 3–4 person pilot waits for it |
| Mar – May 2027 | Run the study |
| Jun – Jul 2027 | Analyse and write |
| ~Aug 2027 | Submit to IUI 2028 |
| ~Feb – Mar 2028 | Present |

**Rules that apply:**

- **Research record.** The study is an experiment: scaffold it with
  `make new-experiment` and fill `PROTOCOL.md` before the first session. The
  pre-registration also strengthens the paper.
- **IRB.** It needs review before any participant session.
- **Anonymity.** IUI desk-rejects submissions that reveal their authors,
  including through videos and supplements. A public, named Mycelium is allowed,
  but the paper must not reveal that the authors built it. Cite Mycelium's
  papers in the third person, give the hypothesis engine its own name in the
  submission, link code only through an anonymized mirror, and scrub the video
  of logos, usernames and voices. Any related submission still under review in
  August (JOSS, for example) must be uploaded in anonymized form.
- **Reviewers' note.** IUI asks for a short note giving the human-subjects
  context. Make the PDF accessible (alt text, tagged PDF) and caption any video.
- **Compensation.** Payments to participants before the grant starts cannot
  come from the grant. FSU allows research gift cards only through its approved
  vendors, and a participant paid $600 or more in a year needs a 1099.
- **Cost.** No article charge: FSU Libraries confirmed on 2026-10-25 that FSU
  is in ACM Open, and ACM waives the charge when the corresponding author's
  institution participates. Make an FSU author the corresponding author.
  Registration has been at the full rate, one paper per registration,
  presented in person.

**Risks and fallbacks:**

- The "AI scientist" field is crowded and moving fast. The paper stands only on
  evidence that collaboration beats autonomy, not on the claim alone.
- If the build or the study slips past August 2027: CSCW (rank A), which now
  takes papers at any time with no deadlines, or IUI 2029. An IUI posters and
  demos submission (deadline about November) can show an early version. CHIIR
  (rank B) is the best fit if rank matters less.
- IUI 2027 asked for papers of about 8,000 words, reviewed double-blind
  including videos and supplements, and published in the ACM Digital Library.

## 4. NAACL 2027: the demo

**The venue:** NAACL 2027, in San Francisco, June 1–5, 2027. System
demonstrations are due **December 4, 2026**, with notification February 10,
2027 and camera-ready March 3, 2027, all anywhere-on-earth (confirmed on
[2027.naacl.org](https://2027.naacl.org/)). The 2027 demo call page itself
returned 404 on 2026-11-06, so the format below comes from the
[NAACL 2025](https://2025.naacl.org/calls/demo/),
[ACL 2026](https://2026.aclweb.org/calls/system_demonstration/) and
[EACL 2027](https://2027.eacl.org/calls/demos/) calls:

- Up to 6 pages, plus unlimited references and appendix, and one extra page
  after acceptance. Submitted through OpenReview.
- Single-blind, so Mycelium can be named and linked.
- A screencast video of up to 2 minutes (NAACL 2025) or 2.5 minutes (ACL 2026,
  EACL 2027). A live demo site or an installable package is strongly
  recommended, and open-source systems are of special interest.
- Archival, in the ACL Anthology. The work must be original and not under
  review anywhere else while NAACL reviews it. A system reported before needs
  a substantial improvement (more than 30%, in NAACL 2025's rule).
- The topics include "application systems using language technology".

**Why NAACL:** the research direction behind Mycelium is NLP and knowledge
graphs, and this is the layer of the system that does language processing.
Mycelium's retrieval results belong to SIGIR, not here.

**What the demo shows: the grounding layer.**

1. Lab conversation and meeting transcripts read into grounded observations
   (`apps/ambient`), with nothing verbatim stored.
2. Those observations linked to concepts in the knowledge graph
   (`apps/knowledge`, built in Postgres; Neo4j is not used), each tied to its
   evidence, and confirmed, edited, faded or retracted by the person.
3. A person's own papers read into demonstrated edges, and a project's state
   extracted from a document under grounding checks.
4. The weekly report's citations checked by code against that evidence.

Suggestions built on a person's projects, interests and background are the use
case the video shows. They are not the claim.

**What it must not lead with:**

- The paper feed. Scholar Inbox, an ACL 2025 System Demonstration, already
  covers it (`docs/research-audit.md`, B1), and these reviewers will know it.
- A "multi-agent" framing. The audit found none in the code, and three recent
  papers argue against the framing.

**The risk is maturity.** The ledger's nightly reasoning step ships switched
off (`AMBIENT_DELIBERATE_ENABLED`). Before December 4, check that the ledger
can be demonstrated end to end on made-up data, and record at least one
measurement as an experiment. The natural candidate is C-025, whether the
weekly's citation checks remove unsupported sentences with useful precision
and recall: it is written down but unmeasured (`EXP-2026-09-002`). If the
ledger is not ready, the fallback within the same theme is item 3 above: paper
facets into edges, plus project-state extraction.

**How it differs from the other papers:** it reports no study, so it does not
overlap with the IUI paper, and it is a short scholarly description rather
than the JOSS software paper.

## 5. SIGIR 2027: open, the demo or a short paper

**The venue:** the 50th SIGIR, in San Jose, July 18–24, 2027. Its tracks page
posted on 2026-11-07: demos due February 11, 2027 with abstracts February 4;
full papers January 21; resource and reproducibility papers February 11;
short-paper dates TBD (February 12 in 2026). The 2027 topics include
scientific literature search and discovery, human-AI collaboration, and
inference cost.

This slot is **not decided**. Pick at most one of the options below, because
January already holds the hypothesis-engine build and the IRB submission.

**Option A: the demo, as NAACL's fallback.**

- The same system, reworked toward retrieval: open sources with every deadline
  and round tracked, grounded retrieval for a person's interests, all on a
  laptop.
- Only if NAACL rejects the demo. NAACL decides on February 10, one day before
  SIGIR's demo deadline, so the paper must be ready to rework in a day.
- SIGIR's demo abstract is due February 4, while NAACL is still reviewing. Ask
  the SIGIR demo chairs whether registering that abstract counts as dual
  submission.
- If NAACL accepts, a SIGIR demo of the same system is out. A demo of a
  clearly different component is possible only with overlap well under ACL's
  25% threshold, and disclosed to both venues' chairs.
- SIGIR 2026's demo track asked for 4 pages plus references, a video or a live
  link, and single-anonymous review.

**Option B: a short paper on the reranking negative results.**

- The pitch: the rerankers everyone recommends fail on profile-shaped queries.
  A declared research interest is about two words.
- The evidence is complete, pre-registered, with paired intervals, on two
  LongEval-Sci snapshots:
  - C-013 (refuted): a cross-encoder gives no significant gain on either
    snapshot, and significant harm on 1–4 word queries.
  - C-017 (refuted): an LLM-written query expansion was meant to fix that, and
    instead doubled the damage, growing with expansion length.
  - C-015 (supported): an LLM listwise reranker loses 18% of nDCG@10 when the
    candidate order is reversed, and adds no ranking signal.
- 4 pages plus references, double-anonymous: describe Mycelium as "a deployed
  system" and do not link the repository.
- About 1–2 weeks of writing in January. The odds in a competitive short-paper
  track are fair at best, and the paper does little for an agents and NLP
  research identity.
- **Not** the benchmark-transfer story (C-021, C-022). C-022 rests on one
  reader over three queries. It needs the multi-judge study (Q-030) first, and
  would then be a stronger full paper later.
- The cheaper home if January is full: working notes for the CLEF LongEval
  2027 lab (CEUR, lower prestige).

**When to decide:** by about January 28, 2027, a week before the demo
abstract. Choose B if January has room for the writing. Hold A as the fallback
only if NAACL is still undecided and B was not chosen.

## What is still needed, by submission

Very generally. The specifics come from each venue's call, and from the
pre-submission research prompt in
[`presubmission-research-prompt.md`](presubmission-research-prompt.md).

| Submission | Still needed |
|---|---|
| **All** | The licence is settled: Apache 2.0 (decided 2026-10-25). Clean the repository (secrets scan, real names in seed data) and make it public by November 15. Set up accounts at least a month before any deadline: ORCID (Brendon has one; confirm Olmo's), OpenReview (a profile can take up to two weeks), PCS, and ACM, SIGIR and SIGCHI membership (SIGIR travel grants need SIGIR membership). Start a deployment log and an AI-use log now. FSU is in ACM Open, so ACM article charges are waived |
| **NAACL 2027 demo** | Confirm the format once the 2027 call page is up. Check that the ambient ledger and knowledge graph can be demonstrated end to end, and record one measurement as an experiment (C-025 is the candidate). Build a stable demo instance with made-up profiles and conversations, and no pilot data. Script and record a screencast of 2 minutes or less. Write the 6 pages: the problem, the grounding layer, what the demo shows, how it differs from existing tools (Scholar Inbox already covers the paper feed, so lead with grounded, consented, retractable knowledge), the measurement, and where to get it. The repository must be public by then. Ask the demo chairs whether a CHI 2027 demo on the same system would count as prior publication. After acceptance, register an author and find travel money (the trip is not in the grant budget) |
| **SIGIR 2027 (open)** | Decide between the demo and the short paper by about January 28 (section 5). For the demo: have the NAACL paper ready to rework toward retrieval within a day of February 10, ask the demo chairs about the February 4 abstract, and after acceptance apply for a SIGIR student travel grant in its roughly two-week window without registering before the decision (SIGIR 2025's covered registration plus a $1,200 stipend). For the short paper: write 4 anonymized pages from the existing experiment records, with no new runs |
| **US-RSE'27 paper** | Record pilot usage numbers (with consent) as an experiment. Measure run times on a laptop, a lab server and a cluster (a NAIRR start-up allocation could supply the cluster). Draft February–April in the IEEE template, with the fit statement, and keep it distinct from the JOSS paper |
| **JOSS** | Start the six-month clock by making the repository public. Show rigorous design and tests in the Django app, or package a core library. Add tests that run on a CPU, continuous integration and tagged releases. Develop in the open through issues and pull requests. Document the department pilot as research use. Write the 750–1,750-word paper with the AI-usage disclosure |
| **IUI 2028 paper** | Build the hypothesis engine (November–January). Pre-register the study in the research record. Complete CITI training, and submit to the IRB by about January 15 so approval lands by early March. Recruit 16–24 participants and find compensation that is not grant money. Run the study (March–May), analyse and write (June–July), anonymize, and watch for the IUI 2028 call |

## Calendar

| When | What |
|---|---|
| By Nov 15, 2026 | Clean the repository and **make it public** under Apache 2.0 (the JOSS clock starts). Accounts and memberships. CITI training. Start the deployment and AI-use logs. File a NAIRR start-up request. Start building the hypothesis engine |
| Nov 2026 | Check the ledger is demo-ready and run its measurement. Build the demo instance (made-up profiles and conversations only), record the video, write the 6 pages. Keep building the engine |
| **Dec 4, 2026** | **Submit the NAACL 2027 demo** |
| Dec 2026 | Build the engine. Draft the IRB protocol; consult OHSP |
| Jan 2027 | **Submit to the IRB by about January 15.** Optional: a CHI 2027 interactive demo (due January 21), only if the engine is presentable and the NAACL demo chairs confirm it won't count as prior publication. If the SIGIR short paper is chosen, write it. **Decide the SIGIR slot by about January 28** |
| Feb 2027 | SIGIR demo abstracts February 4 (option A only). **NAACL decisions February 10.** SIGIR demos due February 11 (option A, only if NAACL rejected). SIGIR short paper due around mid-February (option B; date TBD) |
| Mar 2027 | NAACL camera-ready March 3. IRB approval expected; recruit, pilot with 3–4 people |
| Mar – May 2027 | Run the IUI study. Draft the US-RSE paper; **submit it in mid-April** |
| Apr 2027 | SIGIR decisions (April 5), then the roughly two-week window for student travel grants. Camera-ready around April 30 |
| ~May 16, 2027 | **JOSS: earliest submission**, if the repository went public by November 15 and the research-use evidence is documented |
| Jun 1–5, 2027 | **Present the demo at NAACL**, San Francisco |
| Jul 18–24, 2027 | **Present at SIGIR**, San Jose, if either SIGIR option was submitted and accepted |
| ~Aug 2027 | **Submit to IUI 2028** |
| Oct 25–27, 2027 | **Present at US-RSE'27**, Ann Arbor |
| ~Feb – Mar 2028 | **Present at IUI 2028** |

## How this fits the grant proposal

The proposal budgets two conference trips: US-RSE'27 and IUI 2028. The NAACL
2027 trip (June) and any SIGIR 2027 trip (July) are not in the grant budget,
and both may come before the grant starts, so they need department or
university travel money, or student travel grants (the venue review reported
that SIGIR 2027 promises more fully funded ones for its 50th edition). The hypothesis engine and its first
study begin before the grant. The grant funds the open release, evaluation
across the pilot labs, and the two budgeted trips. With FSU in ACM Open, the
budget's $1,500 open-access line is not needed for the IUI paper. The proposal
itself is kept
out of git, in `docs/grants/`.

## Sources

- [`presubmission-checklists.md`](presubmission-checklists.md): the full
  checklists, calendar and open questions this plan draws on, from the
  2026-10-25 deep-research run, with its own sources. It predates the
  2026-11-07 switch to a NAACL demo, so its SIGIR-demo items now apply only to
  option A
- [`submission-steps.html`](submission-steps.html): the steps for SIGIR,
  US-RSE and IUI as a timeline and checklists; a local copy of the
  [published page](https://claude.ai/artifact/25adGmiX6jQxFenP1rui6p). It
  also predates the NAACL switch
- [NAACL 2027](https://2027.naacl.org/) for the confirmed demo dates; the
  format comes from the [NAACL 2025](https://2025.naacl.org/calls/demo/),
  [ACL 2026](https://2026.aclweb.org/calls/system_demonstration/) and
  [EACL 2027](https://2027.eacl.org/calls/demos/) demo calls
- [JOSS submission requirements](https://joss.readthedocs.io/en/latest/submitting.html)
- [US-RSE'26 participation tracks](https://us-rse.org/usrse26/participate/)
- [ICORE conference rankings portal](https://portal.core.edu.au/conf-ranks/)
- [SIGIR 2027](https://sigir2027.org/) and its
  [tracks page](https://sigir2027.org/pages/submit-tracks.html), which posted
  the demo, full, resource and reproducibility dates by 2026-11-07; the demo
  format above is SIGIR 2026's ([sigir2026.org](https://sigir2026.org/))
- IUI 2027 dates (paper deadline August 20, 2026; conference February 8–11,
  2027, Helsinki), from an external venue review dated 2026-10-23 that cites
  IUI's official announcement
