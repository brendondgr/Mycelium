# Mycelium Documentation

Everything here is meant to be true of the code as it stands. If a change makes a
document wrong, fix the document in the same commit.

## Direction — what we are building and why

| Doc | Read it when |
|---|---|
| [`purpose.md`](purpose.md) | You need to know what Mycelium is and who it is for |
| [`goals.md`](goals.md) | You are deciding what to build next, or want current build status |
| [`styles.md`](styles.md) | You are making a design, copy, mascot, or UX decision |

## Research record

Every experiment, result, figure, and claim lives in
[`research/`](research/). Nothing that will appear in a paper is recorded
anywhere else. Start at [`research/README.md`](research/README.md); the contract
is [`research/AGENT_INSTRUCTIONS.md`](research/AGENT_INSTRUCTIONS.md), and
[`research/CLAIMS.md`](research/CLAIMS.md) is the file to read first — its
`unsupported` rows are the experiment backlog.

## Reference — how it is built

| Doc | Read it when |
|---|---|
| [`repo-map.md`](repo-map.md) | You need to find code. **Read this before searching the tree.** |
| [`architecture.md`](architecture.md) | You need service boundaries, data ownership, or configuration |
| [`api-contract.md`](api-contract.md) | You are changing or consuming an HTTP payload |
| [`discord-integration.md`](discord-integration.md) | You are touching identity linking, guild activation, or delivery |
| [`loadtest.md`](loadtest.md) | You are stress-testing onboarding |
| [`evaluation.md`](evaluation.md) | You are running the retrieval harness or reading its leaderboard |
| [`research-audit.md`](research-audit.md) | You want an independent read on the ranking and agentic layers. **Its claims and workstreams are now tracked in [`research/CLAIMS.md`](research/CLAIMS.md) and [`research/OPEN_QUESTIONS.md`](research/OPEN_QUESTIONS.md)** — read those for current status, this for the reasoning behind them |

## Agent guidance

[`skills/index.md`](skills/index.md) is the registry. `docs/skills/` holds the
canonical text; `.claude/skills/`, `.agents/skills/`, and `.cursor/rules/` are
thin entrypoints pointing back at it. The repository-level instruction file is
[`../CLAUDE.md`](../CLAUDE.md).

## History and source material

- [`changelog.md`](changelog.md) — append-only record of what changed and why.
  Add an entry for any session that changes tracked files; never edit a past one.

## Conventions

- **No plans directory.** An implementation plan is a working document; delete it
  once the work ships and record the outcome in the changelog plus whichever
  reference doc the change affects.
- **Compact over comprehensive.** A locator beats a design essay. Rationale that
  is worth keeping belongs in `architecture.md`, not scattered through the map.
- **Say what is not built.** Neo4j and MinIO run in Compose and nothing reads
  them; the graph phase has not started. Documenting an aspiration as a fact is
  the failure mode these docs exist to avoid.
