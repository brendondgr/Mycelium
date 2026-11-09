# Agent memory systems and agent infrastructure for an agentic Mycelium

Compiled 2026-11-08. GitHub star counts, licences and last-push dates come from an authenticated `gh api repos/<owner>/<repo>` call made on 2026-11-08, cited as "[gh api]" next to the repo link. Venue and arXiv ids that I could not open in this session are marked **unverified-this-session**. They are given from prior knowledge so the writer can check them. They are not invented, but they are not re-confirmed either.

---

## Q1. Catalogue: paper, venue, track, repo, licence, activity, and whether each runs self-hosted on Postgres, CPU and an OpenAI-compatible endpoint

### Takeaway
Most agent-memory systems are vendor projects with arXiv preprints, not peer-reviewed papers. The peer-reviewed ones are mostly academic, sit in main tracks rather than demo tracks, and have small, slowly maintained repos. I found **no ACL/NAACL/EMNLP 2025 system-demonstration paper** for any of the candidate memory systems or frameworks. Two systems store memory in Postgres: Cognee (relational store plus pgvector) and Mem0 (pgvector, per prior knowledge). Graphiti/Zep needs a graph database (Neo4j, FalkorDB or Neptune), and Postgres is not a supported backend.

### Cited findings — memory systems

| System | Paper / venue / arXiv | Repo, licence, stars, last push [gh api] | Self-host on Postgres/CPU with an OpenAI-compatible endpoint? |
|---|---|---|---|
| **Zep / Graphiti** | "Zep: A Temporal Knowledge Graph Architecture for Agent Memory", Rasmussen, Paliychuk, Beauvais, Ryan, Chalef (all Zep AI), arXiv 2501.13956, Jan 2025, preprint — [arXiv](https://arxiv.org/html/2501.13956). Also presented as a talk at KGC 2025 — [KGC video](https://watch.knowledgegraph.tech/videos/zep-a-temporal-knowledge-graph-architecture-for-agent-memory-720p) | [getzep/graphiti](https://github.com/getzep/graphiti): Apache-2.0, 32.6k stars, pushed 2026-11-08. [getzep/zep](https://github.com/getzep/zep): Apache-2.0, 5.0k stars, pushed 2026-11-04 | Graph backends are Neo4j 5.26, FalkorDB, and Amazon Neptune. Kuzu is deprecated, and **Postgres is not mentioned**. Any OpenAI-compatible endpoint works through `OpenAIGenericClient` (Ollama, vLLM, llama.cpp, LM Studio). Small or local models "may emit JSON that doesn't match the schema", and a `json_object` mode is available as a fallback. Telemetry goes to PostHog and is on by default (opt out with `GRAPHITI_TELEMETRY_ENABLED=false`) — [graphiti README](https://github.com/getzep/graphiti) |
| **Mem0** | "Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory", Chhikara, Khant, Aryan, Singh, Yadav. arXiv 2504.19413, cs.CL, 28 Apr 2025. I found no peer-reviewed venue — [arXiv](https://arxiv.org/abs/2504.19413) | [mem0ai/mem0](https://github.com/mem0ai/mem0): Apache-2.0, 68.6k stars, pushed 2026-11-06 | The graph variant Mem0g uses Neo4j — [paper](https://arxiv.org/html/2504.19413v1). From prior knowledge (**unverified-this-session**), pgvector is a supported vector store and the LLM provider can be configured |
| **Letta (MemGPT)** | "MemGPT: Towards LLMs as Operating Systems", arXiv 2310.08560 (2023), **unverified-this-session** | [letta-ai/letta](https://github.com/letta-ai/letta): Apache-2.0, 25.4k stars, pushed 2026-10-18. The README says active source moved to `letta-ai/letta-code` and the V1 API server is now on an `archive` branch — [letta README](https://github.com/letta-ai/letta) | Self-hosted with `letta server`. The current docs describe the V1 SDK as "memory blocks only", and the new Agent SDK has "MemFS", a "git-tracked" memory that "leverages agent dreaming" — [Letta docs](https://docs.letta.com/concepts/memgpt). I could not confirm the Postgres backend from the pages I fetched |
| **A-MEM** | "A-Mem: Agentic Memory for LLM Agents", arXiv 2502.12110. The authors' repo calls it a **NeurIPS 2025** paper — [WujiangXu/A-mem](https://github.com/WujiangXu/A-mem) | [WujiangXu/A-mem](https://github.com/WujiangXu/A-mem): MIT, 1.0k stars, pushed 2026-10-28. [agiresearch/A-mem](https://github.com/agiresearch/A-mem): MIT, 1.2k stars, pushed 2025-12-12 [gh api] | A research codebase built on Zettelkasten-style linked notes, not production infrastructure |
| **MemoryOS** | "Memory OS of AI Agent", Kang et al., **EMNLP 2025 main**, Anthology 2025.emnlp-main.1318, arXiv 2506.06326 — [ACL Anthology](https://aclanthology.org/2025.emnlp-main.1318/) | [BAI-LAB/MemoryOS](https://github.com/BAI-LAB/MemoryOS): Apache-2.0, 1.6k stars, pushed 2026-07-07 | Short-, mid- and long-term personal memory tiers. Reports +3.2% over A-Mem on dialogue coherence — [arXiv](https://arxiv.org/pdf/2506.06326) |
| **MemOS** (MemTensor) | "MemOS: A Memory OS for AI System", arXiv 2507.03724 (v4 Dec 2025), plus an earlier short paper, arXiv 2505.22101. MemCube is its unit abstraction over plaintext, activation and parameter memory — [HF papers](https://huggingface.co/papers/2507.03724) | [MemTensor/MemOS](https://github.com/MemTensor/MemOS): Apache-2.0, 12.3k stars, pushed 2026-11-07 | Self-reported LoCoMo LLM-judge scores: MemOS 75.80, MIRIX 64.33, Mem0 59.22 — [arXiv](https://arxiv.org/html/2507.03724) |
| **MIRIX** | "MIRIX: Multi-Agent Memory System for LLM-Based Agents", arXiv 2507.07957, July 2025 (seen through a mirror) — [mirror](https://arxiv.deeppaper.ai/papers/2507.07957v1) | [Mirix-AI/MIRIX](https://github.com/Mirix-AI/MIRIX): Apache-2.0, 3.5k stars, pushed 2026-11-08 | Six memory types (Core, Episodic, Semantic, Procedural, Resource, Knowledge Vault), each managed by its own agent. Evaluated on ScreenshotVQA and LoCoMo — [mirror](https://arxiv.deeppaper.ai/papers/2507.07957v1) |
| **Cognee** | "Optimizing the Interface Between Knowledge Graphs and LLMs for Complex Reasoning", Markovic et al., arXiv 2505.24478, May 2025. Labelled a preliminary version, and its subject is hyperparameter tuning for multi-hop QA rather than memory — [arXiv](https://arxiv.org/html/2505.24478v1) | [topoteretes/cognee](https://github.com/topoteretes/cognee): Apache-2.0, 33.1k stars, pushed 2026-11-07 | **Yes for Postgres**: relational metadata in SQLite or PostgreSQL, pgvector as a vector store, and Neo4j, FalkorDB, Kuzu or NetworkX for the graph. The pipeline is add, cognify, memify, search. One commentary says memify's pruning and reweighting are not implemented in the defaults — [secondary summary](https://zby.github.io/commonplace/sources/cognee-knowledge-engine) |
| **LangMem** | No paper | [langchain-ai/langmem](https://github.com/langchain-ai/langmem): MIT, 1.8k stars, pushed 2026-11-03 | Built on LangGraph's store. In Mem0's LoCoMo run it had p95 search latency of 59.8 s — [Mem0 paper](https://arxiv.org/html/2504.19413v1) |
| **HippoRAG / HippoRAG 2** | HippoRAG, NeurIPS 2024, arXiv 2405.14831. HippoRAG 2, "From RAG to Memory: Non-Parametric Continual Learning for LLMs", arXiv 2502.14802, ICML 2025. Both **unverified-this-session** | [OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG): MIT, 4.1k stars, pushed 2026-10-06 | An OpenIE triple graph with Personalized PageRank. It targets corpora, not conversation streams |
| **Generative Agents** | Park et al., UIST 2023, arXiv 2304.03442, **unverified-this-session** | [joonspk-research/generative_agents](https://github.com/joonspk-research/generative_agents): Apache-2.0, 22.4k stars, **last push 2024-08-05 (dormant)** | A memory stream scored by recency, importance and relevance, plus reflection. Useful as a conceptual reference only |

**Benchmarks**
- **LoCoMo**: "Evaluating Very Long-Term Conversational Memory of LLM Agents", ACL 2024, arXiv 2402.17753 (**unverified-this-session**). Repo: [snap-research/locomo](https://github.com/snap-research/locomo), licence NOASSERTION, 1.3k stars, last push 2024-08-13 [gh api]. Its 10 conversations average about 26k tokens each — [Mem0 paper](https://arxiv.org/html/2504.19413v1).
- **LongMemEval**: arXiv 2410.10813, ICLR 2025 (**unverified-this-session**). Repo: [xiaowu0162/LongMemEval](https://github.com/xiaowu0162/LongMemEval), MIT, 1.2k stars, pushed 2026-05-11 [gh api]. LongMemEval_S has about 115k-token contexts — [Zep paper](https://arxiv.org/html/2501.13956).
- **"Are We Ready For An Agent-Native Memory System?"** (Zhou et al., arXiv 2606.24775, 23 Jun 2026) is a 2026 systems-level benchmark. It splits memory into representation/storage, extraction, retrieval/routing and maintenance, and evaluates 12 systems on 11 datasets. Its findings: "no single architecture dominates", and "localized maintenance is more cost-efficient than global reorganization" — [arXiv](https://arxiv.org/abs/2606.24775).

### Cited findings — infrastructure

| System | Paper / venue | Repo, licence, stars, last push [gh api] | Notes |
|---|---|---|---|
| **Model Context Protocol** | No paper. Current spec revision is **2026-07-28**, previous stable 2025-11-25 — [MCP versioning](https://modelcontextprotocol.io/docs/2026-07-28/learn/versioning) | [modelcontextprotocol/modelcontextprotocol](https://github.com/modelcontextprotocol/modelcontextprotocol): 9.6k stars. [servers](https://github.com/modelcontextprotocol/servers): 91.9k stars. [python-sdk](https://github.com/modelcontextprotocol/python-sdk): MIT, 24.8k stars | The 2026-07-28 spec makes the protocol stateless: no initialize handshake and no `Mcp-Session-Id`, with capabilities sent in each request's `_meta`. Multi Round-Trip Requests (`resultType: "input_required"`) replace server-initiated elicitation and sampling. Tasks moved to the `io.modelcontextprotocol/tasks` extension. Authorization was hardened: issuer (RFC 9207) validation, and Dynamic Client Registration (DCR) deprecated in favour of Client ID Metadata Documents (CIMD). Sampling, Roots and Logging are deprecated with a 12-month window — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/). MCP is "a Series of LF Projects, LLC" (same source), and the AAIF published the migration guide — [AAIF](https://aaif.io/blog/mcp-2026-07-28-whats-changing-and-how-to-migrate) |
| **Scholarly MCP servers** | None of them has a paper | [blazickjp/arxiv-mcp-server](https://github.com/blazickjp/arxiv-mcp-server): Apache-2.0, 3.3k stars, pushed 2026-10-08. [54yyyu/zotero-mcp](https://github.com/54yyyu/zotero-mcp): MIT, 5.8k stars, pushed 2026-11-06 [gh api] | Semantic Scholar and OpenAlex servers exist but are small community projects: hy20191108 semantic-scholar-mcp (MIT), pvliesdonk scholar-mcp (Semantic Scholar plus OpenAlex plus docling; unauthenticated S2 is limited to about 1 req/s), and oksure openalex-research-mcp with 18 tools — [lobehub](https://lobehub.com/mcp/hy20191108-semantic-scholar-mcp), [PyPI](https://pypi.org/project/pvliesdonk-scholar-mcp/1.2.1/), [lobehub](https://lobehub.com/en/mcp/oksure-openalex-research-mcp). I did not check their maintenance |
| **Agent Skills (SKILL.md)** | No paper. Open spec at agentskills.io — [spec](https://agentskills.io/specification) | [agentskills/agentskills](https://github.com/agentskills/agentskills): Apache-2.0, 27.1k stars. [anthropics/skills](https://github.com/anthropics/skills): 188.9k stars, no repo-level licence [gh api] | A skill is a directory holding `SKILL.md`, which has YAML frontmatter: `name` (at most 64 chars, lowercase and hyphens, must match the directory name) and `description` (at most 1024 chars, says what it does and when to use it). Optional fields are `license`, `compatibility`, `metadata` and an experimental `allowed-tools`. Optional subdirectories are `scripts/`, `references/` and `assets/`. Loading is progressive: about 100 tokens of metadata at startup, the body (under 5000 tokens recommended) on activation, and resources on demand. Validate with `skills-ref validate` — [spec](https://agentskills.io/specification) |
| **Claude Agent SDK** | No paper | [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python): MIT, 8.5k stars, pushed 2026-11-06 | Tied to Claude models, so it is a poor fit for an OpenAI-compatible proxy (my inference) |
| **OpenAI Agents SDK** | No paper | [openai/openai-agents-python](https://github.com/openai/openai-agents-python): MIT, 30.6k stars, pushed 2026-11-08 | |
| **LangGraph** | No paper | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph): MIT, 44.6k stars, pushed 2026-11-08 | |
| **smolagents** (Hugging Face) | No paper | [huggingface/smolagents](https://github.com/huggingface/smolagents): Apache-2.0, 30.3k stars | |
| **PydanticAI** | No paper | [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai): MIT, 21.1k stars, pushed 2026-11-08 | See Q3 |
| **DSPy** | "DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines", ICLR 2024, arXiv 2310.03714 (**unverified-this-session**) | [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy): MIT, 39.0k stars, pushed 2026-11-07 | |
| **Instructor** | No paper | [567-labs/instructor](https://github.com/567-labs/instructor): MIT, 14.1k stars | |
| **Outlines** | "Efficient Guided Generation for Large Language Models", arXiv 2307.09702 (**unverified-this-session**) | [dottxt-ai/outlines](https://github.com/dottxt-ai/outlines): Apache-2.0, 16.0k stars, pushed 2026-09-21 | Constrained decoding needs logit access, so it fits local vLLM or transformers better than a remote proxy (inference) |
| **AutoGen / AG2 / Microsoft Agent Framework** | AutoGen paper: arXiv 2308.08155, COLM 2024. AutoGen Studio: EMNLP 2024 demo. Both **unverified-this-session** | [microsoft/autogen](https://github.com/microsoft/autogen): 61.7k stars, repo licence CC-BY-4.0, which is the docs licence (code licence not checked). **In maintenance mode**: bug fixes and security patches only. The README names Microsoft Agent Framework as successor — [autogen README via search](https://github.com/microsoft/autogen). [microsoft/agent-framework](https://github.com/microsoft/agent-framework): MIT, 14.6k stars. [ag2ai/ag2](https://github.com/ag2ai/ag2): Apache-2.0, 5.1k stars, a community fork | Third-party sources date maintenance mode to October 2025 and give conflicting MAF 1.0 dates (2 or 3 April 2026) — [rywalker](https://rywalker.com/research/autogen) |
| **CrewAI** | No paper | [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI): MIT, 60.6k stars | |
| **Agno** (formerly phidata) | No paper | [agno-agi/agno](https://github.com/agno-agi/agno): Apache-2.0, 43.1k stars | |
| **Inspect AI** (UK AISI) | No paper | [UKGovernmentBEIS/inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai): MIT, 3.2k stars, pushed 2026-11-08 | |
| **Langfuse** | No paper | [langfuse/langfuse](https://github.com/langfuse/langfuse): 37.1k stars, licence NOASSERTION (open core plus EE features) | Self-hosting needs **Postgres, Redis/Valkey, ClickHouse, and S3/blob storage**, plus web and worker containers. Some add-ons need a licence key — [Langfuse self-hosting](https://langfuse.com/self-hosting) |
| **Arize Phoenix** | No paper | [Arize-ai/phoenix](https://github.com/Arize-ai/phoenix): 12.2k stars, licence NOASSERTION (Elastic License 2.0 per prior knowledge, **unverified-this-session**) | |
| **Django-native** | No paper | [vintasoftware/django-ai-assistant](https://github.com/vintasoftware/django-ai-assistant): MIT, 430 stars, last push 2026-03-23. [gts360/django-mcp-server](https://github.com/gts360/django-mcp-server): MIT, 386 stars, last push 2026-03-10 [gh api] | Both are small and were last pushed eight months ago |

### Inferences
- I found no demo-track papers for any candidate memory system or agent framework through ACL Anthology searches. The ACL/EMNLP 2025 hits were main-track research: MemoryOS, MemInsight, and "Unveiling Privacy Risks in LLM Agent Memory" — [search hits](https://aclanthology.org/2025.emnlp-main.1683/), [ACL 2025](https://aclanthology.org/2025.acl-long.1227/). For the owner's NAACL 2027 demo plan, the memory and agent demo niche looks open for a consent-first, verifiable lab-memory system.
- For Mycelium's stack (Postgres, CPU, a proxy endpoint), the lowest-friction options are Cognee, Mem0 and PydanticAI. Graphiti needs a new graph database, which is a new operational dependency.

### Gaps
- Several venues are not confirmed this session: MemGPT, LoCoMo (ACL 2024), LongMemEval (ICLR 2025), DSPy (ICLR 2024), AutoGen (COLM 2024), AutoGen Studio (EMNLP 2024 demo), HippoRAG/HippoRAG 2, Generative Agents, and Outlines.
- Mem0's pgvector support and Letta's current self-host storage backend were not confirmed from primary pages.
- I did not determine maintenance status for the Semantic Scholar and OpenAlex MCP servers.

---

## Q2. Memory systems: data model, contradiction and supersession, deletion, LoCoMo/LongMemEval numbers, and critiques

### Takeaway
Zep/Graphiti is the closest match to Mycelium's ledger. It keeps an episode → entity/fact → community hierarchy and gives each fact **bi-temporal edges** (four timestamps), so a contradicted fact is invalidated rather than deleted. Mem0 keeps flat LLM-curated facts, edited by the operations ADD, UPDATE, DELETE and NOOP. Published LoCoMo numbers are vendor-run, not comparable across reports, and partly contradicted. A plain filesystem agent scored 74% against Mem0's reported 68.5%. None of the memory papers addresses consent or privacy-driven deletion.

### Cited findings
**Zep / Graphiti data model and updates**
- There are three subgraphs. The episode subgraph holds raw messages, text or JSON. The semantic-entity subgraph holds entities plus fact edges, modelled as hyper-edges. The community subgraph holds clusters with summaries. Episodic edges link each episode to the entities it mentions — [Zep paper](https://arxiv.org/html/2501.13956).
- Each fact carries t'created and t'expired (transaction time) and t_valid and t_invalid (real-world validity). An LLM compares each new edge with related edges. When two facts contradict and overlap in time, the old edge's t_invalid is set to the new edge's t_valid. On the transaction timeline, newer information wins — [Zep paper](https://arxiv.org/html/2501.13956).
- Entity resolution embeds names (1024-d) and runs full-text search over names and summaries, then an LLM judges duplicates. Retrieval combines cosine, BM25 (Neo4j's Lucene implementation) and n-hop BFS. Reranking options are RRF, MMR, episode-mention frequency, node distance, and a cross-encoder — [Zep paper](https://arxiv.org/html/2501.13956).
- Ontology can be prescribed as Pydantic entity and edge types, or learned from the data. Every derived fact traces back to the episodes it came from. The reference MCP server supports deleting episodes. Its README says it has **no authentication or authorization, and any caller can reach any `group_id`** — [graphiti README](https://github.com/getzep/graphiti).
- Results on LongMemEval_S:

  | Setup | Accuracy | Latency | Context tokens |
  |---|---|---|---|
  | Full context, gpt-4o-mini | 55.4% | 31.3 s | 115k |
  | Zep, gpt-4o-mini | 63.8% | 3.20 s | 1.6k |
  | Full context, gpt-4o | 60.2% | 28.9 s | 115k |
  | Zep, gpt-4o | 71.2% | 2.58 s | 1.6k |

  Accuracy *fell* on single-session-assistant questions (−9.06% with gpt-4o-mini, −17.7% with gpt-4o). On DMR, Zep scored 94.8% against MemGPT's 93.4% (gpt-4-turbo). The authors call DMR weak: about 60 messages per conversation, and full-context baselines already reach 98% — [Zep paper](https://arxiv.org/html/2501.13956).
- The paper's stated limitations: latency was measured from a residential laptop to AWS; community updates drift and need periodic refresh; weaker models struggle with the temporal data; deletion and privacy are not addressed — [Zep paper](https://arxiv.org/html/2501.13956).

**Mem0 data model and updates**
- Extraction runs on each new message pair. The prompt contains an asynchronously refreshed conversation summary, the last 10 messages, and the new pair. For each extracted fact, the 10 most similar existing memories are retrieved, and an LLM tool call chooses **ADD, UPDATE, DELETE or NOOP**. DELETE removes memories that new information contradicts — [Mem0 paper](https://arxiv.org/html/2504.19413v1).
- The graph variant Mem0g (on Neo4j) **marks obsolete relationships invalid instead of deleting them**, so history stays available for temporal reasoning — [Mem0 paper](https://arxiv.org/html/2504.19413v1).
- LoCoMo overall J scores from Mem0's own run:

  | Method | Overall J |
  |---|---|
  | Full context | 72.90 |
  | Mem0g | 68.44 |
  | Mem0 | 66.88 |
  | Zep | 65.99 |
  | Best RAG | 60.97 |
  | LangMem | 58.10 |
  | OpenAI memory | 52.90 |
  | A-Mem | 48.38 |

  The adversarial category was excluded, all 10 conversations were used, and scores are means over 10 runs. Median total latency was 0.708 s for Mem0 against 9.87 s for full context. Tokens retrieved per query were 1,764 for Mem0 against 26k for full context. Memory store sizes were about 7k tokens for Mem0 and over 600k for Zep — [Mem0 paper](https://arxiv.org/html/2504.19413v1).

**Critiques of the numbers**
- Zep argues that Mem0's comparison used a flawed LoCoMo setup and implemented Zep incorrectly: the user model, timestamp placement, and sequential vs parallel search. Zep's corrected LoCoMo score is 75.14% ± 0.17 — [Zep blog](https://blog.getzep.com/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/).
- Letta put the LoCoMo history in a file and gave a simple agent filesystem tools. With gpt-4o-mini it scored **74.0%**, above Mem0's reported 68.5%. Letta concludes that LoCoMo measures retrieval, not memory management — [Letta blog](https://www.letta.com/blog/benchmarking-ai-agent-memory).
- Mem0 reports a new algorithm (April 2026) scoring 92.5 on LoCoMo. Zep claims 94.7 in 2026. They use different models and setups, so the scores are not comparable. Third-party commentary also notes that Zep scored 58.44 or 65.99 when Mem0 ran it and 75.14 or 94.7 when Zep ran it — [Mem0 blog](https://mem0.ai/blog/ai-memory-benchmarks), [braindetox](https://braindetox.kr/en/posts/memory_benchmark_scores_reliability_2026.html), with the secondary sources flagged as such.
- MemOS's self-reported LoCoMo scores are MemOS 75.80, MIRIX 64.33 and Mem0 59.22. That is another vendor-run table in which Mem0 scores lower than in Mem0's own run — [MemOS arXiv](https://arxiv.org/html/2507.03724).
- A 2026 module-level evaluation says end-to-end F1/BLEU-style metrics treat memory as a black box and leave out cost, update correctness and robustness to dynamic updates. It finds that no architecture wins everywhere — [arXiv 2606.24775](https://arxiv.org/abs/2606.24775).

**Other systems**
- MIRIX uses six typed memories, each managed by its own agent — [mirror](https://arxiv.deeppaper.ai/papers/2507.07957v1).
- MemoryOS uses OS-style short-, mid- and long-term tiers — [ACL Anthology](https://aclanthology.org/2025.emnlp-main.1318/).
- Letta's newest memory, MemFS, is a git-tracked memory with "agent dreaming" — [Letta docs](https://docs.letta.com/concepts/memgpt).
- In Cognee, memify enriches the graph after ingestion — [secondary](https://zby.github.io/commonplace/sources/cognee-knowledge-engine).

### Inferences
- Mycelium's Observation ledger already does supersession and retraction. What it lacks is Graphiti's **explicit validity interval** (valid_at/invalid_at) separated from the **ingestion interval** (created_at/expired_at). Adding these four columns to Observations, or to KG edges, lets "what did the lab believe on date X" be answered in Postgres without a graph database.
- In both Zep and Mem0g, provenance points back to raw episodes. Mycelium deliberately does **not** keep raw text (it lives only in a TTL Redis buffer). So each Observation's provenance should point to a message id or hash plus its consent scope, never to stored text. This is a real point of difference for a paper.
- The Letta filesystem result and the Tran & Kiela single-agent finding (below) suggest that a simple agent given good search tools over the existing ledger may match a dedicated memory layer on retrieval-style benchmarks.
- The Tran & Kiela finding is in "Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets", Tran & Kiela, arXiv 2604.02460, Apr 2026. Its results: single agents match or beat multi-agent systems at equal thinking-token budgets, and multi-agent systems become competitive only when the context is corrupted — [arXiv](https://arxiv.org/abs/2604.02460). This supports one agent with tools over a crew of agents.

### Gaps
- I did not obtain A-MEM's or MemoryOS's own LoCoMo or LongMemEval numbers, or Letta's own numbers on LongMemEval.
- I found no independent, third-party reproduction of any vendor's LoCoMo numbers. The 2606.24775 benchmark may contain one, but I only read its abstract.

---

## Q3. Frameworks: how tools and skills are declared, how existing deterministic verifiers could be wrapped, lock-in and dependency weight

### Takeaway
PydanticAI maps most directly onto Mycelium's existing pattern of a schema-constrained output, a deterministic verifier, and one bounded repair. Its output validators raise `ModelRetry` under a configurable retry budget whose default is 1, which is exactly "one bounded repair". MCP is the right boundary for exposing Mycelium's tools to *external* agents. Agent Skills is a lightweight, vendor-neutral format for procedural knowledge such as "how to run a lit review in this lab". AutoGen is in maintenance mode, and Langfuse's self-host stack is heavy.

### Cited findings
- **PydanticAI**: tools are plain functions registered with `@agent.tool` (which receives `RunContext`) or `@agent.tool_plain`. The function's docstring becomes the tool description. Output validators are declared with `@agent.output_validator`, and raising `ModelRetry` sends the error back to the model. The default output retry budget is **1** and can be set with `retries={'output': N}`. The docs' own example validates SQL with `EXPLAIN` and retries on error. There are three output modes: Tool Output (the default, an output tool whose arguments are the schema), Native Output (JSON-schema response format), and Prompted Output (least reliable) — [PydanticAI docs](https://pydantic.dev/docs/ai/core-concepts/output/).
- **Agent Skills**: a filesystem convention (`SKILL.md`, `scripts/`, `references/`, `assets/`) with progressive disclosure and an experimental `allowed-tools` field for pre-approved tools. It is maintained as an open spec with a validator, `skills-ref` — [spec](https://agentskills.io/specification).
- **MCP 2026-07-28** is stateless. Any server instance behind a load balancer can serve any request, and apps that need state should "mint an explicit handle from a tool and pass it back as an argument". `tools/list` responses can be cached (`ttlMs`, `cacheScope`). Header routing (`Mcp-Method`, `Mcp-Name`) lets gateways rate-limit without parsing request bodies — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/). This suits a Django view behind nginx, which is my inference.
- **Graphiti's MCP reference server has no authN or authZ** — [graphiti README](https://github.com/getzep/graphiti). It is a cautionary example for any Mycelium MCP endpoint that exposes ledger data.
- **AutoGen** takes bug fixes and security patches only. New projects are pointed to Microsoft Agent Framework — [autogen](https://github.com/microsoft/autogen).
- **Langfuse** self-hosting needs Postgres, Redis, ClickHouse and S3 — [Langfuse](https://langfuse.com/self-hosting). ClickHouse would be a new stateful service for Mycelium.
- **Graphiti** works best with providers that support structured output. Local models may break the schema, and `SEMAPHORE_LIMIT` should be kept low for local servers — [graphiti README](https://github.com/getzep/graphiti). This matters for Mycelium's proxy endpoint.

### Inferences
- Mycelium's verifiers can be wrapped two ways. (a) The citation verifier becomes a PydanticAI output validator that raises `ModelRetry(reason)`. (b) Deterministic lookups (KG query, ledger search, paper facets, opportunity search) become `@agent.tool` functions that call existing Django service functions inside the user's authorization context. The agent loop can therefore never see data the consent gate would withhold.
- On weight: PydanticAI, Instructor, smolagents and the MCP Python SDK are libraries. LangGraph, CrewAI and Agno bring their own orchestration, state and persistence abstractions, which overlap with Celery and Postgres. The OpenAI Agents SDK and Claude Agent SDK lean toward their vendors' models. DSPy is most useful for *optimizing* the existing fixed prompts against the research-record evaluation sets, not as a runtime agent.
- For tracing, Inspect AI (MIT, Python, file-based logs) fits Mycelium's `docs/research/experiments` discipline better than Langfuse's ClickHouse stack. Phoenix's licence needs a check before it is bundled with an Apache-2.0 product.

### Gaps
- I did not fetch the tool-declaration docs for the OpenAI Agents SDK, LangGraph, smolagents or Agno this session. The comparisons above rely on general knowledge, not on pages fetched this session.
- I did not verify Phoenix's licence (Elastic License 2.0?) or AutoGen's code licence.

---

## Q4. Privacy and consent for agents that listen to team chat

### Takeaway
There is active 2025–26 work on **contextual integrity (CI) of persistent agent memory**. It shows that frontier models leak memory attributes into the wrong context, that the leakage grows with usage, and that prompting does not fix it. That argues for enforcing visibility deterministically *before* context assembly, which Mycelium's consent gate already does. I found no paper on per-person consent for an ambient Slack or Discord listener, which suggests a gap Mycelium could fill.

### Cited findings
- **CIMemories** (Mireshghallah et al., arXiv 2511.14937, Nov 2025, preprint) uses synthetic profiles with more than 100 attributes. Frontier models reach up to **69% attribute-level violations**. GPT-5's violation rate grows from 0.1% to 9.6% as usage goes from 1 to 40 tasks, and reaches 25.1% over 5 runs of the same prompt. Privacy prompting does not fix it, because models overgeneralize to sharing everything or nothing — [arXiv](https://arxiv.org/abs/2511.14937).
- **CI-Work**, "Benchmarking Contextual Integrity in Enterprise LLM Agents", is an **ACL 2026 Industry track** paper. It reports a privacy-utility trade-off, with violations that can accumulate in persistent memory. Its data is synthetic and its environments simulated — [ACL Anthology PDF](https://aclanthology.org/2026.acl-industry.103.pdf). I saw only snippets, not the full paper.
- **"Unveiling Privacy Risks in LLM Agent Memory"**, ACL 2025 long paper, studies extracting private stored interactions from an agent's memory module — [ACL Anthology](https://aclanthology.org/2025.acl-long.1227/).
- Other 2026 leads seen only as titles or snippets:
  - "Authorization Before Context: A Model-Neutral Audience Boundary Against Cross-Audience Memory Leakage in Agentic Systems" (arXiv 2608.17148) — [arXiv](https://arxiv.org/pdf/2608.17148)
  - MuPPET, on contextual privacy in multi-party conversations (arXiv 2606.23217) — [arXiv](https://arxiv.org/pdf/2606.23217)
  - HUSH-Bench, on memory-use boundaries for sensitive history (arXiv 2606.06055) — [arXiv](https://arxiv.org/pdf/2606.06055)
  - "Got a Secret? LLM Agents Can't Keep It" (arXiv 2605.27766) — [arXiv](https://arxiv.org/pdf/2605.27766)

### Inferences
- "Authorization before context" names exactly the pattern Mycelium uses: filter the ledger by visibility and consent in SQL, then let the model see only what passed. Any agentic version must keep tools as the only path to data, with authorization applied inside each tool, not left to the model's judgement.
- MuPPET (multi-party conversations) and CIMemories (memory growth over time) are natural evaluation sets for an agentic Mycelium. A consent-aware lab assistant, scored on CI leakage alongside utility, is a publishable angle that is not crowded.

### Gaps
- I did not read the full CI-Work, MuPPET, HUSH-Bench or "Authorization Before Context" papers. Their methods and numbers are unverified.
- I found no paper on consent withdrawal or retraction propagation (a person revoking consent leads to deletion of derived memories) in agent memory systems. None of the memory papers (Zep, Mem0) addresses it.

---

## Q5. Concrete adoption candidates for Mycelium, their cost, and the practical path from fixed pipelines to an agent with tools

### Takeaway
Do not adopt a memory product wholesale. Borrow Graphiti's **bi-temporal edge model** into the existing Postgres ledger and KG. Wrap existing deterministic services as typed tools with in-tool authorization. Run **one agent** (not a multi-agent crew) through a light library such as PydanticAI, keeping the existing verifiers as output validators. Expose the same tools over **MCP** for external clients, and package lab procedures as **Agent Skills**. Measure with LongMemEval-style temporal questions plus a contextual-integrity leakage set.

### Cited findings (grounding)
- Bi-temporal invalidation keeps history queryable while answering what is currently valid — [Zep paper](https://arxiv.org/html/2501.13956). Mem0g likewise marks relationships invalid rather than deleting them — [Mem0 paper](https://arxiv.org/html/2504.19413v1).
- A filesystem-tool agent reached 74% on LoCoMo — [Letta blog](https://www.letta.com/blog/benchmarking-ai-agent-memory). Single agents match or beat multi-agent systems at equal token budgets — [arXiv 2604.02460](https://arxiv.org/abs/2604.02460).
- `ModelRetry` validators with a bounded retry budget — [PydanticAI](https://pydantic.dev/docs/ai/core-concepts/output/).
- Stateless MCP suits horizontally served HTTP — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/). The reference memory MCP server has no authN, which is the anti-pattern to avoid — [graphiti README](https://github.com/getzep/graphiti).
- The SKILL.md format and progressive disclosure — [agentskills.io](https://agentskills.io/specification).
- Prompting does not fix CI leakage — [CIMemories](https://arxiv.org/abs/2511.14937).

### Adoption candidates
1. **Bi-temporal columns on Observations and KG edges.**
   - Add `valid_from`, `valid_to`, `recorded_at` and `expired_at`, plus a `superseded_by` foreign key.
   - Map the existing supersession onto `valid_to` and `expired_at`. A retraction (message edited or deleted, or consent withdrawn) becomes a **hard delete or tombstone** rather than an invalidation, because consent is not a belief change.
   - Cost: one migration plus query changes. No new service.
2. **Tool layer over existing services.** Candidate tools:
   - `search_ledger(subject, kind, since)`
   - `kg_neighbors(concept)`
   - `paper_facets(id)`
   - `search_papers(q)` (the existing unified search)
   - `opportunities(q)`
   - `verify_citations(text)`
   - `post_digest_draft()`, which needs human approval

   Each tool is a typed Python function that calls the Django service with the requesting user's authorization. Cost: mostly thin wrappers.
3. **One agent runtime.** PydanticAI (MIT, library) works over the existing OpenAI-compatible proxy, with the current Pydantic schemas becoming output types and the citation verifier an output validator with `retries={'output': 1}`. It runs inside Celery tasks and the Mylo slash-command handlers. Cost: one dependency.
   - Alternatives: smolagents (Apache-2.0, code-agents) or a hand-rolled tool loop with Instructor.
   - Avoid for now: LangGraph, CrewAI and Agno, which duplicate Celery and Postgres state; and AutoGen, which is in maintenance mode.
4. **MCP server.** Mount the same tools as an MCP endpoint, either with the Python SDK or by studying [gts360/django-mcp-server](https://github.com/gts360/django-mcp-server) (small, MIT). Require OAuth per the 2026-07-28 authorization rules, so researchers' Claude, Cursor or other MCP clients can query their lab's ledger under the same consent gates. Optionally consume scholarly MCP servers (arXiv, Zotero) as tools, but beware rate limits and maintenance.
5. **Skills.** Ship `skills/` folders in SKILL.md format for lab procedures (lit-review sweep, reading-group prep, grant-deadline triage), loaded by progressive disclosure. They are vendor-neutral, and the cost is content-writing only.
6. **Evaluation and tracing.**
   - Record agent runs as experiments under `docs/research/experiments`.
   - Use Inspect AI (MIT) for agent evals.
   - Build a small temporal-QA set in the LongMemEval style over the ledger.
   - Add a CI-leakage probe set modelled on CIMemories and MuPPET.
   - Langfuse only if the operator accepts ClickHouse.
7. **Optional, research-only: Graphiti as a comparison baseline.** Not for production. It would need FalkorDB or Neo4j, and its MCP server lacks auth. It is useful as the reference temporal-KG arm in a paper.

### Inferences
- Order of work:
  1. Tools (read-only).
  2. Single agent for Mylo Q&A, with no write tools.
  3. Bi-temporal ledger.
  4. Agent-proposed Observations that still pass the deterministic verifier and consent gate before commit.
  5. MCP exposure.
  6. Skills.

  Each step keeps verifiability: the model chooses tools, but deterministic code still decides what is visible and what is committed.
- A publishable framing that sets Mycelium apart from Zep, Mem0 and Letta has three parts:
  - a **consent-scoped, text-free provenance** memory (no raw episodes kept);
  - **retraction propagation** as a first-class operation, distinct from temporal invalidation;
  - evaluation on **both** temporal QA and CI leakage.

### Gaps
- I found no published Django-native agent framework with real adoption. The two Django packages are small and their last pushes were in March 2026.
- I have not measured cost or latency of a tool-calling loop through Mycelium's proxy on a CPU-only host. A tool loop multiplies LLM calls, and that should be benchmarked as an experiment before rollout.
