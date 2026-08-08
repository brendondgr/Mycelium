# Does team-level disciplinary complementarity help or hurt? — evidence interrogation

Compiled 2026-08-06, in response to a challenge to an earlier claim in
[`SYNTHESIS.md`](SYNTHESIS.md) §5 that the KG-teaming hypothesis was "contradicted by evidence."

**The challenge was correct. The earlier claim was wrong.** It conflated *individual/proposal*
interdisciplinarity with *team-level complementarity*. This file records the verification.

Provenance is marked per section: full paper text, publisher abstract, or secondary source.

---

## The construct split

Two different things travel under "interdisciplinary research":

| | Definition | Example |
|---|---|---|
| **Individual / proposal ID** | One person or one project spanning several fields | A single PI writing a project that ticks four Field-of-Research codes |
| **Team-level complementarity** | Two or more *specialists*, each in their own lane, jointly covering the required fields | PI publishes only in field A; co-I publishes only in field B |

Nearly all of the funding-penalty literature measures the first. The teaming hypothesis is about
the second. Banal-Estañol et al. (2019) is the only study located that measures both separately
and reports different results for each.

---

## 1. Bromham, Dinnage & Hua, *Nature* 534:684–687 (2016)

*Verified from full paper text.*
https://www.nature.com/articles/nature18315 ·
[PDF mirror](https://pastglobalchanges.org/sites/default/files/download/docs/pdf/nature18315.pdf)

**Unit: the proposal, not the team.** The interdisciplinary distance (IDD) score is computed
entirely from **Field of Research codes the applicant ticks on the application form**, plus the
percentage weight they assign to each:

> "Every application must nominate at least one of a defined set of 1,238 Field of Research
> codes, assigning a percentage weighting to each code selected."

No investigator publication histories, affiliations, or citation data are used. The ARC data was
de-identified.

**The authors disclaim the team reading explicitly:**

> "IDD reflects the interdisciplinarity of the project, **not the inclusion of practitioners from
> different disciplines**, because a single researcher can devise a project that spans different
> disciplinary traditions."

**Measure.** Not Rao–Stirling. Phylogenetic species evenness (Helmus et al. 2007) over a
dendrogram of the FoR code hierarchy — captures balance + disparity, standardized 0–1. Variety
(number of codes) is a separate covariate and robustness check.

**Team size was controlled, and its effect was positive:**

> "To test the influence of collaboration, we added the number of named chief investigators to the
> analysis. We find that proposals with **more chief investigators have slightly higher success
> rates (slope = 0.03, P = 0.003)**, across all research fields... Although the relationship
> between number of chief investigators and IDD is positive, the effect is small (Spearman's
> ρ = 0.09), suggesting that the number of participants is not strongly associated with the
> interdisciplinarity of the project proposal."

So within this paper: more investigators → *higher* success, and team size is close to orthogonal
to the interdisciplinarity that gets penalized.

**Effect size.** Main model slope = −0.40 on the logit, P = 1.1×10⁻¹¹, n = 18,476. Fitted
`success = logit⁻¹(−1.35506 − 0.40268 × IDD)` → ≈**20.5% at IDD = 0 down to ≈14.7% at IDD = 1**
(arithmetic from their published equation; these percentages are not printed in the paper).
Division-level model IDD coefficient −0.68. Scheme baseline success 15–20%.

**Authors' own caveat on causation:** "*Whatever the cause of the correlation*..." — they
explicitly float lower average proposal quality as a live alternative to reviewer bias.

**Critiques.** No formal replication failure, rebuttal letter, or *Nature* Matters Arising found.
The main published commentary (Bammer, i2Insights / LSE Impact,
https://i2insights.org/2016/08/23/interdisciplinary-research-funding/) accepts the result and
debates *why*, while noting that "interdisciplinary research" spans everything "from one person
borrowing from other disciplines... to teams working at the interface of two or more disciplines"
— the same construct conflation. Honest state: the finding is not refuted, it is about something
else.

---

## 2. Boudreau, Guinan, Lakhani & Riedl, *Management Science* 62(10):2765–2783 (2016)

*Verified from publisher abstract.*
https://pubsonline.informs.org/doi/10.1287/mnsc.2015.2285 ·
[HBS record](https://www.hbs.edu/faculty/Pages/item.aspx?num=48056)

> "the 'intellectual distance' between the knowledge embodied in research proposals and **an
> evaluator's own expertise** systematically relates to the evaluations given... we randomized
> the assignment of evaluators and proposals to generate 2,130 evaluator–proposal pairs. We find
> **evaluators systematically give lower scores to research proposals closer to their own areas
> of expertise** and to highly novel research proposals."

**Entirely about evaluator–proposal distance. Team composition is not a variable.** Citing it
against multi-specialty team assembly is a misuse. And the distance result runs backwards from
how it is usually invoked — reviewers were harsher on proposals **near** their expertise. Only
the novelty penalty is a headwind, and novelty ≠ team composition.

---

## 3. Banal-Estañol, Macho-Stadler & Pérez-Castrillo, *Research Policy* 48(7):1823–1840 (2019)

**The paper that is squarely on point.** *Verified from full working-paper text.*
[Working paper PDF](https://bse.eu/sites/default/files/working_paper_pdfs/890_0.pdf) ·
[Published](https://www.sciencedirect.com/science/article/abs/pii/S004873331930099X)

Data: 17,835 EPSRC grant applications, 1996–2007; 3,786 academics across 40 UK engineering
departments. Unit = a team application. Award rate 34%; mean team size 2.5.

**Measurement.** Investigator field diversity computed **from each team member's own prior 5-year
publication record**, mapped to WoS subject categories → 15 Leydesdorff–Rafols fields. They
construct a variable that is essentially the teaming target:

> "**num additional fields** — # of fields where the team has published but the PI has not"

explained with exactly the two-specialists scenario:

> "Suppose a two-member team in which the PI has only published in field A whereas the other team
> member has only published in field B. This team should have **no individual-level diversity**
> of knowledge because it is composed of **two specialists**, whereas it exhibits **team-level
> diversity**... the Blau's index of fields of each researcher would be 0 whereas the num
> additional fields variable would be 1."

**Finding 1 — funding penalty (the real threat):**

> "Columns 2, 3, 4 and 5 show that the level of team diversity in knowledge and skills **decrease
> the likelihood of the team obtaining the grant**. The coefficient of... (num additional fields),
> the heterogeneity of fields (Blau index fields team) and the coefficient of variation of
> research type... are negative and significant."

Team size also reduces award probability, with diminishing effect.

**Finding 2 — impact benefit:**

> "column 2 points at a **significant positive effect of the team diversity in knowledge (num
> additional fields)**" on ex-post success (top-25% normalized citations).

Note the asymmetry: only *num additional fields* (team-level complementarity) and educational
diversity are significantly positive ex-post. **Individual-level interdisciplinarity
(within-person Blau/Shannon) is penalized ex-ante and is *not* significant ex-post.**

**Finding 3 — the penalty is offsettable:**

> "the prestige of the PI has a strong positive effect in mitigating the negative impact of
> diversity. The coefficients of the interaction terms are all positive and... highly
> significant. Moreover, **the sum of the coefficient of the interaction term and the main effect
> is often close to zero, indicating that the negative effect of diversity is not only mitigated
> but offset if the team is led by a prestigious PI**."

**Authors' conclusion:**

> "diverse teams are not only penalized but are also **biased against**... On ex-post performance,
> our results suggest that **diverse teams are more likely to generate high-impact research**...
> Even team size... tends to simultaneously decrease the likelihood of ex-ante approval and
> increase the likelihood of ex-post success."

They also checked and found **no** effect of demographic diversity (gender, academic age, rank)
on either award or ex-post success.

**Caveats.** UK engineering only, 1996–2007. PI-prestige proxied by full professorship. Ex-post
sample small (963 publications from 1,493 grants). The authors state: "our database does not
allow us to measure project novelty and separate project novelty from team diversity" — so part
of the funding penalty may be a novelty penalty rather than a composition penalty. Their ρ
estimates suggest the selection correction was not doing much work.

---

## 4. Wanzenböck, Lata & Ince, *QSS* 1(3):1136–1158 (2020)

*Full text read; every table checked.*
https://direct.mit.edu/qss/article/1/3/1136/96101/

7,208 proposals, H2020 Societal Challenges pillar, 2014–2016.

**There is no disciplinary-diversity variable in this paper at all** — no Blau/Shannon/HHI over
partner fields, no cognitive-distance measure. Multidisciplinarity appears only in the theory
section, never operationalized; the authors note that semantic/text-mining methods "would be
necessary" to reach proposal content.

What consortium composition did predict (MLR on main-list/above-threshold, McFadden R² ≈ 0.09):

| Variable | Effect |
|---|---|
| **Consortium size** | **Positive, highly significant** (0.069\*\*\* / 0.074\*\*\*; OLS on expert score 0.151\*\*\*) |
| Coordinator FP7 experience | Strongly positive (0.336\*\*\*) |
| Top-50 universities in consortium | Positive (0.227\*\*\*) |
| Share of universities (HES) | **Negative** (−0.010\*\*\*); firms (PRC) and research orgs (REC) positive |
| CEE partners | Strongly negative (−0.228\*\*\*) |
| Prior acquaintance | Tiny positive on status, **significantly negative** on expert score (−0.002\*\*) |
| Network centrality | Significant for clearing threshold, **not** significant at the main-list margin |

Net: neutral-to-favourable for the teaming hypothesis. Institutional/sector heterogeneity and
larger consortia are rewarded; the paper simply has nothing to say about disciplinary mix.

---

## 5. Xiang, Romero & Teplitskiy, *PNAS* 122(16):e2409752122 (2025)

*Verified from publisher abstract.* https://www.pnas.org/doi/10.1073/pnas.2409752122

**Unit: manuscripts, not teams.** 128,950 S&T manuscripts with peer-review data. Two constructs
measured on the *submission*:

- **Topic** interdisciplinarity (from title/abstract): 1 SD → **1.2 pp lower** acceptance.
- **Knowledge-base** interdisciplinarity (from references): 1 SD → **0.9 pp higher** acceptance.

Interpretation: topic ID "cut[s] across disciplinary evaluation standards and threaten[s]
symbolic boundaries"; knowledge-base ID benefits from "combining a large pool of non-redundant
information." High-topic-ID submissions "did not fare worse if they also had high knowledge-base
interdisciplinarity."

The cleanest published statement of a construct split of this kind — but its unit is the
manuscript. Analogically supportive (breadth of inputs helps; framing is what gets punished);
not team-level evidence.

---

## 6. Evidence for the complementary-specialists framing

- **Lin, Frey & Wu, *Expertise diversity of teams predicts originality and long-term impact in
  science and technology*, arXiv:2210.04422** — https://arxiv.org/abs/2210.04422. *Abstract
  verified only; published version not checked.* Quantifies **expertise distance between team
  members from their prior career histories** across 23M papers and 4M patents: expertise-diverse
  teams "tend to produce work with greater originality... no significant impact advantage in the
  short- (2 years) or mid-term (5 years). Instead, they exhibit substantially higher long-term
  impact (10 years)." Effect strongest when other diversity dimensions are absent (same
  institution/country). Authors explicitly frame implications "for funding, assembling, and
  retaining teams."
- **Uzzi, Mukherjee, Stringer & Jones, *Science* 342:468–472 (2013)** —
  https://www.science.org/doi/10.1126/science.1240474. Highest-impact papers pair a conventional
  core with a tail of atypical combinations; **2× as likely to be highly cited**. And:
  **"teams are 37.7% more likely than solo authors to insert novel combinations into familiar
  knowledge domains."** Shape matters — conventional core plus novel tail, not maximal novelty.
- **Sun, Livan, Ma & Latora, *Communications Physics* 4:263 (2021)** —
  https://www.nature.com/articles/s42005-021-00769-z. *Abstract/secondary only.* 44,419 UK
  research-council grants: interdisciplinary researchers show lower short-run impact and less
  early funding, but "eventually outperform their specialized counterparts in funding
  performance, both in terms of volume and value." Career-level unit → survivorship risk.
- **Nooteboom, Vanhaverbeke, Duysters, Gilsing & van den Oord, *Optimal cognitive distance and
  absorptive capacity*, Research Policy 36(7) (2007)** —
  https://www.sciencedirect.com/science/article/abs/pii/S0048733307000807. Inverted-U confirmed
  for firm alliances: moderate cognitive distance maximizes innovative performance, optimum
  shifting outward for exploratory work. Firm-level alliance data; transfer to academic grant
  teams is an inference. **Implication: "maximize disciplinary distance" is the wrong objective.**

---

## 7. Things that could not be verified

- **Multi-PI vs single-PI NIH R01 success rates.** No credible head-to-head comparison found.
  Search results were dominated by AI-generated SEO content making unsourced claims in both
  directions. NIGMS confirms MPI R01s exist and are ~25% larger in budget, and NIH notes MPI
  accounted for ~20% of major grants by 2013, but no official success-rate breakdown was located.
  https://www.nigms.nih.gov/loop/2024/07/early-stage-investigators-and-multi-pi-r01-grants
  **Treat any claim about MPI success rates as unverified.**
- **Modi et al., *Scientific Reports* 15:4461 (2025), "variability versus atypicality"** —
  **do not cite for this question.** Full text read: variability and atypicality are operationalized
  on **gender, ethnicity and race**, not discipline, and the paper explicitly puts deep-level
  disciplinary attributes out of scope. (For the record: 106 NIH CTSA pilot proposals, racial
  variability −64% funding odds, gender atypicality +139%.)
- Exact Bromham Fig. 2 magnitudes beyond the fitted equation; the published (vs working paper)
  version of Banal-Estañol.

---

## 8. Bottom line

**The teaming hypothesis is not contradicted.** Bromham measures proposal topic spread from
applicant-ticked codes and disclaims the team reading in print; its actual team variable (number
of chief investigators) has a **positive** effect on funding. Boudreau is about reviewer expertise
distance and contains no team variable at all.

**The real threat is narrower and comes from Banal-Estañol et al. (2019):** teams whose members
cover fields the PI does not are **less likely to be funded**, while producing **more high-impact
research**. That is a funding-stage penalty on precisely the object a teaming system assembles.

Read straight, that paper says: build complementary-specialist teams; anchor them under a
high-prestige PI (which fully offsets the penalty in their estimates); expect the evaluation
system to undervalue them; and treat the penalty as bias rather than as evidence of lower quality
— which is how the authors themselves characterise it.

Two design implications:

1. **Target an interior distance optimum**, not maximum distance (Nooteboom; Uzzi's conventional
   core plus atypical tail).
2. **Framing may matter as much as assembly.** Xiang et al. locate the penalty in topic framing
   rather than knowledge breadth, so a system that assembles a broad team *and* helps frame the
   proposal within a recognisable disciplinary home may capture the upside without the evaluation
   cost. Inference across constructs, not a verified finding — but cheap and testable.
