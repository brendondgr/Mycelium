> **Provenance.** The output of [`presubmission-research-prompt.md`](presubmission-research-prompt.md), run on 2026-10-25 with an external deep-research tool and kept as delivered. It was spot-checked, not re-verified. Two corrections: (1) JOSS confirms a web application qualifies through *either* a core library *or* rigorous domain modelling and testing, and its own example of the second is a Django-style MVC app; (2) the claim that Florida State University is not in ACM Open could not be re-checked, because the participant list did not load, and is wrong: FSU Libraries confirmed on 2026-10-25 that FSU **is** in ACM Open, so ACM article charges are waived. The licence was settled the same day as Apache 2.0. The decisions taken from this report are in [`publication-plan.md`](publication-plan.md).

# Mycelium Submission Plan, Oct 2026 – Mar 2028: Checklists, Type-Level Lessons, Calendar and Open Questions

**Bottom line: make the Mycelium repository public in November 2026, not just before the SIGIR deadline. JOSS requires a repository that has been "public for more than six months prior to submission, with active development spanning that period," [readthedocs](https://joss.readthedocs.io/en/latest/submitting.html) so going public in early February 2027 would push JOSS eligibility into August 2027, the same month as the probable IUI 2028 deadline. Going public in November 2026 makes JOSS possible from about May 2027 and also covers the CHI 2027 demo (January 21, 2027), which is not anonymous.** [acm](https://chi2027.acm.org/authors/interactive-demos/) The two other risks that drive the schedule are these. First, IUI is double-blind and desk-rejects papers that reveal their authors, so the IUI paper must refer to the system without naming it as the authors' own. [acm](https://iui.acm.org/2027/call-for-papers/) Second, the FSU IRB has to approve the hypothesis-engine study by about March 2027 if the data are to be collected and analysed before an August deadline.

## TL;DR

- **Sequence:** repository public by mid-November 2026 → CHI 2027 interactive demo (optional, Jan 21, 2027) → SIGIR 2027 demo (call not yet published; previous edition was due Feb 12, 2026) → IRB application in January 2027 → US-RSE'27 paper (tentatively mid-April 2027) → JOSS from about May–June 2027, once six months of public history *and* evidence of research use exist → IUI 2028 full paper (previous edition: abstract Aug 13, paper Aug 20).
- **Biggest policy constraints:** IUI double-blind review (names hidden in the paper, videos and supplements; self-citations in the third person; concurrent related submissions must be uploaded in anonymized form). JOSS has four desk-reject gates (six months of public history, sustained development, demonstrated research use, open-source practice). US-RSE requires original work "not published elsewhere," so it must not repeat the SIGIR demo paper.
- **Money and ethics:** Florida State University does **not** appear on ACM's ACM Open participant list, so an APC (article processing charge) probably applies to the IUI full paper; check this with FSU Libraries now. [acm](https://libraries.acm.org/acmopen/open-participants) FSU exempt IRB reviews "may receive clearance within 2 weeks or 10 business days," non-committee (expedited) reviews "within 4 weeks," and CITI training must be finished before review starts. [fsu](https://knowledgebase.research.fsu.edu/s/article/How-long-will-it-take-for-OHSP-or-the-IRB-to-approve-of-my-study)

---

## Key Findings

### 1. Which 2027/2028 calls exist (as of Oct 25, 2026)

| Venue | Status of call | What we could verify |
|---|---|---|
| SIGIR 2027 demos | **Not published.** The sigir2027.org tracks page says the track pages are "2027 placeholders" [sigir2027](https://sigir2027.org/pages/submit-tracks.html) | Only the full-paper call is out, and its dates are marked "PROPOSED": abstract Jan 14, 2027; paper Jan 21, 2027; notification Apr 5; camera-ready and author registration Apr 30. It uses OpenReview and is double-anonymous [sigir2027](https://sigir2027.org/pages/submit-full.html) |
| US-RSE'27 | **Not published on us-rse.org.** A GitHub repository USRSE/usrse27 contains an announcement post dated 2026-10-21 [github](https://github.com/USRSE/usrse27/pull/8) | Ann Arbor and the October 25–27 dates could not be confirmed from an official page |
| JOSS | Rolling; rules updated in 2026 | Six-month public-history gate, research-impact gate, mandatory AI-usage disclosure [theoj](https://joss.theoj.org/about) |
| IUI 2028 | **Not published** | IUI 2027 (previous edition): abstract Aug 13, 2026; paper Aug 20; initial notifications Oct 29; rebuttal Nov 5; final decision Nov 23; camera-ready Dec 3; conference Feb 8–11, 2027, Helsinki [acm](https://iui.acm.org/2027/call-for-papers/) |
| CHI 2027 interactive demos | **Published** | Due Jan 21, 2027; up to 6 pages excluding references (single-column); walkthrough video ≤5 min; not anonymous [acm](https://chi2027.acm.org/authors/interactive-demos/) |

Two other demo deadlines fall very soon: IUI 2027 posters and demos (Nov 10, 2026; 4 pages; ≤5-minute video; held in Helsinki) [acm](https://iui.acm.org/2027/call-for-posters-demos/) [x](https://x.com/ACMIUI) and CHIIR 2027 demos (Oct 29, 2026). [github](https://chiir2027.github.io/) [acm](https://iui.acm.org/2027/call-for-posters-demos/) Both are probably too early unless a public instance already runs.

### 2. The JOSS six-month arithmetic (sequencing conflict a)

JOSS's documentation says: "The repository must have been public for more than six months prior to submission, with active development spanning that period." [readthedocs](https://joss.readthedocs.io/en/latest/submitting.html) Its editorial guide adds that "a recent repo dump or commits concentrated into a short window fails this gate." [readthedocs](https://joss.readthedocs.io/en/latest/editing.html) Some examples:

- Public **Feb 1, 2027** (just before a SIGIR-style deadline): earliest JOSS submission about **Aug 2, 2027**, competing with IUI.
- Public **Jan 15, 2027** (before CHI): about **Jul 16, 2027**.
- Public **Nov 15, 2026** (recommended): about **May 16, 2027**, before US-RSE notification and well before IUI.

Six months is a minimum, not a guarantee. JOSS also screens for "evidence that the software is actually being used for research… Potential future use is not sufficient," and for issues, pull requests, releases, tests, CI, documentation and contribution guidelines. [readthedocs](https://joss.readthedocs.io/en/latest/editing.html) A desk rejection is public and comes with advice to "resubmit in six months or more." [github](https://github.com/PhilanthroPy-Project/PhilanthroPy/issues/127) Two months of use in one department is thin evidence. By May 2027 the team should be able to point to a SIGIR or CHI demo paper, the US-RSE paper and preferably at least one outside lab running Mycelium.

**Recommendation:** finalise the licence (both MIT and Apache-2.0 are OSI-approved; JOSS requires "a plain-text LICENSE file with the contents of an OSI approved software license"). [readthedocs](https://joss.readthedocs.io/en/latest/review_checklist.html) Then publish the repository by mid-November 2026 with tagged releases, a CONTRIBUTING file, CI and public issues. After that, develop in public steadily instead of in bursts.

### 3. Anonymity across the four papers (sequencing conflict b)

- **IUI (double-anonymous review: reviewers do not know who the authors are, and authors do not know the reviewers).** The IUI 2027 call requires that "authors' names and affiliations are not visible anywhere in the submission, including… video figures, and supplemental materials." Self-citations "must use the third person," and "failure to follow these guidelines may result in submissions being desk-rejected without review." [acm](https://iui.acm.org/2027/call-for-papers/) The IUI 2027 call does not forbid public repositories or preprints. A named, public Mycelium repository plus SIGIR, US-RSE and JOSS papers is therefore allowed, but the IUI manuscript must not *reveal* that the authors built it.
  - Cite the Mycelium papers in the third person ("Mycelium [12] provides…").
  - Give the hypothesis engine its own name in the submission, or a placeholder.
  - Link code only through an anonymized mirror. SIGIR's 2027 call recommends anonymous.4open.science and treats "links to source code repositories that directly reveal the identities" as grounds for desk rejection; [sigir2027](https://sigir2027.org/pages/submit-full.html) the same practice is the safe choice at IUI.
  - Scrub the video of logos, FSU branding, usernames and voice introductions.
  - IUI also requires that "if you have any concurrent submissions… based on the same study, artifact, or dataset… you must include an anonymized version of that submission." [acm](https://iui.acm.org/2027/call-for-papers/) Any paper still under review in August 2027 (for example JOSS) must be uploaded anonymized.
- **SIGIR demo (previous edition: single-anonymous review, meaning reviewers see the authors' names but authors do not see the reviewers').** Naming Mycelium is fine. SIGIR 2026's general policy also said "Authors may post drafts of their papers on the web, submit them to arXiv." [sigir2026](https://sigir2026.org/en-AU/pages/submissions/submission-policies-and-information)
- **CHI interactive demo:** "Submissions should NOT be anonymous." [acm](https://chi2027.acm.org/authors/interactive-demos/)
- **US-RSE and JOSS:** reviews are not anonymous to authors (JOSS reviews take place in public GitHub issues).

### 4. Does one paper count as prior publication against another?

- **SIGIR demo vs. IUI full paper.** IUI wants "original paper submissions that are not under consideration elsewhere." [acm](https://iui.acm.org/2027/call-for-papers/) This is not a conflict as long as the SIGIR demo describes the Mycelium platform and the IUI paper reports the new hypothesis-engine study. Do not include hypothesis-engine user-study results in the demo paper. Cite the demo in IUI in the third person.
- **SIGIR demo vs. US-RSE paper.** The USRSE'26 papers track "requires original work, not published elsewhere." [us-rse](https://us-rse.org/usrse26/participate/) Make the US-RSE paper an *experience/engineering* paper (deployment lessons, deterministic citation checking, self-hosting on laptops, sustainability, community), not a rewritten system description.
- **CHI demo vs. SIGIR demo.** CHI allows previously published work "as long as the demonstration adds a novel aspect," and requires a publication history. [acm](https://chi2027.acm.org/authors/interactive-demos/) The reverse direction is the risk: SIGIR's 2027 full-paper call forbids work "previously published" or "under review" anywhere. [sigir2027](https://sigir2027.org/pages/submit-full.html) If the 2027 demo call uses the same wording, a CHI demo accepted on Feb 18, 2027 could count as prior publication against a SIGIR demo submitted in February. **Ask the SIGIR demo chairs before submitting both.** If both go ahead, make the CHI demo about the *interaction* (proposed profile changes, briefings) and the SIGIR demo about *retrieval and recommendation*.
- **JOSS.** We did not find a JOSS rule against prior conference papers about the same software. Earlier papers can serve as evidence of "research impact." [theoj](https://joss.theoj.org/about) Ask the JOSS editors if in doubt.

### 5. IRB at FSU (sequencing conflict c)

- **Terms.** An *IRB* (Institutional Review Board) reviews research on people. *Exempt* review covers minimal-risk studies in eight federal categories (45 CFR 46.104(d)); [fsu](https://www.research.fsu.edu/research-offices/ohsp/human-research-review/) FSU staff decide whether a study qualifies, and "only the IRB and the Office for Human Subjects Protection (OHSP) staff have the authority to determine whether a proposal meets the exempt requirements." [fsu](https://www.research.fsu.edu/research-offices/ohsp/human-research-review/review-pathways/) [fsu](https://knowledgebase.research.fsu.edu/s/article/How-is-IRB-review-performed) *Expedited* (non-committee) review covers minimal-risk research in nine federal categories and is done by at least one IRB member on a rolling basis. [fsu](https://www.research.fsu.edu/research-offices/ohsp/human-research-review/review-pathways/) [fsu](https://www.research.fsu.edu/research-offices/ohsp/human-research-review/) *Full committee* review happens at monthly meetings. [fsu +2](https://www.research.fsu.edu/research-offices/ohsp/human-research-review/) *Limited IRB review* (a privacy and confidentiality check) may be needed for some exempt categories (2, 3, 7, 8). [fsu](https://www.research.fsu.edu/research-offices/ohsp/investigator-resources/revised-common-rule/)
- **Likely category.** A within-subjects study with adult researchers using software, with questionnaires and interviews, looks like exempt category 3 ("benign behavioral interventions… from adult subjects"). [fsu](https://www.research.fsu.edu/research-offices/ohsp/human-research-review/review-pathways/) If identifiable screen, audio or interaction logs are recorded, the study may need limited review or expedited review. Only OHSP can decide.
- **Timelines (FSU's own figures).** "Exempt studies may receive clearance within 2 weeks or 10 business days, often less; Non-committee reviews may be completed within 4 weeks." [fsu](https://knowledgebase.research.fsu.edu/s/article/How-long-will-it-take-for-OHSP-or-the-IRB-to-approve-of-my-study) January 2023 averages were 8 days exempt, 18 expedited and 41 convened. [fsu](https://hub.research.fsu.edu/newsletter/article/updates-office-human-subjects-protection) FSU's pre-award guidance warns that review "may take on average 40 days." These figures assume complete applications on FSU templates. [fsu](https://www.research.fsu.edu/research-offices/ohsp/human-research-review/review-pathways/) [fsu](https://www.research.fsu.edu/research-offices/ohsp/grant-applications-funding-the-irb/ohsp-guidance-on-pre-award-applications-for-funding/)
- **Prerequisites.** CITI human-subjects training must be completed "before the OHSP/IRB will review or approve of the study." [fsu](https://www.research.fsu.edu/media/7923/student_research_guidance_20210203.pdf) Every team member needs a current CAMS conflict-of-interest disclosure, or "a delay in IRB review" follows. Submit through RAMP IRB, [fsu](https://www.research.fsu.edu/research-offices/ohsp/investigator-resources/) and check the HRP-308 pre-review worksheet. [fsu](https://knowledgebase.research.fsu.edu/s/article/How-is-IRB-review-performed) "Approval cannot by law be granted retroactively," so even piloting with real participants must wait. [fsu](https://www.research.fsu.edu/media/7923/student_research_guidance_20210203.pdf) [fsu](https://www.research.fsu.edu/research-offices/ohsp/)
- **Consent.** If OHSP expects an exempt determination, use FSU's *information sheet* template instead of the full consent template. [fsu](https://www.research.fsu.edu/research-offices/ohsp/human-research-review/review-pathways/)
- **Compensation.** FSU Procurement allows gift cards "only… for research participants," purchased through Blackhawk Network, Tango or Prolific, on approved fund codes (110, 140, 520–560 except 556, 599). [fsu](https://procurement.fsu.edu/taxonomy/term/131) FSU Foundation rules say that gift cards are cash equivalents and that a participant receiving $600 or more in a calendar year needs a 1099. [fsu](https://foundation.fsu.edu/sites/foundation.fsu.edu/files/documents/forms-and-resources/Disbursement-Policy-and-Procedures.pdf) [fsu](https://foundation.fsu.edu/sites/foundation.fsu.edu/files/documents/forms-and-resources/FSUF-Expenditure-Policy.pdf) Ask whether FSU-employee participants (postdocs, staff) are treated differently. [fsu](https://foundation.fsu.edu/sites/foundation.fsu.edu/files/documents/forms-and-resources/Disbursement-Policy-and-Procedures.pdf)
- **Fit with August 2027.** Submit to OHSP in January 2027 and allow up to 6 weeks including revisions, giving approval by early March. Recruit in March, run 16–24 sessions from March to May, and analyse in June–July. That fits, with about one month of slack. Submitting after March puts the IUI deadline at risk.

### 6. Open access and money

- **ACM Open.** The ACM Open participant list (1,835 participants when fetched) does **not** include Florida State University; the US list goes from "Florida Institute of Technology" to "Ford Motor Company." [acm](https://libraries.acm.org/acmopen/open-participants) The IUI 2027 call says APCs are waived only if the corresponding author's institution participates. [acm](https://iui.acm.org/2027/call-for-papers/) [siggraph](https://www.siggraph.org/news/acm-open-acm-digital-library-and-publishing-with-acm/)
- **APC levels.** For 2026, ACM subsidised APCs at "$250 APC for ACM/SIG members, $350 for non-members" (IUI 2027 call). [acm](https://iui.acm.org/2027/call-for-papers/) For 2027, the CHI 2027 Papers call states: "APC for 2027 is $500 for ACM/SIG members and $750 for non-members"; the Web Conference 2027 demo call gives the same figures. The Web Conference 2027 demo call also warns that "2027 will be the final year of this subsidy and in the future APC pricing will be based on the actual cost of publishing," so if the IUI 2028 proceedings are published in 2028, the $500/$750 rate may not apply.
- **Extended abstracts.** CHI says interactive demos are published as an "extended abstract" type that "will not be charged an article processing charge." [acm](https://chi2027.acm.org/authors/interactive-demos/) Check whether the SIGIR demo paper type is APC-eligible on ACM's article-types page.
- **Membership.** At least one ACM/SIG member author lowers the APC, and SIGIR travel grants require SIGIR membership. [sigir](https://sigir.org/general-information/travel-grants/) [acmse](https://acmse.net/2027/wp-content/uploads/sites/8/2026/06/CFP-ACMSE2027-v0.1.pdf) Join ACM, SIGIR and SIGCHI now.

---

## Details: Checklists per Submission

### A. ACM SIGIR 2027 — Demonstration paper (San Jose, July 18–24, 2027)

*Official pages: SIGIR 2027 full-paper call https://sigir2027.org/pages/submit-full.html (2027 rules that probably carry over); tracks page https://sigir2027.org/pages/submit-tracks.html (demo call still a placeholder); SIGIR 2026 submission policies https://sigir2026.org/en-AU/pages/submissions/submission-policies-and-information; SIGIR 2025 demo call https://sigir2025.dei.unipd.it/call-demo-papers.html (older edition); SIGIR travel grants https://sigir.org/general-information/travel-grants/.*

**Start now (Oct–Nov 2026)**
- [ ] Make the repository public under the name Mycelium with the final licence (see Key Finding 2).
- [ ] Create OpenReview profiles for both authors using institutional emails. The SIGIR 2027 full-paper call warns that "signing up for a profile can take up to two weeks," requires DBLP import for authors with ≥10 DBLP papers, and treats incomplete profiles as grounds for desk rejection. [sigir2027](https://sigir2027.org/pages/submit-full.html) Whether demos use OpenReview or EasyChair (SIGIR 2025 demos used EasyChair) is **unknown for 2027**. [unipd](https://sigir2025.dei.unipd.it/call-demo-papers.html)
- [ ] Join ACM and SIGIR, which is needed for SIGIR student travel grants. [sigir](https://sigir.org/general-information/travel-grants/)
- [ ] Build a **public demo instance with synthetic profiles only**: fake researchers, open papers and public funding calls, with no real user's data. The SIGIR 2025 demo call (previous edition) required "a link a) to a video recording or b) to the online web interface… (login details shall be specified in your submission if applicable)." [unipd](https://sigir2025.dei.unipd.it/call-demo-papers.html) Offer a no-login guest mode, or a shared demo credential listed in the paper.

**Before submission (Dec 2026 – Feb 2027)**
- [ ] Watch sigir2027.org for the demo call. Until it appears, plan on the previous-edition rules the user reported for SIGIR 2026: 4 pages plus references, video or live link, single-anonymous review, in the proceedings, due Feb 12, 2026. **We could not open the SIGIR 2026 demo page to re-verify these.**
- [ ] Use the ACM `sigconf` two-column template. The 2027 full-paper call requires ACM CCS concepts and keywords for review. [sigir2027](https://sigir2027.org/pages/submit-full.html)
- [ ] Produce a 3–5 minute captioned screen-capture video. No length rule is published for 2027.
- [ ] Hosting: a small cloud VM or FSU research-computing host with uptime monitoring, running from submission through the conference.
- [ ] Ask the chairs whether a parallel CHI demo is acceptable (Key Finding 4).

**At submission**
- [ ] The author list is final at abstract time for SIGIR full papers ("No changes to authorship… after the abstract submission deadline"). [sigir2027](https://sigir2027.org/pages/submit-full.html) Assume the same for demos.
- [ ] One author may have to agree to review (the full-paper rule asks one author per submission to serve as a reviewer). [sigir2027](https://sigir2027.org/pages/submit-full.html)
- [ ] AI policy: comply with the ACM policy on AI use, [sigir2027](https://sigir2027.org/pages/submit-full.html) and describe Mycelium's own LLM use in the paper as part of the method.

**After acceptance**
- [ ] Camera-ready through ACM TAPS (The ACM Publishing System, which turns author LaTeX or Word source into the final HTML and PDF), plus the e-rights form. The full-paper camera-ready date is proposed as Apr 30, 2027. [sigir2027](https://sigir2027.org/pages/submit-full.html)
- [ ] Registration: SIGIR 2026 required "at least one author from each accepted paper will attend the conference in person". [sigir2026](https://sigir2026.org/en-AU/pages/submissions/submission-policies-and-information) The 2027 full-paper call lists author registration on Apr 30, 2027. [sigir2027](https://sigir2027.org/pages/submit-full.html) SIGIR 2025 demos accepted "no pre-recorded videos" in place of attendance. [unipd](https://sigir2025.dei.unipd.it/call-demo-papers.html)
- [ ] SIGIR student travel grant: the window "will open directly following the acceptance notifications and will remain open for approximately two weeks." The student must be a SIGIR member and the presenter, and the advisor must submit a statement of support. [sigir](https://sigir.org/general-information/travel-grants/) At SIGIR 2025 the award covered "the cost of registration and also a stipend of USD1200." Do **not** register before the decision, because "SIGIR Awards cannot reimburse you for the registration." [unipd](https://sigir2025.dei.unipd.it/student-grants.html) SIGIR 2025 also had NSF-funded grants for US-based students. [unipd](https://sigir2025.dei.unipd.it/nsf-student-grants.html)
- [ ] Booth: bring a laptop running the local version as a fallback for conference Wi-Fi.

**What reviewers look for.** SIGIR 2027 full papers are judged on "novelty, technical depth, elegance, practical or theoretical impact, and presentation". [sigir2027](https://sigir2027.org/pages/submit-full.html) The demo criteria are unpublished. SIGIR 2026 accepted **24 demo short papers** (for example Peerispect, which came with a "live, publicly available demo" and a video tutorial, and MCP Servers for Pyserini and RankLLM). [sigir2026](https://sigir2026.org/en-AU/pages/program/accepted-papers) [sigir2026](https://sigir2026.org/program.html) A demo needs a working system and a clear IR contribution: hybrid BM25 plus compact-embedding retrieval, deterministic citation checking, and on-premise and laptop deployment. It needs a small evaluation (latency and memory on a laptop, retrieval quality on a small labelled set, early usage figures), not a user study. SIGIR 2027 lists "Scientific literature search and discovery," "Agentic IR," and "attribution, grounding" as topics, [sigir2027](https://sigir2027.org/pages/submit-full.html) so position Mycelium there.

### B. US-RSE'27 — Papers track (Ann Arbor, Oct 25–27, 2027; due tentatively mid-April 2027)

*Official pages: USRSE'26 call (previous edition) https://us-rse.org/usrse26/participate/; IEEE templates https://www.ieee.org/conferences/publishing/templates; IEEE AI-generated-text guidelines (linked from the US-RSE call); USRSE'24 travel page https://us-rse.org/usrse24/attend/travel/ (older edition).*

**Start now**
- [ ] Track the USRSE'27 site. The announcement exists in the USRSE/usrse27 GitHub repository (Oct 21, 2026) [github](https://github.com/USRSE/usrse27/pull/8) but we could not read it on us-rse.org.
- [ ] Keep a deployment log from today (users, briefings generated, failures, hardware) as raw material for an experience paper.

**Before submission (previous-edition rules, USRSE'26)**
- [ ] Paper: "10 page maximum… includes figures. References and the statement of connection to the US-RSE community will not be included in the paper length limit," IEEE Manuscript Template, PDF. [us-rse](https://us-rse.org/usrse26/participate/)
- [ ] A statement of under 300 words on how the work connects to "the Mission, Goals, & Interests of the US-RSE Community." [us-rse](https://us-rse.org/usrse26/participate/)
- [ ] Originality: "original work, not published elsewhere." [us-rse](https://us-rse.org/usrse26/participate/) Keep it distinct from the SIGIR demo.
- [ ] AI disclosure follows IEEE's guidelines on AI-generated text, which the US-RSE call names as "our community's policy". [us-rse](https://us-rse.org/usrse26/participate/) Read the IEEE page for where to disclose.
- [ ] Single-anonymous or double-anonymous review is **not stated** in the USRSE'26 call; ask.

**At submission**
- [ ] EasyChair (USRSE'26). "There will be no extensions." [us-rse](https://us-rse.org/usrse26/participate/)

**After acceptance**
- [ ] Previous-edition timeline: notification Jul 28; camera-ready Sep 25; a 15-minute talk plus 5 minutes of Q&A; publication on Zenodo, with a DOI; an invitation to submit to a post-conference special journal issue. [us-rse](https://us-rse.org/usrse26/participate/) The 2026 journal is not identified. USRSE'25 used *Future Generation Computer Systems* according to a BSSw recap, which is not an official source. [bssw](https://bssw.io/blog_posts/usrse-25-conference-recap-code-practices-and-people)
- [ ] Travel: USRSE'26 lists Schmidt Sciences as providing "Attendee Travel and Registration Support". [us-rse](https://us-rse.org/usrse26/) The 2026 terms were not found. USRSE'24 (older edition) covered "up to $2100" with "priority… to those having an accepted submission," plus up to $500 for dependent care. [us-rse](https://us-rse.org/usrse24/attend/travel/)
- [ ] Registration and in-person rules for authors: not found; ask.

**What reviewers look for:** "quality, relevance, and novelty" (USRSE'26). [us-rse](https://us-rse.org/usrse26/participate/) An experience paper should show transferable lessons for other RSEs: architecture choices for self-hosting, testing deterministic output checking, privacy, and costs.

### C. JOSS — Software paper (rolling)

*Official pages: submission requirements https://joss.readthedocs.io/en/latest/submitting.html; review checklist https://joss.readthedocs.io/en/latest/review_checklist.html; editorial guide https://joss.readthedocs.io/en/latest/editing.html; scope page https://joss.theoj.org/about; JOSS blog post on generative AI (Jan 2026) https://blog.joss.theoj.org/2026/01/preparing-joss-for-a-generative-ai-future.*

**Start now**
- [ ] Publish the repository (mid-November 2026 at the latest), with an OSI licence file, tagged releases, CI, tests, documentation, CONTRIBUTING, and public issues and pull requests. [readthedocs](https://joss.readthedocs.io/en/latest/submitting.html)
- [ ] Separate a **core library** (retrieval, recommendation, citation checking) from the web application. JOSS's "Submitting a paper" documentation says web-based tools "may be considered 'in scope' for JOSS, provided that they meet one or both of the following criteria: 1) they are built around and expose a 'core library' through a web-based experience… or 2) the web application demonstrates a high-level of rigor with respect to domain modeling and testing." A core library is therefore one of two routes, not a strict requirement, but it is the clearer route for Mycelium.
- [ ] Get ORCID iDs for both authors.

**Before submission (from ~May 2027)**
- [ ] Gate checklist: more than six months public with development "distributed across that period"; "evidence the software is actually being used for research"; open-source practice. [readthedocs](https://joss.readthedocs.io/en/latest/editing.html) JOSS also states that it "requires that software should be feature-complete." [theoj](https://joss.theoj.org/about)
- [ ] Paper (750–1,750 words) with the required sections: summary, statement of need, state of the field, software design, research impact statement, and AI usage disclosure. The checklist says the impact statement must give "evidence of realized impact… or credible near-term significance." [readthedocs](https://joss.readthedocs.io/en/latest/review_checklist.html)
- [ ] AI-usage disclosure: JOSS permits generative AI but "all such use must be disclosed," and "failure to provide a complete and accurate disclosure… may be considered an ethical breach." [readthedocs](https://joss.readthedocs.io/en/latest/submitting.html) Note that JOSS gives extra scrutiny to "rapid AI-assisted code generation." [theoj](https://blog.joss.theoj.org/2026/01/preparing-joss-for-a-generative-ai-future)

**At submission**
- [ ] Submit through the JOSS web form with a paper.md and paper.bib in the repository. Reviewers must work through the public checklist. JOSS requires at least two reviewers. [readthedocs](https://joss.readthedocs.io/en/latest/editing.html)

**After acceptance**
- [ ] Archive the release on Zenodo or a similar service and supply the DOI. JOSS currently asks for the archive DOI after review (per JOSS-using projects; confirm in the docs). [github](https://github.com/DirkKuiper/flits/issues/95) JOSS has no APC.

### D. ACM IUI 2028 — Full paper (deadline expected ~August 2027)

*Official pages: IUI 2027 call (previous edition) https://iui.acm.org/2027/call-for-papers/; ACM authorship and AI policy https://www.acm.org/publications/policies/new-acm-policy-on-authorship; ACM human-participants policy https://www.acm.org/publications/policies/research-involving-human-participants-and-subjects; SIGCHI accessibility guide https://sigchi.org/resources/guides-for-authors/accessibility/; SIGCHI video guide https://sigchi.org/resources/guides-for-authors/videos/; ACM simultaneous-submissions policy https://www.acm.org/publications/policies/simultaneous-submissions; ACM Open participants https://libraries.acm.org/acmopen/open-participants; FSU OHSP review pathways https://www.research.fsu.edu/research-offices/ohsp/human-research-review/review-pathways/; FSU IRB timing FAQ https://knowledgebase.research.fsu.edu/s/article/How-long-will-it-take-for-OHSP-or-the-IRB-to-approve-of-my-study.*

**Start now**
- [ ] CITI training for both authors; CAMS disclosures; draft the protocol, information sheet, recruitment text and compensation plan.
- [ ] Pre-register the study design (conditions, counterbalancing, measures). This is good practice for within-subjects designs and helps with rigour.
- [ ] Ask FSU Libraries about ACM Open, and budget for the APC.

**Before submission**
- [ ] IRB approval or exempt determination before the first participant (target early March 2027). [fsu](https://www.research.fsu.edu/research-offices/ohsp/)
- [ ] Template: ACM TAPS single-column, LaTeX `\documentclass[manuscript,review,anonymous]{acmart}`. [acm](https://iui.acm.org/2027/call-for-papers/)
- [ ] Length (IUI 2027): "We encourage authors to stay within an 8,000 word limit". Above 10,000 words, add a justification note. References, captions, the GenAI Usage Disclosure and appendices do not count. [acm](https://iui.acm.org/2027/call-for-papers/)
- [ ] Anonymize everything (Key Finding 3), including the video and the anonymized repository mirror.
- [ ] Include a human-subjects note for reviewers. IUI says "authors are asked to submit a short note to reviewers that provides this context." [acm](https://iui.acm.org/2027/call-for-papers/) [acm](https://chi2027.acm.org/authors/interactive-demos/)
- [ ] Make the PDF accessible: alt text, tagged PDF, reading order (SIGCHI guide). Caption any video. [acm](https://iui.acm.org/2027/call-for-papers/)
- [ ] Societal-impact reflection; IUI "encourage[s]" it. [acm](https://iui.acm.org/2027/call-for-papers/)
- [ ] Generative AI: ACM "no longer requires the disclosure" of AI used for writing, but AI used *in the research* "must be described in detail in the methods section." [acm](https://iui.acm.org/2027/call-for-papers/) Mycelium's MoE model and decision models are part of the method.

**At submission**
- [ ] Precision Conference System (PCS): SIGCHI → IUI → Papers. The abstract deadline comes a week before the paper (2027 pattern). [acm](https://iui.acm.org/2027/call-for-papers/) Create the PCS account early.
- [ ] Upload anonymized versions of any concurrent related submissions, or face desk rejection. [acm](https://iui.acm.org/2027/call-for-papers/)

**After acceptance**
- [ ] Rebuttal about a week after initial notification (2027 pattern), then TAPS camera-ready about ten days after the final decision. [acm](https://iui.acm.org/2027/call-for-papers/)
- [ ] Registration: IUI 2027 requires at least one author to register (not workshop-only), "attend in person, and present." [acm](https://iui.acm.org/2027/call-for-papers/) IUI 2026 required the *full* (non-student) rate and "one registration covers one paper only." [acm](https://iui.acm.org/2026/call-for-papers/) The 2028 rule is unknown, so budget for a full registration.
- [ ] APC, unless FSU joins ACM Open. [siggraph](https://www.siggraph.org/news/acm-open-acm-digital-library-and-publishing-with-acm/)

**What reviewers look for.** IUI expects claims to be "supported by rigorous evidence appropriate to the claims (e.g., user study…)." Its topics include "user control and steering of LLMs and agents" and "mixed-methods evaluations." [acm](https://iui.acm.org/2027/call-for-papers/) A within-subjects study with 16–24 participants should use counterbalancing, a credible baseline condition (for example the same engine without continuous steering or memory), pre-specified measures, and qualitative analysis. Expect reviewers to ask about the novelty of the steering and memory interaction compared with existing ideation and "AI scientist" tools.

### E. Optional: CHI 2027 interactive demo (Pittsburgh, May 10–14, 2027)

*Official page: https://chi2027.acm.org/authors/interactive-demos/*
- [ ] Due **Jan 21, 2027** via PCS. Up to 6 pages excluding references, ACM single-column; an abstract of 150 words or fewer; a **walkthrough video of ≤5 minutes** (3 minutes recommended), accessible and captioned; a still image of at least 1920×1080 px with an image description; a floor plan and equipment list. The booth is about 2 m × 2 m with a table, Wi-Fi and power; outlets must be specified at submission. The total upload is ≤250 MB. [acm](https://chi2027.acm.org/authors/interactive-demos/)
- [ ] Not anonymous. The author list freezes at submission. Prior work is allowed "as long as the demonstration adds a novel aspect". [acm](https://chi2027.acm.org/authors/interactive-demos/)
- [ ] After acceptance: notification Feb 18; e-rights Feb 25; TAPS Mar 4; publication-ready Mar 18 (double-column, ≤4 pages). Published as an extended abstract with no APC. In-person presentation by a registered presenter is required. Plan for queues and a maximum of 5 minutes per person. [acm](https://chi2027.acm.org/authors/interactive-demos/)

### F. Optional: workshop papers (e.g., NeurIPS AI-for-science workshops)
We did **not** research specific 2027 workshop calls. Rules vary by workshop, so read each call for whether it is archival, its page limits, and whether it is anonymized. Non-archival workshop papers generally do not count as prior publication at ACM venues, but confirm this against IUI's concurrent-submission rule and declare the workshop paper if it reports the same study.

---

## Summary by Submission Type

| Type | What they share | Main risks |
|---|---|---|
| **Demo (SIGIR, CHI, IUI demos)** | Short paper (4–6 pp); video ≤5 min with captions; usually live public access without login; in-person booth; usually not anonymous or single-anonymous; light evaluation | Downtime; real user data on screen; overlapping demos counting as prior publication |
| **Research paper (IUI)** | Double-anonymous; rigorous evaluation; ethics note; anonymized supplements; rebuttal; APC unless the institution is in ACM Open; one in-person registered author | Anonymity leaks via named repo or video; IRB delay; undeclared concurrent submissions |
| **Community conference paper (US-RSE)** | Original, practice-oriented lessons; community-fit statement; Zenodo DOI; journal special issue | Repeating the demo paper; vague "lessons" |
| **Journal software paper (JOSS)** | Gates on public history, research use and open practice; short paper; public review; AI disclosure; archive DOI | Premature submission → public desk rejection and six-month wait |
| **Workshop paper** | Usually short and often non-archival; fast feedback | Must still be declared if it overlaps a later archival paper |

**Reusable lessons.** Create accounts (OpenReview, PCS, ORCID, ACM/SIG membership) at least a month before any deadline; the CHI 2027 Papers call, for example, states that "All authors are required to have an ORCID and the DBLP field on their profile has to be filled in" and that "The affiliations entered in PCS during submissions are final." Keep one canonical synthetic demo dataset. Keep captioned 3- and 5-minute video cuts. Maintain an AI-use log from day one, because JOSS and IEEE ask for disclosure and ACM asks for AI-in-method description. Ask FSU about ACM Open once and record the answer.

---

## Backward-Planned Calendar (Oct 2026 – Mar 2028)

| When | Action |
|---|---|
| **Late Oct – mid Nov 2026** | Finalise licence → **make repository public** (by Nov 15). ACM, SIGIR and SIGCHI memberships. OpenReview, PCS and ORCID accounts. CITI training. Ask FSU Libraries about ACM Open. Start the deployment log |
| **Nov – Dec 2026** | Build the synthetic-data public demo instance. Draft the IRB protocol (information sheet, recruitment, compensation). Record the demo video. Draft the CHI demo |
| **Jan 2027** | Submit IRB application in RAMP (by ~Jan 15). **Jan 21: CHI interactive demo.** [acm](https://chi2027.acm.org/authors/interactive-demos/) Watch for the SIGIR 2027 demo call (SIGIR full-paper abstract Jan 14 and paper Jan 21, proposed) |
| **Feb 2027** | **SIGIR demo** (previous edition due ~Feb 12). Feb 18: CHI notification; Feb 25: CHI e-rights [acm](https://chi2027.acm.org/authors/interactive-demos/) |
| **Mar 2027** | Mar 4 CHI TAPS; Mar 18 CHI publication-ready. [acm](https://chi2027.acm.org/authors/interactive-demos/) IRB approval expected → begin recruitment and pilot |
| **Mar – May 2027** | Run the 16–24-person within-subjects study |
| **Apr 2027** | SIGIR notification (full paper Apr 5, proposed) → **SIGIR travel grant window (~2 weeks)**. [sigir](https://sigir.org/general-information/travel-grants/) Camera-ready and author registration ~Apr 30. **Mid-April: US-RSE'27 paper (tentative)** |
| **May 2027** | CHI conference (May 10–14). [acm](https://chi2027.acm.org/) **JOSS eligible from ~May 16** if public by Nov 15 → submit once the research-use evidence is documented. Book SIGIR travel |
| **Jun – Jul 2027** | Analyse the study; write the IUI paper. **SIGIR July 18–24.** US-RSE notification (previous edition Jul 28). Apply for US-RSE travel support |
| **Aug 2027** | **IUI 2028 abstract and paper** (previous edition Aug 13 / Aug 20). Upload anonymized concurrent submissions |
| **Sep 2027** | US-RSE camera-ready (previous edition Sep 25). Book Ann Arbor travel |
| **Oct 2027** | **US-RSE'27, Oct 25–27.** IUI initial reviews (previous edition ~Oct 29) |
| **Nov – Dec 2027** | IUI rebuttal (~1 week), final decision (~late Nov), TAPS camera-ready (~early Dec), APC payment. US-RSE special-issue submission if invited. JOSS review revisions |
| **Jan – Mar 2028** | IUI 2028 conference (previous edition held in February). Register at full rate, attend and present in person |

---

## Recommendations

1. **Publish the repository in November 2026.** This is the most valuable single action, because it unlocks JOSS before IUI and is needed for the CHI and SIGIR live demos.
2. **Submit the IRB application by mid-January 2027.** Ask OHSP for a pre-submission consultation in December about exempt category 3 versus expedited, given screen and log recording.
3. **Give each paper a separate contribution:** SIGIR = IR system demo; CHI = interaction demo (optional); US-RSE = RSE experience and engineering lessons; JOSS = software artifact; IUI = hypothesis-engine study, with Mycelium cited in the third person.
4. **Do the CHI demo only if the SIGIR demo chairs confirm** that an accepted CHI extended abstract will not count as prior publication.
5. **Budget** for an IUI APC (the CHI 2027 Papers call gives the 2027 rate as $500 for ACM/SIG members and $750 for non-members, and the Web Conference 2027 demo call says 2027 is "the final year of this subsidy," so a 2028 publication may cost more), full-rate IUI registration, and travel to San Jose, Ann Arbor and possibly Pittsburgh. Apply for SIGIR and US-RSE student support.

## Positioning (not source-verified in this research; treat as a starting list)
Reviewers are likely to compare Mycelium with free scholarly alert feeds (Google Scholar alerts, Semantic Scholar feeds, arXiv listings), paid AI research assistants (e.g., Elicit, Consensus), funding-opportunity databases (e.g., Pivot, GrantForward), and "AI scientist" or co-scientist systems. Mycelium's differentiators should be stated plainly: it is self-hosted down to a laptop; it covers papers, grants, fellowships and conferences in one profile; deterministic citations and output checking; and human-approved profile changes. For IUI, the hypothesis engine must be set against ideation and literature-review tools on the axis of continuous steering plus per-topic memory. We did not collect accepted RecSys, IUI, CHI or US-RSE comparison papers in this pass, which is a gap to fill.

## Open Questions

**To SIGIR 2027 demo chairs:** Demo deadline, submission system (OpenReview or EasyChair), single- or double-anonymous review, video length? Does a CHI 2027 extended abstract on the same system count as prior publication? Is live-link uptime checked? Is the demo article type APC-exempt?

**To US-RSE'27:** Confirm dates, venue and deadline. Is review anonymous? Which journal hosts the special issue? Registration rules for presenters? Travel-support terms and deadline?

**To IUI 2028 chairs (when the call appears):** Is a public, named predecessor system acceptable if cited in the third person? Can the anonymized supplement link to an anonymous repository mirror? Must presenters register at the full rate?

**To JOSS editors:** Does deployment in one FSU department plus demo and conference papers meet the research-use gate? Must the web application and core library be separate repositories?

**To FSU OHSP/IRB:** Exempt category 3 or expedited for a within-subjects study with interaction logs and screen or audio recording? Information sheet or full consent? Can FSU employees or students be paid participants, and through which gift-card route? Data retention rules for logs?

**To FSU Libraries / Office of Research:** Is FSU joining ACM Open (or a Florida consortium deal) before 2028? Can the department or library cover ACM APCs?

**To FSU Travel / Controller and the Graduate School:** Booking lead times and pre-approval for travel to San Jose, Ann Arbor and Pittsburgh? Rules on whether registration can be prepaid? Graduate-student conference travel grants and their deadlines?

## Caveats
- The SIGIR 2027 demo call, the USRSE'27 call and the IUI 2028 call were unpublished on Oct 25, 2026. Rules marked "previous edition" may change.
- We could not open the SIGIR 2026 demo-track page itself. The SIGIR 2026 demo rules quoted (4 pages, video or link, single-anonymous, Feb 12) come from the user's brief and from the SIGIR 2025 demo call.
- The SIGIR 2027 full-paper dates are explicitly "PROPOSED." [github](https://github.com/ccfddl/ccf-deadlines/pull/3075)
- ACM Open membership was checked against the participant list on the date of research. FSU could join later. [acm](https://libraries.acm.org/acmopen/open-participants)
- The 2027 APC figures ($500 members / $750 non-members) come from conference calls (CHI 2027 Papers, Web Conference 2027 demos), not from an ACM policy page; the 2028 rate is not yet announced.
- FSU IRB timing figures date from 2023 [fsu](https://hub.research.fsu.edu/newsletter/article/updates-office-human-subjects-protection) and depend on complete applications. [fsu](https://knowledgebase.research.fsu.edu/s/article/How-long-will-it-take-for-OHSP-or-the-IRB-to-approve-of-my-study)
- We did not verify: ACM artifact badges (no target venue's call mentions artifact evaluation, so badges likely do not apply); SIGCHI travel grants; specific NeurIPS workshop calls; or competitor details.