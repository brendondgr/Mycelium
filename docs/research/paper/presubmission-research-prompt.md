# Deep-research prompt: what to check and do before each submission

Paste everything under **The prompt** into a deep-research tool. It asks for
pre-submission checklists for the four committed submissions in
[`publication-plan.md`](publication-plan.md), organized by submission type, so
nothing is discovered the week before a deadline. It names what we already
know and leaves the model free to find what we don't.

---

## The prompt

You are helping a small university team prepare four submissions about one
open-source system, over late 2026 to early 2028. For each, find out what we
must check, prepare and do before submitting, at submission, and after
acceptance. Organize the answer by submission, and also by submission type
(demo, research paper, community conference paper, journal software paper,
workshop paper), because we will reuse the type-level lessons for later venues.
Explore beyond the categories below wherever something matters.

### The team and the system

- An assistant professor in a Department of Scientific Computing at Florida
  State University (Tallahassee, Florida), as principal investigator, and a
  graduate student who built the system and is its research software engineer.
- **Mycelium**, an open-source research assistant that any lab can host on its
  own hardware, down to a laptop. It recommends open papers, grants,
  fellowships and conferences against each person's interest profile, tracks
  every deadline and update, and has an AI agent write daily or weekly
  briefings. It uses small models (BM25, compact embeddings, small decision
  models, a mixture-of-experts language model with about 3B active parameters).
  Deterministic code generates citations and checks the model's output.
  Profile changes are proposed to the person rather than made silently.
- It has been in prototype use in one university department for about two
  months. The repository is private now and will be made public, under the name
  Mycelium, before any submission. The licence (MIT or Apache 2.0) is being
  finalised.
- A new tool on top of it, a **hypothesis engine**, is being built. The
  researcher steers it with continuous feedback, and it keeps a memory report
  per topic across its literature reviews. It will be evaluated in a within-
  subjects user study with about 16–24 researchers.

### The four submissions, and what we already know

1. **ACM SIGIR 2027, demo track** (San Jose, July 18–24, 2027). The 2027 demo
   call is not published yet. SIGIR 2026's demos were 4 pages plus references,
   needed a video or a live link, used single-anonymous review, appeared in the
   proceedings, and were due February 12, 2026.
2. **US-RSE'27, papers track** (Ann Arbor, October 25–27, 2027; submissions
   tentatively due mid-April 2027). USRSE'26 papers were up to 10 pages in the
   IEEE template, peer-reviewed, published on Zenodo, required a short
   statement of fit with US-RSE, and could be extended into a journal special
   issue.
3. **JOSS, software paper** (rolling). 750–1,750 words, with sections for:
   summary, statement of need, state of the field, software design, research
   impact, and an AI-usage disclosure. The repository must have been public for
   more than six months with active development, there must be evidence of
   research use, and a web tool must either expose a core library or show
   rigorous domain modelling and testing.
4. **ACM IUI 2028, full paper** (deadline expected around August 2027; nothing
   published for 2028 yet). IUI 2027 asked for about 8,000 words, double-blind
   review including videos and supplements, and published in the ACM Digital
   Library. This paper reports the hypothesis engine's user study.

Optional, if time allows: a **CHI 2027 interactive demo** (due January 21,
2027; 6 pages plus video; not anonymous), and workshop papers such as the
NeurIPS AI-for-science workshops (non-archival).

### What to find for each submission

- **Format and mechanics.** The template and its exact variant, limits and what
  counts toward them, required sections, video or supplementary-material specs
  (length, format, captions), the submission system and how long its account
  setup takes (for example OpenReview profiles), abstract-registration dates,
  conflict-of-interest declarations, and any reviewing duty imposed on authors.
- **Anonymity and prior publication.** How to handle a public, named
  repository, self-citation and preprints in anonymous tracks. Whether a demo
  paper, the JOSS paper, the US-RSE paper and the IUI paper count as prior
  publication against each other, and how to keep each distinct.
- **Ethics and disclosure.** What IRB approval the user study needs at Florida
  State University (review categories, typical timelines, consent, participant
  compensation rules), the human-subjects statements venues require, and each
  venue's and publisher's policy on generative-AI use (ACM, IEEE, JOSS). Data
  privacy for a live demo, which must show no real user's data.
- **Artifacts and availability.** Code and data availability statements, ACM
  artifact badges and whether they apply, licence expectations, and what a live
  demo must provide (access without login, uptime during review and the
  conference, hosting options).
- **After acceptance.** Camera-ready process (for example ACM TAPS), copyright
  and open-access options (ACM Open, and whether Florida State University
  participates; article charges), registration rules (how many authors must
  register, at what rate), in-person presentation rules, demo booth logistics,
  accessibility requirements (alt text, captions, accessible PDFs), and travel
  grants for students (SIGIR, SIGCHI, US-RSE and others).
- **What reviewers look for.** Each track's stated criteria; recent accepted
  examples of the same kind (scholarly or research-opportunity recommenders at
  SIGIR or RecSys; mixed-initiative research or ideation tools at IUI or CHI;
  experience papers at US-RSE; JOSS papers for web-based research tools); and
  common reasons such submissions are rejected. How much evaluation a demo
  needs.
- **Positioning.** The systems reviewers will compare us against, from free
  scholarly feeds to paid research assistants, funding databases and "AI
  scientist" systems, and how comparable submissions differentiated themselves.
- **Lead times.** How far ahead each item must start: IRB, accounts, video
  production, demo hosting, camera-ready, travel booking and funding.

### What to deliver

1. **A checklist per submission**, grouped into: start now; before submission;
   at submission; after acceptance. Link the official page behind each item.
2. **A summary by submission type**: what demos, research papers, community
   conference papers, journal software papers and workshop papers each require
   in common.
3. **A backward-planned calendar** from late October 2026 to March 2028,
   combining all four submissions and their lead times.
4. **Open questions** we should put to the organizers, to Florida State
   University's IRB, or to its research and travel offices.

### Ground rules

- Use official sources: the venue's call, the publisher's policies, and
  Florida State University's own pages. Link every page you used.
- If a 2027 or 2028 call is not published, give the previous edition's rule and
  mark it "previous edition".
- Never invent a rule, date, fee or requirement. If you can't find something,
  say so.
