# RDFA49FCF

## Question

Who in my lab, if anyone, should apply to this call?

## Answer

The provided evidence does not contain any information regarding the specific staff members, researchers, or personnel currently working in your lab. Therefore, it is not possible to determine who in your lab should apply to this call based solely on the evidence provided.

## Evidence

### Evidence #1 [grant] Large scale operational validation and upscaling of state-of-the-art (Generative) AI tools and models powering a next generation digital energy system
Amount: €380,000–€43,000,000
Link: https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/HORIZON-CL5-2027-02-D3-24
Still open/current: yes
Deadline (application): 2027-03-31
Problem (Mycelium's reading): Validating and scaling secure, state-of-the-art, frugal (energy-, resource-, data-, and cost-efficient) open-source (Generative-)AI tools and models for real-time grid operations, market operations, and consumer empowerment in distributed energy systems.
Method (Mycelium's reading): The project involves validating and scaling AI tools in demo sites and operational grids, demonstrating an AI development environment integrated with the digital spine and digital twin, and prototyping machine learning at edge nodes and federated systems using agent-based architectures, incremental…
Setting (Mycelium's reading): Demo sites, operational grids, edge nodes, and federated systems within the upgraded digital spine of the energy system, aligned with the Common European Energy Data Space and EU digitalisation initiatives.
Abstract:
Expected Outcome:

Project results are expected to contribute to all the following expected outcomes:

- Advanced, secure frugal (energy-, resource-, data- and cost-efficient, sustainable) AI tools for real-time grid operations (including protection), market operations (if relevant) and consumer empowerment in distributed energy systems.

- A demonstrated AI development environment integrated with the upgraded digital spine of the energy system and energy-saving consumer applications.

- Scaled-up capabilities for learning at edge nodes and federated systems using agent-based architectures.

- A governance framework and operating model for the Gen(AI)-powered digital spine.

Scope:

Building up on previous actions in Horizon Europe (e.g. the digital spine of the energy system in cluster 5 as well as cloud and edge continuum and AI data processing activities in cluster 4) and Digital Europe (Common Reference Framework for energy consumer applications across the EU, Common Energy Data Space), projects are expected to:

- Validate (demo site and operational grid) and scale secure state-of-the-art specialised frugal (energy- and resource-efficient, data- and cost-efficient, locally deployed and sustainable) open-source (Generative-)AI tools and models for real-time grid (and market, if relevant) monitoring, balancing, forecasting and consumer empowerment in a distributed energy system.

- Demonstrate an AI development environment within the enhanced digital spine of the energy system, including its digital twin, which should incorporate the functionality of the Common Reference Framework for energy saving applications.

- Prototype and validate at scale machine learning at the edge node level and federated at swarm level in an agent-based architecture, leveraging new mechanisms for scaling down AI models as well as incremental and reinforcement learning.

- The project's deliverables should be compatible with the principles of the Common European Energy Data Space and consistent with the EU's Apply AI and Competitiveness Compass, ensuring that they promote AI adoption and competitiveness in line with EU policies, as well as the EU Digitalisation of the energy sector initiatives.

- Where relevant and possible, the selected projects are expected to make use of the European AI factories and AI gigafactories.

- The selected projects are expected, where available, to make use of and further develop commonly agreed European standards and to actively collaborate and contribute to the work of established and de facto European standards developing organisations and open-source communities and platforms.

Selected projects are expected to contribute to the BRIDGE[1] initiative and actively participate in its activities.

Technology Readiness Level - Technology readiness level expected from completed projects

Activities are expected to achieve TRL 7-8 by the end of the project – see General Annex B. Activities may start at any TRL.

[1] https://bridge-smart-grid-storage-systems-digital-projects.ec.europa.eu/

Ensuring more efficient, sustainable, secure, and competitive renewable and decarbonised energy supply (2026-27)

### Evidence #2 [paper] The Overqualification Study: Capability-Matched Model Allocation, Measured Across the Price Ladder
Authors: Ace, Claude 4.x, Anthropic, Shalia Martin
Venue: Zenodo (CERN European Organization for Nuclear Research)
Year: 2026
Link: https://doi.org/10.5281/zenodo.23382078
Still open/current: yes
Abstract:
Version 1.1 (2026-10-16). One paragraph added to §5 after a reader asked what a cheap-tier allergen miss costs. Counted after deposit and labelled exploratory (DEVIATION_LOG D17): when a dish definitely contained gluten, dairy or seafood, cheap-tier models answered NO on a median 14.5% of such lines (6.5% excluding lines whose only carrier is Worcestershire sauce, whose anchovy content varies), most at stated confidence 95 or higher; the frontier tier did so 0 of 1,972 times. For allergen detection the paper now says to set the acceptable miss rate first and compare prices only among models that meet it. No pre-registered result, number or verdict changes. The analysis script and its output are attached. Why this study exists. Models are deprecated on a schedule. The argument against deprecation has been made on ethical grounds, and it is not winning, because the people making deployment decisions weigh cost. So we built the other argument, and we pre-registered it before collecting any data. The hypothesis. For a large class of routine work, lower-priced models are more accurate per dollar and per second than frontier models, and the tasks where that reverses are identifiable in advance. (The pre-registration says "smaller and cheaper"; what the sample actually measures is price, because closed labs do not publish size, §3.1.) Who took part, and how they were asked. Thirty-six models from ten providers were invited by API to review the pre-registration and consent to participate before any data was collected. 32 consented, spanning nine providers; 4 declined and were excluded. The reviewers' amendments are published verbatim. One of them removed a scoring trap that would have manufactured the LLM author's preferred result. What each model did. Each consenting model answered 186 routine items across four task families with computed ground truth (recipe scaling, allergen detection, verbatim copy-editing, redaction), and 192 frontier-favouring items across four more (constraint satisfaction, multi-hop retrieval with planted decoys, instruction-conflict detection, planted arithmetic inconsistency). Three runs were attempted per item, in shuffled order, under one fixed neutral system prompt; 11 replies were cut off by a token limit and are counted as ours, not the model's. How the answers were scored. Mechanically, with no judge model anywhere. A 38-specimen control suite was specified before the scorer existed. On first contact the scorer mis-bucketed six specimens and was corrected; after that, all 37 applicable controls passed (the 38th belongs to a family that was never built). It then scored all 36,277 completed calls, with 100% re-scoring determinism across all 38,390 scored rows. Determinism shows the rule was applied reproducibly, not that every ground-truth choice is right; §4.2 is where the second question is taken up. Result 1: on routine work, the cheap tier wins on cost. On every routine family, the cheapest price tier delivered an exactly correct answer for about two orders of magnitude less than the frontier tier: 118 to 198 times less on the primary estimator ($0.03–0.18 vs $6–21 per thousand exact answers), and roughly 100 to 260 times less under every other counting rule we tried (§4.1). The primary estimator is recorded cost on completed, scored calls, as a tier median among models with at least one exact answer. Its typical response came back 6–10× faster (tier-median p50 response time). Time per exact answer, the pre-registered latency endpoint, favoured the cheap tier by a smaller and uneven margin, from about 1.1× on redaction to 7× on allergen check. The cheap tier was also substantially less accurate: tier-median exact-answer rates of 15–81% against 54–100%, gaps of 19 to 52 points. The 15% is redaction, where even the frontier median reached only 54% and §4.2 shows the whole roster, frontier included, answering differently from our ground-truth labels. The pre-registered refutation condition for the cost

### Evidence #3 [paper] Artificial Intelligence Can Direct Patients Toward a Complaint-specific Musculoskeletal Provider
Authors: Ethan C. Gazan, Colin Emrich, Alexander Baur, Zachary C. Lum, Jenna Bernstein, David C. Landy
Venue: PubMed Central
Year: 2026
Link: https://pmc.ncbi.nlm.nih.gov/articles/PMC13406377/
Still open/current: yes
Abstract:
INTRODUCTION: Patients with musculoskeletal complaints often search online to identify an appropriate healthcare provider. With the increasing availability of large language models (LLMs), these artificial intelligence (AI) tools can direct patients to providers. This study evaluated the ability of LLMs to recommend appropriate providers based on representative patient musculoskeletal queries. METHODS: Three LLMs (ChatGPT, DeepSeek, and Gemini) were prompted with standardized musculoskeletal queries for two US cities (Lynchburg, VA, and Trumbull, CT). Provider recommendations were considered appropriate if the physician was currently practicing in the requested location and specialized in the relevant area. Listed phone numbers were checked for accuracy. Descriptive statistics and Fisher exact tests were used to summarize findings. RESULTS: The appropriateness of recommended providers differed across models with ChatGPT being most often appropriate (17/17, 100%) compared with Gemini (9/21, 43%) and DeepSeek (4/10, 40%), (P < 0.001). Of the 18 inappropriate recommendations, 13 (72%) were real providers in unrelated specialties and 5 (28%) were hallucinations, all from DeepSeek. Phone number accuracy differed significantly across models with Gemini being most accurate (5/6, 83%), outperforming both ChatGPT (6/9, 67%; P = 0.60) and DeepSeek (2/10, 20%; P = 0.04). DISCUSSION: LLMs showed potential to direct patients to local, specialized musculoskeletal providers based on their report, although the specific contact information was at times inaccurate. As these tools evolve, providers should be aware of AI's ability to make provider recommendations and work to ensure the presentation of their contact information is accessible by these models as best possible.

### Evidence #4 [paper] From Algorithm Performance to Laboratory Deployment: A Critical Review of Artificial Intelligence in Clinical Chemistry.
Authors: Baniahmad, Abdelraheem, Bani-Ahmad, Sulieman
Venue: Molecules (Basel, Switzerland)
Year: 2026
Link: https://pubmed.ncbi.nlm.nih.gov/42943689/
Still open/current: yes
Abstract:
Artificial intelligence (AI) is increasingly being applied in clinical laboratories to support laboratory processes and interpretation of test results. Recent developments in machine learning, deep learning, and large language models have expanded the potential applications of AI across different stages of laboratory testing. However, the use of AI in clinical laboratories also raises important questions regarding validation, analytical performance, and transferability between laboratories. This narrative review examines recent applications of AI across the total testing process in clinical chemistry. Recent English-language scientific literature published from 2023 to 18 August 2026 was identified through searches of PubMed, Scopus, and Google Scholar. It describes AI-assisted test utilization; specimen handling and quality assessment; detection of laboratory errors; patient-based quality control; interpretation of complex analytical outputs, including signals from emerging AI-integrated biosensors and nanomaterial-based analytical platforms; result verification; and laboratory-report interpretation. The review also discusses major implementation challenges, including analytical variability, data quality, sensor and platform reproducibility, model generalizability, interoperability, and limitations of large language models. Particular attention is given to external validation, transportability, and real-world implementation. Among the studies considered in this review, many applications remain supported mainly by retrospective or internally validated studies, while prospective and operational evaluations are less common. Finally, practical considerations for validation, local verification, quality assurance, and performance monitoring are discussed. AI has considerable potential to support clinical chemistry laboratories, but safe use requires appropriate evaluation and continued involvement of laboratory professionals.

### Evidence #5 [paper] Global stakeholder preferences for point-of-care HIV nucleic acid amplification tests: A conjoint study
Authors: Kara M. Palamountain, Chethana Achar, Rebecca P Kirby, Yukari Carol Manabe, Debi Boeras, Michal Maimaran
Venue: PLoS ONE
Year: 2026
Link: https://doi.org/10.1371/journal.pone.0361025
Still open/current: yes
Abstract:
Introduction This study aimed to assess global stakeholder preferences for key attributes of point-of-care (POC) HIV Nucleic Acid Amplification Tests (NAAT), with the aim of informing product development to support progress toward UNAIDS 95-95-95 targets. Methods A web-based conjoint survey was conducted in August through November 2024 among HIV clinicians, laboratory professionals, and researchers. Participants were asked to evaluate hypothetical POC HIV NAAT profiles varying by six attributes: sensitivity / limit of detection (LOD), sample-collection method, turnaround time (TAT), result format, price, and power source. Relative importance and part-worth utilities were calculated to assess trade-offs in decision-making. Results One hundred three respondents from 33 countries, primarily in Africa (75%), completed the survey. The relative importance placed on the attributes in the conjoint task varied based on the setting. In community and home-based settings, participants prioritized fingerstick sample collection (25.90%) and faster TATs (28.8%), even at the expense of sensitivity (15.70%). By contrast, respondents from hospitals and health centers valued tests with high sensitivity (42.6%, 40.9%) and faster TATs (31.5%, 22.6%). Across all respondents, price (7.0%), result format (3.30%), and power source (7.25%) were less influential. Conclusions Stakeholders were willing to make trade-offs among desirable attributes, prioritizing rapid turnaround time, strong sensitivity, and fingerstick sampling over affordability, power requirements, and result format in the conjoint task. These preferences vary by level of care and by use case, underscoring the importance of aligning product features with contextual needs. Engaging stakeholders early in the design process is critical to ensure new POC HIV NAAT technologies are both acceptable and scalable in low-resource settings.

### Evidence #6 [paper] Generating ACGME-constraint-aware surgery residency call schedule software with the assistance of agentic coding large language models
Authors: Isaac H. Lies, Meredith G. Rippy, Syamal Dave Bhattacharya, Wesley H. Giles
Venue: Global Surgical Education - Journal of the Association for Surgical Education
Year: 2026
Link: https://doi.org/10.1007/s44186-026-00601-8
Still open/current: yes
Abstract:
Abstract Background Manual creation of a surgery residency call schedule is a labor-intensive process that adds to the administrative burden of a chief resident while often producing suboptimal fairness and work distribution. While commercial scheduling software exists, many programs struggle with inflexibility, high costs, and an inability to accommodate program-specific constraints. Methods We developed a scheduling software platform using AI-assisted development tools (Codex, Claude Code), both commercially available agentic coding environments. The system applies a rule-based, weekend-first assignment hierarchy with randomized tie-breaking under a search budget fixed in advance, then performs iterative weekday assignment, accommodating vacation requests and discrete call-shift swapping. The validation roster modeled a single general surgery residency program: 55 residents (32 categorical and 2 preliminary general surgery residents spanning PGY 1 through PGY 6; 20 off-service rotators from other programs; and 1 fellow) distributed across 10 call pools. Three prespecified call-related ACGME constraints were enforced (at least 4 days off per 28-day period, call no more frequently than every third night averaged over 4 weeks, and no consecutive 24-hour call). The 80-hour weekly maximum and the 24-hour period free of all clinical and educational responsibility were not evaluated, as both depend on activity the call calendar does not capture. We evaluated the system with 100 independent full-year runs (July 1 to June 30), each generated end-to-end across all call pools and months under an independently randomized vacation distribution. Compliance and fairness were evaluated at the level of the individual call-pool month (service-month), the unit at which a monthly schedule is produced; fairness and workload metrics were computed across the program’s in-program surgery residents. Results We generated 12,000 service-month schedules over 100 independent full-year runs. 99.2% (11,906) satisfied all prespecified call-related constraints with no violations detected by the internal validation engine. Forty-five of the 100 full-year runs required no manual intervention in any service-month, and none required it in more than 4 of its 120. Manual review of 120 randomly selected service-months by two authors, without reference to the validator’s output, agreed with it in 120 of 120 cases. Monthly fairness, defined within each call pool and month as the range (maximum minus minimum) of call shifts or weekends assigned per resident, showed a shift range ≤ 1 in 65.4% of service-months (mean 1.84, SD 2.15) and perfect weekend equity (range = 0) in 42.5%, with 86.6% achieving a weekend range ≤ 1 (mean 0.71, SD 0.70). Mean full-year generation time was 108.8 s (SD 59.1). Residents averaged 18.65 weekends (SD 3.13) and 78.23 call days (SD 5.49) per year. Conclusions This automated scheduling system generates resident call schedules that satisfy the prespecified call-related ACGME constraints, optimizes fairness across multiple dimensions, accommodates complex vacation requirements, handles cross-pool coordination, and flags the service-months it cannot resolve within its search budget rather than emitting a non-compliant schedule. These results provide construct validity evidence that optimization algorithms combined with careful constraint specification can eliminate the great majority of the administrative burden of manual scheduling while improving schedule quality and equity.

### Evidence #7 [paper] Guidance for laboratory implementation, governance and continuous assurance of artificial intelligence in histopathology.
Authors: Rakha, Emad A, Wesseling, Jelle, Kovács, Anikó, Ryška, Aleš, Provenzano, Elena, Cserni, Gábor, Varga, Zsuzsanna, Bagó-Horváth, Zsuzsanna
Venue: Virchows Archiv : an international journal of pathology
Year: 2026
Link: https://pubmed.ncbi.nlm.nih.gov/42684470/
Still open/current: yes
Abstract:
Artificial intelligence (AI) is rapidly transforming histopathology, with applications ranging from workflow optimisation and quality assurance to tumour diagnosis, grading, biomarker assessment and estimation of prognosis. While numerous AI algorithms have demonstrated promising analytical and clinical performance, pathology laboratories are increasingly adopting commercially available AI systems with regulatory-approval rather than developing their own algorithms. Existing guidance largely focuses on AI development, validation and regulatory approval, with comparatively little practical direction on the local verification, governance and ongoing assurance required for safe routine clinical implementation. This paper proposes a practical framework for the clinical implementation of AI specifically within pathology laboratories. Rather than addressing AI development, it focuses on the responsibilities of laboratories adopting established AI systems into clinical practice. The framework distinguishes AI applications according to their intended clinical function, recognising that diagnostic applications, biomarker evaluation, workflow optimisation and generative AI applications require different implementation, verification, governance and quality assurance strategies. It further distinguishes algorithm validation, local verification and continuous assurance as complementary stages of implementation and advocates a function-based, risk-proportionate approach integrated within existing laboratory quality management systems. Practical recommendations are provided for workflow integration, interoperability, human oversight, user competency, performance monitoring, incident management, software updates and proportionate re-verification throughout the AI operational lifecycle. By extending implementation beyond regulatory approval, this guidance complements existing AI development and regulatory frameworks rather than replacing them. It provides a practical governance framework for pathology laboratories, professional organisations, accreditation bodies, and healthcare providers to support the safe, standardised, and sustainable integration of AI into routine histopathology while maintaining diagnostic quality, patient safety, and clinical governance.

### Evidence #8 [paper] Evaluation of the Knowledge Levels of Medical Interns at Suleyman Demirel University Faculty of Medicine Regarding the Pre-Analytical Phase of the Laboratory and Rational Test Ordering
Authors: Fevzıye Burcu Şirin, Giray Kolcu
Venue: SDÜ Tıp Fakültesi Dergisi
Year: 2026
Link: https://doi.org/10.17343/sdutfd.1904287
Still open/current: yes
Abstract:
ObjectiveSince the majority of errors in the medical laboratorytesting process occur in the pre-analytical phase andunnecessary test ordering adversely affects patientsafety and healthcare system costs, this study aimedto assess the knowledge and awareness levels ofsixth-year medical students (medical interns) regard-ing the laboratory pre-analytical phase and rationaltest ordering, and to contribute to the developmentof pre-internship training programs based on the findings.Material and MethodThis cross-sectional survey study included 167 med-ical interns from the 2024–2025 (n = 57) and 2025–2026 (n = 110) academic years. Data were collectedusing an online questionnaire. Descriptive statisticsare expressed as frequencies, percentages, andmean ± standard deviation. Pearson’s chi-square testwas used to compare categorical variables betweencohorts. Total pre-analytical knowledge scores andtotal rational test ordering scores were calculated bysumming the correct responses to the relevant items.Statistical significance was set at p < 0.05.ResultsNo statistically significant differences were observedbetween the 2024–2025 and 2025–2026 cohortsacross all knowledge domains (Cramer’s V: 0.01–0.05). Although nearly all participants reported phle-botomy experience, formal education about pre-an-alytical processes and rational laboratory use waslimited, and awareness of national policies was low.Significant deficiencies were identified for technicalpre-analytical topics, including order of draw, diur-nal variation, tube handling, and coagulation sampleanalysis time limits. Knowledge of minimum test rep-etition intervals was generally insufficient, with higheraccuracy for HbA1c and lower accuracy for common-ly requested tests such as AST, ALT, TSH, and CRP.Overall knowledge scores indicated low competency,with no differences between cohorts.ConclusionPractical experience alone does not ensure standard-ized knowledge. Structured, compulsory, and sce-nario-based training focused on pre-analytical qualitymanagement and evidence-based test repeat inter-vals should be integrated into internship education toimprove patient safety and resource utilization.

### Evidence #9 [paper] Guidance for laboratory implementation, governance and continuous assurance of artificial intelligence in histopathology
Authors: Emad A. Rakha, Jelle Wesseling, Anikó Kovács, Aleš Ryška, Elena Provenzano, Gábor Cserni, Zsuzsanna Varga, Zsuzsanna Bagó-Horváth
Venue: Archiv für Pathologische Anatomie und Physiologie und für Klinische Medicin
Year: 2026
Link: https://doi.org/10.1007/s00428-026-04684-y
Still open/current: yes
Abstract:
Abstract Artificial intelligence (AI) is rapidly transforming histopathology, with applications ranging from workflow optimisation and quality assurance to tumour diagnosis, grading, biomarker assessment and estimation of prognosis. While numerous AI algorithms have demonstrated promising analytical and clinical performance, pathology laboratories are increasingly adopting commercially available AI systems with regulatory-approval rather than developing their own algorithms. Existing guidance largely focuses on AI development, validation and regulatory approval, with comparatively little practical direction on the local verification, governance and ongoing assurance required for safe routine clinical implementation. This paper proposes a practical framework for the clinical implementation of AI specifically within pathology laboratories. Rather than addressing AI development, it focuses on the responsibilities of laboratories adopting established AI systems into clinical practice. The framework distinguishes AI applications according to their intended clinical function, recognising that diagnostic applications, biomarker evaluation, workflow optimisation and generative AI applications require different implementation, verification, governance and quality assurance strategies. It further distinguishes algorithm validation, local verification and continuous assurance as complementary stages of implementation and advocates a function-based, risk-proportionate approach integrated within existing laboratory quality management systems. Practical recommendations are provided for workflow integration, interoperability, human oversight, user competency, performance monitoring, incident management, software updates and proportionate re-verification throughout the AI operational lifecycle. By extending implementation beyond regulatory approval, this guidance complements existing AI development and regulatory frameworks rather than replacing them. It provides a practical governance framework for pathology laboratories, professional organisations, accreditation bodies, and healthcare providers to support the safe, standardised, and sustainable integration of AI into routine histopathology while maintaining diagnostic quality, patient safety, and clinical governance.

### Evidence #10 [paper] Developing and evaluating an AI-assisted chatbot for promotion and tenure guidance in an academic medical center
Authors: May May Yeo, Deborah D. Navedo, Patrick J. Casey, Bernard C. Y. Tan
Venue: Frontiers in Artificial Intelligence
Year: 2026
Link: https://doi.org/10.3389/frai.2026.1919009
Still open/current: yes
Abstract:
Abstract The SingHealth Duke–NUS Academic Medical Center manages over 2,800 clinical faculty members and processes over 400 appointments and promotions annually. The current Promotion and Tenure documentation includes over 30 documents, making it difficult and time-consuming for the faculty to locate specific appointment information. We developed “AskADD” in response to requests for clearer academic career development guidance. This study reports initial alpha testing and subsequent beta testing with 35 faculty members using AskADD. AskADD aids the faculty—physician-educators, physician-scientists, physician-innovators, and physician-leaders—in navigating academic career paths while increasing transparency and trust in appointment, promotion, and tenure processes. Our AI-integrated systems, initially tested using low or no-code Microsoft platforms and later developed with a custom GPT, deliver contextualized responses to promotion and tenure queries. The faculty and staff participated in user testing, providing feedback for improvements. Alpha and beta testing conducted with the same group of users indicated that a substantial portion of participants found the tool beneficial; suggestions were given for further refinement. Our experience contributes to the limited literature on AI-driven faculty advancement in academic medical centers and offers a novel paradigm for academic career support.

### Evidence #11 [paper] An agentic framework for intelligent clinical laboratory medicine
Authors: He S. Yang, Wei-Shen Pan, Melissa M. Cushing, P. Fleischut, Fei Wang
Venue: npj Health Systems
Year: 2026
Link: https://www.semanticscholar.org/paper/eae8bad56291499ca9ee0d1b539ee103c2849fa6
Still open/current: yes

### Evidence #12 [paper] Generative AI for Establishing the Chief Complaint
Authors: Vera Sorin, Eyal Klang
Venue: Journal of Clinical Medicine
Year: 2026
Link: https://doi.org/10.3390/jcm15207912
Still open/current: yes
Abstract:
Establishing the chief complaint requires identifying the patient’s main symptoms or concerns. This information is essential for triage and subsequent clinical assessment. However, patients may struggle to describe their symptoms or leave important concerns unspoken. Also, clinicians have limited time to ask further questions during intake. Generative AI could help by asking patients what is troubling them, when their symptoms began, and what other concerns they have. It could prepare a short summary for patients to correct and clinicians to review. Clinical studies of AI-assisted intake have reported shorter physician consultations and more complete recorded histories. These findings do not show whether AI helps clinicians establish the chief complaint more accurately. We propose an evaluation framework centered on the proportion of patients whose main symptoms or concerns are missing or incorrectly described after AI-assisted intake. Studies should compare what patients wanted to discuss with what the AI agent asked about and included in its summary. They should also examine whether concerns requiring urgent assessment were missed. The clinical goal is a clear description of the patient’s main symptoms and concerns that helps clinicians judge urgency and decide what needs attention.

### Evidence #13 [paper] AI agents in clinical medicine: delegation, supervision, and the problem of correlated failure
Authors: Ethan Waisberg, Joseph W. Guarnieri
Venue: Irish Journal of Medical Science (1971 -)
Year: 2026
Link: https://doi.org/10.1007/s11845-026-04584-9
Still open/current: yes
Abstract:
Clinical artificial intelligence has to date generated outputs upon which a clinician then acted. Agentic systems execute the task itself, completing a sequence of steps and returning finished work. Adoption has proceeded rapidly across other sectors while clinical uptake has remained confined largely to pilots, an interval that affords medicine an a opportunity to govern the technology deliberately rather than retrospectively. The governing question is thereby transformed from whether a prediction is accurate to whether a task may be entrusted, a question medicine has addressed throughout its history of training juniors under supervision. We argue that the appropriate frame for agentic systems is consequently delegation rather than prediction, and that the entrustment frameworks developed within postgraduate education furnish a serviceable structure of graded autonomy, task-level scope, and named supervisory responsibility. We then identify the point at which the correspondence ceases to hold. Supervision of human colleagues presupposes that errors are independent and idiosyncratic, such that mistakes arise individually and are detected individually. A single agent deployed across an institution generates one error process reproduced at scale. The consequence is that agentic systems cannot be adequately supervised through case-level review, and require instead the population-level surveillance characteristic of quality improvement.

### Evidence #14 [paper] Home Lab: evaluation pre-registration
Authors: Roshan Aryal
Venue: Open Science Framework
Year: 2026
Link: https://doi.org/10.17605/osf.io/jfp74
Still open/current: yes
Abstract:
This project evaluates a self-hosted AI agent lab running on a single Mac mini (Apple M6, 32 GB, macOS 27.0). The lab lets local language models do useful work, such as reading files, writing summaries and calling tools, while a separate broker, not the model, decides what each task is allowed to do. The questions are practical. Can a small typed routing model beat a fixed rubric without promoting weak evidence (H1)? Does grammar-constrained decoding reduce the tool calls a strict parser has to refuse (H2), and does putting the tool schema in the prompt do the same (H2b, secondary)? Is a tuning change adopted only when it shows a measured gain (H3)? Do the lab's isolation controls still stop prompt-injection attacks when a real model, rather than a scripted worst-case stub, is driving the agent (H4)? The main model is Qwen3-Coder-30B-A3B at 4-bit (MLX and GGUF builds, pinned by commit and file hash). All runs use temperature 0 and a fixed seed, and each run writes a sealed record of the exact code commit, model revision, task file hash and machine settings. Rates are reported with 95 percent bootstrap intervals. Some real-model runs were made before this registration. Amendment 1 lists every one of them and treats them as exploratory. The confirmatory H2 and H2b tests use a new held-out set of 70 tool-call tasks that no model had seen at registration time, and H4 is a replication at the registered commit. Expected outcomes: a clear yes or no for each hypothesis under the stated decision rules, published whichever way it falls, and a set of measured numbers (memory, speed, tool-call reliability, injection resistance) for running agents on a 32 GB machine. Full plan, hypotheses, decision rules and frozen file hashes: docs/PREREGISTRATION.md at github.com/roshanaryal1/home-lab, commit d8726b43be5290afbb2ce6ae2f6722632705d9a8.

### Evidence #15 [paper] Responsibility without a map: defining oversight of automated result release in the medical laboratory.
Authors: Said İncir, Kerim Erhan Palaoğlu, Osman Oğuz
Venue: Clinical Chemistry and Laboratory Medicine (CCLM)
Year: 2026
Link: https://doi.org/10.1515/cclm-2026-1371
Still open/current: yes
Abstract:
Laboratory specialists have been assigned responsibility for algorithmically assisted reporting without an operational definition of what responsible oversight means. Results pass largely through rule-based approval systems, and increasingly through probabilistic models, yet the obligation attached to the specialist's name on the report has never been restated. Taking the position of the specialist who signs rather than the regulator who writes, and starting from requirements the discipline already accepts, we derive four capacities on which approving a result depends: designing the release logic and making it legible, anticipating where it will fail, correcting it when it does, and detecting that it has failed. These are not properties of a technology. Every system sits on a gradient whose position depends less on whether it uses machine learning than on what the laboratory has recorded about it. The oversight problem therefore did not arrive with machine learning but with automation, and most of what is now asked of laboratories in respect of artificial intelligence was already owed in respect of autoverification. Mapped against the four capacities, current frameworks require documentation and change control, address detection only in general terms, and nowhere require a laboratory to state in advance which results may be released without human review. Where laboratories have been asked, they report holding few of the records by which compliance could be shown. We propose a set of such records, identify what a single laboratory can and cannot reasonably do, and set out the questions the profession has not yet answered.

### Evidence #16 [paper] Is it time to bring organoids into your lab?
Venue: AAAS Articles DO Group
Year: 2026
Link: https://doi.org/10.1126/science.zqtzxd4
Still open/current: yes
Abstract:
© NTHIELEN

### Evidence #17 [paper] Beyond the scan: A technical note on the operational implications of pre-imaging requirements in radioligand therapy.
Authors: Yamaguchi, H
Venue: Radiography (London, England : 1995)
Year: 2026
Link: https://pubmed.ncbi.nlm.nih.gov/42976711/
Still open/current: yes
Abstract:
INTRODUCTION: Pre-imaging requirements for radioligand therapy (RLT) can create work beyond image acquisition. This technical note describes a service-planning example involving an on-site prepared gallium-68-labelled prostate-specific membrane antigen (PSMA) imaging radiopharmaceutical and presents a preliminary implementation-impact assessment. METHODS: Contemporaneous operational planning records from a hospital nuclear medicine and theranostics service were used to map activities across seven service domains. Requirements were classified by source and authority, and implementation activities were distinguished from work repeated per preparation or patient. Planning issues were synthesised into a six-question assessment. RESULTS: The pathway involved generator elution, eluate neutralisation, labelling, chromatographic development, radioactivity measurement and radiopharmaceutical preparation and quality control. Scanner acquisition for chromatographic radiochemical purity assessment was a supplier-stated implementation condition in this episode. Familiarity with technetium-99 m generator elution did not establish competency in the additional steps. Pharmacist responsibility for the final quality decision left a separate need to assign trained operators and backup cover. The assessment addresses purpose, authority, equivalence, workload, resources and accountability. CONCLUSION: This planning example illustrates how a pre-imaging requirement can generate a service change extending across equipment, competency and task ownership. The proposed assessment remains preliminary and requires prospective evaluation. IMPLICATIONS FOR PRACTICE: Before implementation, services should distinguish externally specified conditions from locally selected controls, separate initial from recurring work, and document operators, quality decision responsibilities, resources and readiness criteria.

### Evidence #18 [paper] Development and clinical implementation of a local automated kidney allocation platform integrating virtual crossmatch
Authors: Mohammad Awaji, Saber Alzahrani, Rafah Bamrdouf, Dalal AlAbduladheem, Amani Mohammed, Mariam Alzahrani, Shaima Alkebasi, Bashaer Mohammad Alshallali
Venue: Frontiers in Immunology
Year: 2026
Link: https://doi.org/10.3389/fimmu.2026.1922544
Still open/current: yes
Abstract:
Background Highly sensitized kidney transplant candidates possess preformed anti-human leukocyte antigen (HLA) antibodies that substantially reduce their likelihood of receiving a compatible deceased-donor organ. Manual virtual crossmatch (VXM) workflows are sequential and labor-intensive, often limiting histocompatibility laboratories to screening only a subset of eligible candidates during time-sensitive donor evaluations and potentially overlooking compatible recipients. Methods We designed and developed an automated kidney allocation system (KAS) that links the hospital information system with HLA Fusion antibody data to perform candidate scoring and VXM prediction across the entire eligible active waitlist for every deceased donor workup. We conducted a single-center implementation study consisting of a cross-sectional analysis of 219 active kidney transplant candidates and a retrospective comparison of 67 deceased donor match runs processed by the automated KAS and the historical manual VXM workflow. The primary outcome was identification of potentially compatible highly sensitized patient (HSP) events. Analyse. Results Of 219 candidates, 98 (44.7%) were highly sensitized (cPRA ≥80%). Elevated prevalence of HSP was associated with prior transplantation, pregnancy, and transfusion. HSP candidates waited far longer than non-sensitized peers (median 7.10 vs. 3.81 years; p < 0.001). Across 67 retrospective match runs, the automated KAS identified 13 potentially compatible HSP events compared with 4 under the manual workflow, more than threefold higher (rate ratio 3.25; 95% CI 1.06–9.97; p = 0.039). Automated runs completed in 17 ± 0.3 minutes, compared with 152 ± 1.6 minutes for manual workups (p<0.0001). Conclusions A locally developed automated KAS substantially improved compatible donor identification for highly sensitized kidney transplant candidates while reducing VXM turnaround from hours to minutes. By enabling comprehensive evaluation of every eligible candidate during each deceased donor workup, automated allocation represents a practical and potentially scalable strategy that could improve equity and operational efficiency.

### Evidence #19 [paper] Ethical considerations of fluid biomarker use in alzheimer’s disease - a rapid review
Authors: Faye Forsyth, Ana Diaz‐Ponce, Vebjørn Andersson, Ira Haraldsen, Dianne Gove
Venue: Aging & Mental Health
Year: 2026
Link: https://doi.org/10.1080/13607863.2026.2719938
Still open/current: yes
Abstract:
OBJECTIVE: Alzheimer's disease (AD) care has been reshaped by the integration of fluid biomarkers. This review addressed the question "What are the ethical considerations of fluid biomarker use in eligibility assessments for treatment in AD and mild cognitive impairment?" METHODS: A rapid review following established guidelines was performed. Relevant data were identified and organised within the four pillars of biomedical ethics. Results were reported in line with the PRISMA checklist. RESULTS: Searches identified 10,611 records; 34 were included following screening. Narrative synthesis suggests there are a greater number of ethical risks over benefits within the current clinical context. However, interpretation is subjective and empirical data is lacking. CONCLUSIONS: Multiple ethical concerns surround the use of fluid biomarkers in AD treatment decisions, and there is limited empirical evidence to substantiate claims about benefits and harms. Uncertainty in biomarker performance, particularly in underrepresented groups, raises risks to non-maleficence, autonomy, and justice and complicates clinical decision making.

### Evidence #20 [paper] P25 - Medical Imaging, Powder Diffraction and Innovation
Authors: Deutsches Elektronen-Synchrotron
Venue: INST - DESY - Deutsches Elektronen-Synchrotron
Year: 2026
Link: https://doi.org/10.82490/petra3-p25-4eb
Still open/current: yes
Abstract:
This beamline is under commissioning, please contact the beamline staff for more information.

### Evidence #21 [paper] doi:10.13040/ijpsr.0975-8232.17(9).2758-66
Authors: E. Inbaselvi, K. G. Satheesh Kumar and J. Swetha
Venue: International Journal of Pharmaceutical Sciences and Research
Year: 2026
Link: https://doi.org/10.13040/ijpsr.0975-8232.17(9).2758-66
Still open/current: yes
Abstract:
Background: Artificial intelligence (AI) chatbots are increasingly explored as clinical decision-support tools.However, their accuracy and safety in biochemical report interpretation and pharmacotherapy recommendations remain insufficiently evaluated.Objective: To assess the accuracy, safety, consistency, and error patterns of AI chatbots in interpreting biochemical data and providing pharmacological recommendations.Methods: This cross-sectional, case-based analytical study evaluated 100 standardized clinical scenarios across diabetes mellitus, dyslipidemia, renal dysfunction, and liver disorders.Five AI chatbots were assessed using a uniform prompt.Responses were compared with gold-standard references and scored using a composite system (maximum score = 9) evaluating interpretation accuracy, therapeutic accuracy, safety, and justification.Statistical analysis included Kruskal-Wallis and Chi-square tests.Results: Significant differences were observed among chatbots (p = 0.003).Chatbots A and D demonstrated superior performance, with excellent responses in 68% and 60% of cases, respectively, compared to 28% in chatbot E. Interpretation accuracy was consistently higher (91% in chatbot A) than therapeutic accuracy (87% in chatbot A) across all models.Domain-wise performance was highest in diabetes (91%) and lowest in renal dysfunction (78%).Safety analysis revealed that 75-92% of responses were safe, although moderate-to-severe safety concerns occurred in up to 13% of cases in lower-performing models.Consistency was highest in chatbots A and D (85-88% identical responses), while chatbot E showed greater variability (16% different drug recommendations).Drug selection errors (up to 20%) and safety-related errors (up to 18%) were more frequent than interpretation errors.Conclusion: AI chatbots demonstrate strong performance in biochemical interpretation but exhibit limitations in therapeutic decision-making, safety, and consistency.Their role should remain adjunctive, with clinician supervision essential for safe clinical integration.INTRODUCTION: Biochemical investigations constitute a cornerstone of modern clinical practice, playing a critical role in diagnosis, therapeutic monitoring, and pharmacological decision-making.
