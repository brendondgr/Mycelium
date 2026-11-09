# Agentic literature-assistant and research-feed systems (compared to Mycelium)

Scope: agentic and pipeline systems for literature QA, deep research, survey synthesis, paper search and personalised paper feeds, plus lab-facing chat bots, 2023–2026. Notes are current to 2026-11-08. GitHub star counts, licences and last-push dates come from the GitHub REST API on 2026-11-08 (`api.github.com/repos/<repo>`), so each one is a snapshot. "DEMO" marks a system-demonstration-track paper. "unverified" means I could not confirm the fact from a primary source.

## Q1. Catalogue: paper, group, venue/track, arXiv id, repo, licence, stars, maintenance

### Takeaway
Seven of the candidates are verified **demo-track** papers: OpenResearcher and Arxiv Copilot (EMNLP 2024 demo); Ai2 Scholar QA and Scholar Inbox (ACL 2025 demo); TinyScientist, ResearStudio and LLM×MapReduce-V3 (EMNLP 2025 demo). Four more demo papers were found and are directly relevant to Mycelium's design: NLP-KG (ACL 2024 demo), SlackAgents (EMNLP 2025 demo), SciTrue (EACL 2026 demo), and Hindsight agent memory plus Media-to-Insights continuous monitoring (both ACL 2026 demo). PaperQA2, OpenScholar, STORM, PaSa, AutoSurvey and SurveyForge are main-track or journal papers, not demos. "Paper Copilot" was published as a demo under the name **Arxiv Copilot**.

### Cited Findings

**Literature QA and synthesis (pull)**
- **PaperQA2** (FutureHouse): "Language agents achieve superhuman synthesis of scientific knowledge", Skarlinski, Cox, White et al., arXiv 2409.13740 (Sep 2024). It is a preprint; I found no conference track. — [arXiv](https://arxiv.org/abs/2409.13740v2)
  - Repo: github.com/Future-House/paper-qa. Apache-2.0, ~9.6k stars, last push 2026-10-26, actively maintained. Uses LiteLLM so it runs on any provider. — [GitHub API / README](https://github.com/Future-House/paper-qa)
- **OpenScholar** (Ai2 + UW; Asai, Hajishirzi et al.): arXiv 2411.14199, published in *Nature* on 2026-02-04 (DOI 10.1038/s41586-025-10072-4). Journal paper, not a demo. — [Ai2 blog](https://allenai.org/blog/openscholar-nature); [infodocket](https://www.infodocket.com/2026/02/04/research-paper-synthesizing-scientific-literature-with-retrieval-augmented-language-models/)
  - Repo: github.com/AkariAsai/OpenScholar. Apache-2.0, ~1.7k stars, last push 2025-08-13, so research code that is now quiet. Separate repos hold the demo (allenai/open-scholar-demo) and ScholarQABench. — [README](https://github.com/AkariAsai/OpenScholar)
- **Ai2 Scholar QA** — DEMO: "Ai2 Scholar QA: Organized Literature Synthesis with Attribution", Singh, Chang, Haddad, … Weld, Downey, Feldman (Ai2). ACL 2025 System Demonstrations, pp. 513–523, arXiv 2504.10861. — [ACL Anthology](https://aclanthology.org/2025.acl-demo.49)
  - Repo: github.com/allenai/ai2-scholarqa-lib. Apache-2.0, ~290 stars, last push 2026-10-26, active. — [GitHub](https://github.com/allenai/ai2-scholarqa-lib)
- **Asta** (Ai2 agent ecosystem, launched 2025-08-26): an assistant (Paper Finder = "Find Papers", Scholar QA = "Summarize literature", DataVoyager for data analysis), AstaBench, and developer resources including an MCP "Scientific Corpus Tool" over the Semantic Scholar API (200M+ papers). — [Ai2 blog](https://allenai.org/blog/asta); [aiwire](https://dev.aiwire.net/2025/08/27/ai2-launches-asta-an-open-agentic-ecosystem-for-science/)
  - **AstaBench**: arXiv 2510.21652, ICLR 2026 (oral listing). Main track, not a demo. Repo allenai/asta-bench: Apache-2.0, ~140 stars, last push 2026-11-03. — [ICLR proceedings](https://proceedings.iclr.cc/paper_files/paper/2026/hash/b2ce9568dbb559aefc8c98ca5b5314ce-Abstract-Conference.html); [arXiv](https://arxiv.org/pdf/2510.21652)
  - **Asta Paper Finder**: repo allenai/asta-paper-finder. Apache-2.0, ~250 stars, last push 2026-10-29. The README calls it a "frozen-in-time" snapshot that is "not actively maintained". — [README](https://github.com/allenai/asta-paper-finder)
- **OpenResearcher** — DEMO: "OpenResearcher: Unleashing AI for Accelerated Scientific Research", Zheng … Pengfei Liu (GAIR / SJTU). EMNLP 2024 System Demonstrations, pp. 209–218, arXiv 2408.06941. — [ACL Anthology](https://aclanthology.org/2024.emnlp-demo.22)
  - Repo: GAIR-NLP/OpenResearcher. Apache-2.0, ~510 stars, last push 2024-10-10 (unmaintained). — [GitHub](https://github.com/GAIR-NLP/OpenResearcher)
- **NLP-KG** — DEMO: "NLP-KG: A System for Exploratory Search of Scientific Literature in NLP", Schopf & Matthes (TUM). ACL 2024 demos. — [ACL Anthology](https://aclanthology.org/2024.acl-demos.13/)
  - Repo: NLP-Knowledge-Graph/NLP-KG-WebApp. MIT, 15 stars, last push 2025-10-16. — [GitHub](https://github.com/NLP-Knowledge-Graph/NLP-KG-WebApp)
- **SciTrue** — DEMO: "SciTrue: Evidence-Grounded Claim Verification in Science", Tan, Li, Gahegan. EACL 2026 demos. No repo was found. — [ACL Anthology](https://aclanthology.org/2026.eacl-demo.27/)
- **CiteLab** — DEMO: modular citation-generation framework (Citeflow + Citefix), Shen et al. (CASIA). ACL 2025 demos. Repo SjJ1017/CiteLab: MIT, 18 stars. — [ACL Anthology](https://aclanthology.org/2025.acl-demo.47)

**Paper search agents**
- **PaSa** (ByteDance Seed + PKU; He, Huang, … Hang Li, Weinan E): "PaSa: An LLM Agent for Comprehensive Academic Paper Search". ACL 2025 **main (long)**, pp. 11663–11679. — [ACL Anthology](https://aclanthology.org/2025.acl-long.572)
  - Repo: bytedance/pasa. Apache-2.0, ~1.7k stars, last push 2025-05-27 (quiet). The arXiv id is unverified in my sources. — [GitHub](https://github.com/bytedance/pasa)

**Deep-research / report generation (pull)**
- **STORM** (Stanford OVAL; Shao, Jiang, Kanell, Xu, Khattab, Lam): NAACL 2024 (main), arXiv 2402.14207. **Co-STORM** ("Into the Unknown Unknowns", Jiang, Shao, Ma, Semnani, Lam): EMNLP 2024 (main), arXiv 2408.15232. — [search summary of arXiv/GitHub](https://arxiv.org/abs/2408.15232)
  - Repo: stanford-oval/storm (`knowledge-storm` package). MIT, ~31.8k stars, last push 2025-09-30. — [GitHub](https://github.com/stanford-oval/storm)
- **GPT-Researcher** (Assaf Elovic, community project): no peer-reviewed paper found. Repo assafelovic/gpt-researcher: Apache-2.0, ~30.5k stars, last push 2026-10-10, active. — [GitHub](https://github.com/assafelovic/gpt-researcher)
- **LangChain open_deep_research**: MIT, ~12.7k stars. The GitHub API reports the repo as **archived** (last push 2026-08-10). — [GitHub](https://github.com/langchain-ai/open_deep_research)
- **HuggingFace smolagents** (it ships an open deep-research example): Apache-2.0, ~30.3k stars, last push 2026-11-03. — [GitHub](https://github.com/huggingface/smolagents)
- Other open deep-research clones (no papers):
  - dzhng/deep-research: MIT, ~19.9k stars.
  - jina-ai/node-DeepResearch: Apache-2.0, ~5.2k stars.
  - nickscamara/open-deep-research: ~6.3k stars, no SPDX licence.
  - — [GitHub API snapshot](https://github.com/dzhng/deep-research)
- **ResearStudio** — DEMO: "A Human-intervenable Framework for Building Controllable Deep Research Agents", Yang & Weng. EMNLP 2025 demos. Repo not verified: the abstract says code would be released "upon acceptance". — [ACL Anthology](https://aclanthology.org/2025.emnlp-demos.69/)
- **TinyScientist** — DEMO: Yu, … Kyle Richardson, Jiaxuan You (UIUC). EMNLP 2025 demos. Repo ulab-uiuc/tiny-scientist: MIT, 139 stars, last push 2026-03-04. — [ACL Anthology](https://aclanthology.org/2025.emnlp-demos.41/); [GitHub](https://github.com/ulab-uiuc/tiny-scientist)
- **IRIS** — DEMO: Interactive Research Ideation System (MCTS, human-in-the-loop), Garikaparthi, Patwardhan, Vig, Cohan. ACL 2025 demos. Repo Anikethh/IRIS-Interactive-Research-Ideation-System: 38 stars, no licence. — [ACL Anthology](https://aclanthology.org/2025.acl-demo.57)
- **GraphMind** — DEMO: novelty assessment, da Silva, Yan, Gui, He. EMNLP 2025 demos. Repo unverified. — [ACL Anthology bib](https://aclanthology.org/2025.emnlp-demos.21/)

**Survey generation**
- **AutoSurvey** (Wang et al.): NeurIPS 2024 main, arXiv 2406.10252. Repo AutoSurveys/AutoSurvey: ~480 stars, no licence, last push 2025-02. — [NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2024/hash/d07a9fc7da2e2ec0574c38d5f504d105-Abstract.html)
- **SurveyX** (IAAR-Shanghai; Liang et al.): arXiv 2502.14776, venue unverified. Repo IAAR-Shanghai/SurveyX: ~1k stars, no licence. — [arXiv](https://arxiv.org/pdf/2502.14776)
- **SurveyForge** (Yan et al.): arXiv 2503.04629. The repo describes it as "ACL-2025 main conference"; I did not check that against the Anthology. Repo InternScience/SurveyForge: 334 stars, no licence. — [arXiv](https://arxiv.org/abs/2503.04629v1); [GitHub](https://github.com/InternScience/SurveyForge)
- **LLM×MapReduce-V3** — DEMO: MCP-driven, hierarchically modular survey-generation agent (Tsinghua NLP, Maosong Sun group). EMNLP 2025 demos. Repo thunlp/LLMxMapReduce: Apache-2.0, ~880 stars, last push 2026-03. — [ACL Anthology](https://aclanthology.org/2025.emnlp-demos.51/)

**Personalised feeds / digests (push)**
- **Scholar Inbox** — DEMO: Flicke … Andreas Geiger (Tübingen). ACL 2025 demos (already known to the owner). Public code unverified; a third-party CLI exists (mrshu/scholarinboxcli). — [ACL Anthology](https://aclanthology.org/2025.acl-demo.30/)
- **Arxiv Copilot** (preprint title "Paper Copilot") — DEMO: "A Self-Evolving and Efficient LLM System for Personalized Academic Assistance", Lin, Feng, Han, Liu, Jiaxuan You (UIUC). EMNLP 2024 demos, pp. 122–130, arXiv 2409.04593. Deployed as the Hugging Face Space ulab-ai/ArxivCopilot; GitHub repo unverified. — [ACL Anthology](https://aclanthology.org/2024.emnlp-demo.13)
- **PaperFlow**: "Profiling, Recommending, and Adapting Across Daily Paper Streams", Wang … Cheng Tan. arXiv 2606.07454 (June 2026). No venue, no repo listed. — [arXiv](https://arxiv.org/abs/2606.07454)
- **ArxivDigest** (AutoLLM): no paper. MIT, ~470 stars, last push 2024-05 (unmaintained). — [GitHub](https://github.com/AutoLLM/ArxivDigest)
- **PaperBee** (theislab, Helmholtz Munich): LLM-filtered daily paper lists posted to Slack, Telegram and other channels. MIT, 137 stars, last push 2026-01-13. Paper unverified. — [GitHub](https://github.com/theislab/paperbee)
- **paper-summarizer**: Slack bot that summarises arXiv links. AGPL-3.0, 71 stars, last push 2023 (dead). — [GitHub](https://github.com/discus0434/paper-summarizer)

**Human-centred literature tools (HCI)**
- **DiscipLink** (HKUST; Zheng … Xiaojuan Ma): UIST 2024 full paper, arXiv 2408.00447, DOI 10.1145/3654777.3676366. No public repo found (a 0-star cynnowe/disciplink is unrelated or unverified). — [arXiv](https://arxiv.org/abs/2408.00447v1)

**Lab and workplace chat agents, agent memory**
- **CHOIR** (Virginia Tech): "A Chatbot-mediated Organizational Memory Leveraging Communication in University Research Labs". CHI 2026 full paper, Best Paper Honorable Mention, arXiv 2509.20512, DOI 10.1145/3772318.3791314. Repo unverified. — [project page](https://choir.cs.vt.edu/); [arXiv](https://arxiv.org/abs/2509.20512)
- **SlackAgents** — DEMO (Salesforce AI Research): multi-agent library for agents in Slack workspaces. EMNLP 2025 demos. Repo SalesforceAIResearch/SlackAgents: Apache-2.0, 10 stars, last push 2026-06. — [ACL Anthology](https://aclanthology.org/2025.emnlp-demos.76/)
- **Hindsight** — DEMO: "Structured Agent Memory that Retains, Recalls, and Reflects". ACL 2026 demos. Repo vectorize-io/hindsight: MIT, last push 2026-11-07. The API reported ~59.8k stars, which is surprisingly high; re-check before citing. — [ACL Anthology](https://aclanthology.org/2026.acl-demo.27/)
- **Media-to-Insights** — DEMO: multi-agent continuous media monitoring and reporting. ACL 2026 demos. Repo unverified. — [ACL Anthology](https://aclanthology.org/2026.acl-demo.44/)

**Benchmarks and evaluation platforms**
- **SciArena** (Yale, NYU, Ai2): NeurIPS 2025 Datasets & Benchmarks track, arXiv 2507.01001. — [NeurIPS](https://papers.neurips.cc/paper_files/paper/2025/hash/9811fe727c94e7ff79f701c94ed1d938-Abstract-Datasets_and_Benchmarks_Track.html)
- **DeepScholar-Bench** (Stanford/Berkeley; Patel, Arabzadeh et al.): arXiv 2508.20033, listed at NeurIPS 2025 (track unverified). The repo now resolves to guestrin-lab/deepscholar: MIT, 249 stars. — [arXiv](https://arxiv.org/html/2508.20033v2); [project](https://sky.cs.berkeley.edu/project/deepscholar-bench/)
- **DeepResearch Bench**: repo Ayanami0730/deep_research_bench. Apache-2.0, ~850 stars, last push 2026-09. 100 PhD-level tasks (50 English, 50 Chinese), scored with the RACE LLM-judge metric. — [open_deep_research README](https://github.com/langchain-ai/open_deep_research)
- **Agent-research frameworks** (not literature assistants, listed for context): SakanaAI/AI-Scientist (~15k stars) and SamuelSchmidgall/AgentLaboratory (~5.9k stars, MIT). — [GitHub API snapshot](https://github.com/SakanaAI/AI-Scientist)

**Demo-volume scan:** a scan of the ACL Anthology demo volumes for ACL/NAACL/EMNLP 2024–2025, EACL 2026 and ACL 2026 found only the above as literature or research-assistant demos. There is no 2026 NAACL demo volume, which fits NAACL 2027 being the next one. — [EMNLP 2025 demos volume](https://aclanthology.org/volumes/2025.emnlp-demos/); [ACL 2026 demo volume](https://aclanthology.org/volumes/2026.acl-demo/)

### Inferences
- Precedent for a NAACL 2027 Mycelium demo is strong. Five literature or research-assistant systems were accepted in demo tracks in each of 2024 and 2025. ACL 2026 alone had about a dozen science-tooling demos, so reviewers know the genre. The novelty bar will be in **lab scope + push + consent ledger + verification**, not in "RAG over papers".
- Arxiv Copilot (EMNLP 2024 demo) and Scholar Inbox (ACL 2025 demo) are the two closest prior **demo** papers on personalised feeds, and Mycelium must position against both. CHOIR (CHI 2026) is the closest prior work on **lab chat**, though it is HCI rather than NLP.

### Gaps
- Not verified: the PaSa arXiv id, and public code for Scholar Inbox, Arxiv Copilot, ResearStudio, GraphMind, SciTrue, CHOIR and Media-to-Insights.
- The SurveyX venue and the ACL 2025 claim for SurveyForge come only from arXiv and repo text.
- Semantic Scholar's research feeds: I found no dedicated paper.
- Elicit, Undermind and Consensus are closed commercial products. I gathered no verified technical facts about them; use them only as named comparators.

## Q2. Architecture: truly agentic, fixed pipeline, or multi-agent? Tools, grounding, verification

### Takeaway
Most systems marketed as "agents" in this space are **pipelines with LLM decision points**. Only PaperQA2 (agent picks tools in any order), PaSa (RL-trained crawl/expand policy), GPT-Researcher, open_deep_research and Co-STORM (multi-agent loops) have a model choosing actions. Ai2's production systems, Scholar QA and Paper Finder, are explicitly hand-coded pipelines with LLM judgments, which is close to Mycelium's current design.

### Cited Findings
- **PaperQA2** has three tools: Paper Search (LLM-generated keyword query, then chunk and embed), Gather Evidence (embed query, top-k chunks, LLM-scored summary per chunk, LLM re-score), and Generate Answer. The README says "The tools can be invoked in any order by a language agent". A hard-coded "fake" agent path also exists. Metadata includes citation counts and a retraction check. — [README](https://github.com/Future-House/paper-qa)
- **Ai2 Scholar QA** is a RAG pipeline: LLM query preprocessing and metadata filtering, then Semantic Scholar snippet search plus keyword search (256 candidates), then the mxbai-rerank-large reranker (top 50), aggregated per paper. A three-step generator follows: (i) exact **quote extraction**, (ii) planning an outline and clustering quotes to sections, (iii) section-by-section generation. List-type sections also get comparison tables via ArxivDIGESTables. Corpus: 11M+ full texts, 100M+ abstracts. — [README](https://github.com/allenai/ai2-scholarqa-lib)
- **Asta Paper Finder**: "a pipeline of manual-coded components which involve LLM decisions in several key-points". A query is parsed into a structured object, and an execution planner routes it to intent-specific workflows. These return LLM relevance-judged papers, ranked with content relevance plus criteria such as "influential" or "early works". The online version adds multi-turn use and progress updates. — [README](https://github.com/allenai/asta-paper-finder)
- **OpenScholar**: a trained 8B LM plus a datastore of 45M open-access papers, a trained reranker (OpenScholar_Reranker), supplementary Semantic Scholar and web search APIs, and a **self-feedback loop** that iteratively retrieves and refines during generation, with post-hoc citation attribution. — [README](https://github.com/AkariAsai/OpenScholar); [Ai2 blog](https://allenai.org/blog/openscholar-nature)
- **PaSa**: two LLM agents. A Crawler issues search calls and expands citations; a Selector scores each paper's relevance from title and abstract. Both are optimised with RL on the synthetic AutoScholarQuery set (35k queries). — [ACL Anthology / GitHub summary](https://aclanthology.org/2025.acl-long.572)
- **OpenResearcher**: RAG with "tools" for query understanding, literature search, filtering, answer generation and **self-refinement**. — [ACL Anthology](https://aclanthology.org/2024.emnlp-demo.22)
- **STORM / Co-STORM**: STORM simulates multi-perspective question asking against search to write Wikipedia-like cited articles, with no user interaction. Co-STORM is multi-agent discourse that the user can observe and steer, and it keeps a dynamic **mind map**. — [arXiv 2408.15232](https://arxiv.org/abs/2408.15232)
- **GPT-Researcher**: planner agent → execution/crawler agents per sub-question → publisher, run in parallel. Has an MCP client (`RETRIEVER=tavily,mcp`) and ships as a Claude Skill. — [README](https://github.com/assafelovic/gpt-researcher)
- **open_deep_research**: a LangGraph agent with separate summarisation, research and compression models; any search API or MCP server; evaluated on DeepResearch Bench. — [README](https://github.com/langchain-ai/open_deep_research)
- **ResearStudio**: hierarchical Planner–Executor that writes every step to a live "plan-as-document". The user can pause, edit the plan or code, and resume. — [ACL Anthology](https://aclanthology.org/2025.emnlp-demos.69/)
- **LLM×MapReduce-V3**: an MCP-driven, hierarchically modular multi-agent system for interactive survey generation. — [ACL Anthology](https://aclanthology.org/2025.emnlp-demos.51/)
- **Arxiv Copilot**: builds user profiles from the user's papers, refreshes its paper DB daily from new arXiv submissions, and uses "thought retrieval" that self-evolves from past user queries. Efficiency optimisations reportedly save ~69.92% of time. — [arXiv 2409.04593](https://arxiv.org/html/2409.04593v1)
- **Scholar Inbox**: a recommender trained on each user's ratings. A "map of science" handles cold start, and active learning prompts users to rate papers. Also offers visual summaries and semantic search. — [ACL Anthology](https://aclanthology.org/2025.acl-demo.30/)
- **PaperFlow**: a three-stage loop. Profiling keeps an *inspectable* scholarly profile; Recommending ranks each day's stream under a fixed display limit; Adapting updates the user state from heterogeneous feedback and models interest drift across days. — [arXiv](https://arxiv.org/abs/2606.07454)
- **CHOIR**: a Slack bot. Members @-mention it and get answers grounded in the lab's documents, with citations to chunks. It proposes documentation updates that directors approve, and approved edits are auto-committed to a GitHub repo. — [project page](https://choir.cs.vt.edu/)
- **Hindsight**: memory split into world, experience, observation and opinion networks, with retain/recall/reflect operations. Recall is parallel vector + keyword + graph + temporal retrieval, backed by **PostgreSQL + pgvector**. It provides fact-belief separation and opinions with confidence that evolve. — [ACL Anthology](https://aclanthology.org/2026.acl-demo.27/)
- **Media-to-Insights**: a hybrid keyword-then-semantic Matching Agent (~20% fewer agent calls), batched feature extraction (7→2 calls/article), a report agent with deterministic dedup and density clustering, plus "four autonomous life-cycle agents" that manage the evolution of watchers. — [ACL Anthology](https://aclanthology.org/2026.acl-demo.44/)
- **SciTrue** links each claim component to explicit scientific sources for "source-level accountability". **FactSearch** (ACL 2026 demo) decomposes outputs into atomic claims, issues targeted queries to a **self-hosted meta-search engine**, and verifies modularly. — [SciTrue](https://aclanthology.org/2026.eacl-demo.27/); [FactSearch](https://aclanthology.org/2026.acl-demo.36/)
- **DiscipLink**: an LLM proposes exploratory questions from relevant disciplines and expands queries with disciplinary terms. Uses Semantic Scholar API search, text-embedding-3-small, and theme extraction. — [arXiv](https://arxiv.org/abs/2408.00447v1)

### Inferences
- Mycelium's "fixed pipelines + schema-constrained outputs + deterministic verifiers" matches what Ai2 actually ships. Paper Finder's "planner routes a structured query to intent-specific workflows" is the smallest agentic step Mycelium could take: an LLM router over its existing deterministic pipelines. A free-form tool loop is not needed for that.
- Media-to-Insights is architecturally the nearest analogue to Mycelium's nightly ingest→match→report. It is the cleanest published example of "agentic monitoring with a cheap deterministic pre-filter and deterministic dedup".

### Gaps
- I did not read the full papers for OpenResearcher, Arxiv Copilot or Scholar Inbox. The model details (e.g. Scholar Inbox's exact recommender model) are unverified here.

## Q3. Reported evaluations

### Takeaway
Pull-QA systems evaluate on benchmarks of expert-written questions (LitQA2, ScholarQABench, PaperFindingBench/AstaBench, DeepResearch Bench, DeepScholar-Bench) plus expert preference. Feed systems evaluate on user ratings (Scholar Inbox: 800k ratings) or simulated longitudinal users (PaperFlow). Lab-chat systems use field deployments (CHOIR). None of them evaluates lab-level feeds or citation verification of push reports.

### Cited Findings
- **PaperQA2**: on LitQA2 (248 multiple-choice questions), 85.2% precision and 66.0% accuracy (secondary summary). WikiCrow articles were rated more accurate than Wikipedia's. It found ~2.34 contradictions per paper, 70% validated by experts. — [HF papers](https://huggingface.co/papers/2409.13740); [Moonlight review](https://www.themoonlight.io/review/language-agents-achieve-superhuman-synthesis-of-scientific-knowledge)
- **OpenScholar**: on ScholarQABench (2,967 expert queries, 208 long-form answers; CS, physics, neuroscience, biomed), the 8B model beats GPT-4o by 6.1% and PaperQA2 by 5.5% in correctness. GPT-4o fabricated 78–90% of citations. Experts preferred OpenScholar-8B and OpenScholar-GPT-4o over expert answers 51% and 70% of the time. — [Ai2 blog / Nature coverage](https://allenai.org/blog/openscholar-nature)
- **Ai2 Scholar QA**: "outperforms competing systems" on a recent scientific QA benchmark (ScholarQA-CS per the paper; exact numbers not captured). — [ACL Anthology](https://aclanthology.org/2025.acl-demo.49)
- **AstaBench**: 2,400+ problems in 11 benchmark sets across literature understanding, code, data analysis and end-to-end discovery. Scores are cost-aware; 57 agents in 22 classes were tested. Asta Paper Finder scores over double ReAct on PaperFindingBench (self-reported). Conclusion: agents are "far from solving" research assistance, and literature understanding is the most mature area. — [Ai2 AstaBench blog](https://allenai.org/blog/astabench); [arXiv](https://arxiv.org/pdf/2510.21652)
- **PaSa-7B** beats Google+GPT-4o by 37.78% recall@20 and 39.90% recall@50 on RealScholarQuery. — [ACL Anthology/arXiv summary](https://aclanthology.org/2025.acl-long.572)
- **Co-STORM**: 70% of participants prefer it to a search engine and 78% to a RAG chatbot. — [arXiv](https://arxiv.org/abs/2408.15232)
- **open_deep_research**: RACE 0.4344 on DeepResearch Bench (#6 on 2025-08-02). The run cost $87.83 and 207M tokens. — [README](https://github.com/langchain-ai/open_deep_research)
- **ResearStudio**: state of the art on GAIA in autonomous mode, beating OpenAI DeepResearch and Manus (self-reported). — [ACL Anthology](https://aclanthology.org/2025.emnlp-demos.69/)
- **SurveyX**: +0.259 in content quality and +1.76 in citation quality over prior systems. — [arXiv](https://arxiv.org/pdf/2502.14776)
- **Scholar Inbox**: evaluated on a new public dataset of 800k user ratings plus a user study. — [ACL Anthology](https://aclanthology.org/2025.acl-demo.30/)
- **PaperFlow**: benchmark of 24 simulated users, 50 daily streams, 1,200 user-day episodes and 20,727 papers. Best results versus 5 baselines on oracle ranking, behavioural alignment and blind human evaluation. — [arXiv](https://arxiv.org/abs/2606.07454)
- **CHOIR**: 15 formative interviews, then a one-month deployment in 4 labs with 21 participants. 107 questions were asked (45 answered successfully per a secondary summary) and directors made 38 document updates. Key tension: students preferred private Q&A, which hid documentation gaps from directors. — [project page](https://choir.cs.vt.edu/); [Moonlight review](https://www.themoonlight.io/review/choir-a-chatbot-mediated-organizational-memory-leveraging-communication-in-university-research-labs)
- **SciTrue**: human evaluation of 300 attributions; it beats GPT-4o-search-preview and Perplexity Sonar Pro on traceability, attribution accuracy and context alignment. — [ACL Anthology](https://aclanthology.org/2026.eacl-demo.27/)
- **Hindsight**: 83.6% on LongMemEval and 83.2% on LoCoMo with a 20B open model; 91.4% LongMemEval with Gemini-3 Pro. — [ACL Anthology](https://aclanthology.org/2026.acl-demo.27/)
- **SciArena**: Elo from 20k+ researcher votes over 47 models. SciArena-Eval meta-evaluates LLM judges against those votes. — [NeurIPS](https://papers.neurips.cc/paper_files/paper/2025/hash/9811fe727c94e7ff79f701c94ed1d938-Abstract-Datasets_and_Benchmarks_Track.html)
- **DeepScholar-Bench**: a live, monthly-refreshed related-work-writing task scored on synthesis, retrieval and verifiability. v1 reported no system above 19% on all metrics; v2 reported a 31% geometric mean. — [arXiv v2](https://arxiv.org/html/2508.20033v2)
- **DiscipLink**: within-subject experiment plus an exploratory study with 7 interdisciplinary researchers. Users reported better efficiency and lower workload, but also information overload. — [arXiv](https://arxiv.org/abs/2408.00447v1)

### Inferences
- Benchmarks Mycelium could run cheaply:
  - **Paper search and retrieval:** PaperFindingBench and LitQA2 through AstaBench, which is open and cost-aware; RealScholarQuery from PaSa.
  - **Weekly-report synthesis:** DeepScholar-Bench, whose verifiability axis maps onto Mycelium's citation verifier.
  - **Daily feed ranking:** the PaperFlow-style longitudinal user-day protocol is the only published protocol that matches a daily feed. Scholar Inbox's 800k-rating dataset is a possible offline ranking test set.
- Per the repo's research rules, any such run must go under `docs/research/experiments/`.

### Gaps
- Exact Ai2 Scholar QA benchmark numbers and Arxiv Copilot user-study numbers were not captured.
- PaperQA2's LitQA2 figures come from a secondary review, not the PDF.

## Q4. How each differs from Mycelium

### Takeaway
Almost every system above is **individual, pull-based and session-scoped**: you ask, it answers, it forgets. Mycelium is **lab/department-scoped, push-based and persistent**: nightly ingest, briefings, a Discord/Slack bot, a consent-gated chat ledger, a lab knowledge graph, and grants, fellowships and conference calls. Mycelium does not yet have agentic tool choice, interactive deep QA or long-form synthesis.

### Cited Findings
- **Pull QA** (PaperQA2, OpenScholar, Scholar QA, OpenResearcher, STORM, GPT-Researcher, open_deep_research): each takes a single user query and returns a cited answer or report. None advertises scheduled delivery, team scope, or grant/fellowship feeds. — [PaperQA2 README](https://github.com/Future-House/paper-qa); [Scholar QA README](https://github.com/allenai/ai2-scholarqa-lib); [GPT-Researcher README](https://github.com/assafelovic/gpt-researcher)
- **Push feeds** (Scholar Inbox, Arxiv Copilot, PaperFlow, ArxivDigest, PaperBee):
  - All are individual-profile recommenders. Scholar Inbox trains on individual ratings ([ACL Anthology](https://aclanthology.org/2025.acl-demo.30/)); Arxiv Copilot builds per-user profiles with daily arXiv refresh ([arXiv](https://arxiv.org/html/2409.04593v1)).
  - PaperBee does post to Slack/Telegram channels with a lab-focused LLM filter prompt, the nearest to "lab feed", but has no paper, verifier or knowledge graph. — [GitHub](https://github.com/theislab/paperbee); [search summary](https://awesome.ecosyste.ms/projects/github.com%2Ftheislab%2Fpaperbee)
- **Lab chat**: CHOIR is the only published lab-scoped Slack assistant found. It is invoked on demand and grounded in lab documentation, not literature. Its privacy finding (private Q&A vs director visibility) bears directly on Mycelium's consent ledger. — [CHOIR](https://choir.cs.vt.edu/)
- **Self-hosting and openness**:
  - Ai2 Scholar QA needs the Semantic Scholar API plus commercial LLMs (Claude Sonnet 3.7 default) and a Modal-hosted reranker. — [README](https://github.com/allenai/ai2-scholarqa-lib)
  - OpenScholar releases a full datastore and open 8B models. — [README](https://github.com/AkariAsai/OpenScholar)
  - PaperQA2 runs on any LiteLLM provider over local files. — [README](https://github.com/Future-House/paper-qa)
  - FactSearch makes the self-hosted search backend a first-class design point. — [ACL Anthology](https://aclanthology.org/2026.acl-demo.36/)

### Inferences
- Mycelium's demo story is the intersection that is empty in the literature: lab-scope × push × consent-gated chat evidence × verifiable weekly report × self-hostable. No single published system covers more than two of these.
- Gap to close: Mycelium has no interactive, query-driven deep QA. Reviewers will compare any "agentic" claim against PaperQA2, Scholar QA and open_deep_research.

### Gaps
- No published system was found that combines grants, fellowships or conference calls with literature feeds (unverified absence; not exhaustively searched).

## Q5. What Mycelium could adopt, and how hard

### Takeaway
The best moves are, cheapest first:
1. **Wrap PaperQA2 or the Scholar QA library as tools** behind Mylo slash commands, for on-demand cited QA over the lab's papers.
2. **Borrow Paper Finder's "LLM router over hand-coded workflows" pattern**, the smallest honest step to "agentic".
3. **Borrow Scholar QA's quote-extraction-before-writing** to strengthen the weekly-report verifier.
4. **Benchmark on AstaBench (PaperFindingBench/LitQA2) and DeepScholar-Bench.**
5. **Study Hindsight's fact/belief/observation memory**, which already runs on Postgres + pgvector, against the evidence ledger.

### Cited Findings and adoption notes
- **PaperQA2 as a dependency (low–medium effort).**
  - What it is: a pip package (`paper-qa>=5`, Python 3.11+, Apache-2.0) with agentic search/gather/answer tools over a local paper directory, any LiteLLM model, and retraction-checked metadata. — [README](https://github.com/Future-House/paper-qa)
  - Use: a `/mylo ask` command over a lab's member-paper corpus, which Mycelium already ingests for KG facets.
  - Risk: it uses its own index rather than Mycelium's pgvector store, so there is index duplication.
- **ai2-scholarqa-lib components (medium effort).** Apache-2.0, with modular `PaperFinder` and `MultiStepQAPipeline` classes. — [README](https://github.com/allenai/ai2-scholarqa-lib)
  - Adopt the **quote extraction → outline + quote clustering → per-section generation** pattern for the Monday weekly. Every sentence is then built from extracted verbatim quotes, which suits Mycelium's deterministic citation verifier.
  - The mxbai-rerank-large reranker is a drop-in rerank candidate. Mycelium's own experiments found rerankers did not help on short queries, so measure before adopting.
- **Paper Finder pattern (medium effort).** An LLM parses the query into a structured object, and an execution planner routes it to intent-specific deterministic workflows. — [README](https://github.com/allenai/asta-paper-finder)
  - This maps onto Mycelium's existing schema-constrained pipelines: a router picks among {feed search, KG lookup, project-state query, grant search}. It keeps verifiers in place and adds the minimum agency.
- **Asta Scientific Corpus Tool via MCP (low effort).** An MCP extension of the Semantic Scholar API over 200M+ papers. — [Ai2 Asta](https://allenai.org/blog/asta)
  - If Mylo becomes a tool-calling agent, this is a ready external tool alongside Mycelium's own MCP tools.
- **GPT-Researcher or open_deep_research as the "deep dive" tool (medium effort).** Both have MCP clients and are permissively licensed (Apache-2.0 / MIT). — [GPT-R README](https://github.com/assafelovic/gpt-researcher); [ODR README](https://github.com/langchain-ai/open_deep_research)
  - open_deep_research is now archived, so prefer GPT-Researcher or smolagents if a maintained dependency matters.
- **Hindsight memory (medium–high effort; pattern more than dependency).** — [ACL Anthology](https://aclanthology.org/2026.acl-demo.27/)
  - Its world/experience/observation/opinion networks with retain/recall/reflect, temporal entity graph and confidence-scored opinions parallel Mycelium's Observations (kinds, supersession, retractions).
  - It is MIT-licensed and on Postgres + pgvector. A natural comparator and baseline for the "agent memory" step, and a likely question from NAACL reviewers.
- **Media-to-Insights pattern (low effort, pattern only).** A deterministic keyword pre-filter before semantic or agent matching (~20% fewer agent calls), batched extraction (7→2 calls), deterministic dedup + clustering in the report, and life-cycle agents that evolve "watchers". — [ACL Anthology](https://aclanthology.org/2026.acl-demo.44/)
  - The life-cycle agents are a template for letting an agent propose edits to interest clusters or watch topics, which humans approve.
- **CHOIR's approve-then-commit loop (low effort, pattern).** Bot-proposed documentation updates are approved by the director and auto-committed. — [CHOIR](https://choir.cs.vt.edu/)
  - Applies to ledger Observations and project-state edits: agent proposes, PI approves.
  - Its private-vs-visible Q&A finding should shape Mycelium's consent design.
- **ResearStudio "plan-as-document" (medium effort, pattern).** Streams every step and tool call to a live, editable plan with pause/edit/resume. — [ACL Anthology](https://aclanthology.org/2025.emnlp-demos.69/)
  - A good demo-UI pattern for showing agent transparency at NAACL.
- **PaperFlow protocol (medium effort, evaluation).** An inspectable profile, a fixed daily display budget (cf. Mycelium's Top-25 slate), feedback-driven drift, and a longitudinal user-day benchmark. — [arXiv](https://arxiv.org/abs/2606.07454)
  - The closest published evaluation design for Mycelium's nightly slate; cite it and potentially adopt its protocol.
- **Scholar Inbox cold-start (medium effort).** A map of science plus active-learning rating prompts, and an 800k-rating public dataset. — [ACL Anthology](https://aclanthology.org/2025.acl-demo.30/)
  - The dataset could serve as an offline ranking eval. The active-learning prompt could become a Mylo Discord interaction.
- **Verification baselines.**
  - SciTrue: claim-component-to-source linking, human-evaluated. — [ACL Anthology](https://aclanthology.org/2026.eacl-demo.27/)
  - FactSearch: atomic-claim decomposition over self-hosted search. — [ACL Anthology](https://aclanthology.org/2026.acl-demo.36/)
  - CiteLab (MIT): a modular citation-generation and evaluation framework. — [ACL Anthology](https://aclanthology.org/2025.acl-demo.47)
  - All three are comparators for Mycelium's deterministic citation verifier. CiteLab could host an ablation.
- **Benchmarks.**
  - AstaBench: open, cost-aware, with literature-understanding sets. — [Ai2](https://allenai.org/blog/astabench)
  - DeepScholar-Bench: live; verifiability metric. — [arXiv](https://arxiv.org/html/2508.20033v2)
  - SciArena-Eval: for validating any LLM judge. — [NeurIPS](https://papers.neurips.cc/paper_files/paper/2025/hash/9811fe727c94e7ff79f701c94ed1d938-Abstract-Datasets_and_Benchmarks_Track.html)
  - DeepResearch Bench: RACE metric, but general-domain and partly Chinese, so less suitable. — [ODR README](https://github.com/langchain-ai/open_deep_research)
- **PaSa (medium–high effort).** An RL-trained crawler/selector with citation expansion and open 7B models. — [GitHub](https://github.com/bytedance/pasa)
  - Its Selector (title+abstract → relevance score) is a candidate reranker and baseline. Citation expansion is a retrieval channel Mycelium lacks.
  - Running 7B models adds GPU needs that Mycelium's host does not have (per project memory, no GPU on this host).

### Inferences
- A defensible NAACL 2027 framing:
  - Agentic routing (Paper Finder pattern) over **verified** deterministic tools.
  - A consent-gated lab memory benchmarked against Hindsight-style memory.
  - Push delivery evaluated with a PaperFlow-style longitudinal protocol and an AstaBench/DeepScholar slice.
  - This differs clearly from all prior demos and reuses permissively licensed components.
- Licence compatibility with Mycelium's Apache 2.0:
  - Compatible: PaperQA2, ai2-scholarqa-lib, OpenScholar, PaSa, GPT-Researcher and LLM×MapReduce (Apache-2.0); STORM, open_deep_research, Hindsight and TinyScientist (MIT).
  - No licence on GitHub: AutoSurvey, SurveyX, SurveyForge and IRIS. Treat them as reference-only.

### Gaps
- Effort estimates are my judgment from READMEs, not measured.
- I did not check whether PaperQA2's index can be pointed at an external pgvector store.
- Hindsight's very high star count is unexplained and should be re-checked.
