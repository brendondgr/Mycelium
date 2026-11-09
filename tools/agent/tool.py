"""The agent tool's declaration. Standard library and spec imports only."""

from tools._framework.spec import Beat, Mount, Setting, Tool


def _s(key, kind, default, help_, **kw):
    env = "AGENT_" + key.upper()
    return Setting(key, kind, default, help_, env=env, django=env, **kw)


class AgentTool(Tool):
    name = "agent"
    summary = (
        "Mylo as a conversational agent: answers questions about everything a "
        "person may see in Mycelium (their profile, labs, projects, feeds, the "
        "corpus, the knowledge graph, stored papers and files), cites what it "
        "read, remembers, and changes nothing."
    )
    #: Corpus search, feeds and reports come from these; all three are core,
    #: so the agent is never blocked by an optional tool. Tools that add
    #: functions (fulltext, files) are not dependencies: they contribute
    #: through ``Tool.agent``.
    depends_on = ("retrieval", "recommendation", "delivery")
    agent = "tools.agent.functions"
    settings = (
        _s("model", "str", "", "The agent's model. Empty uses LLM_MODEL."),
        _s(
            "max_output_tokens",
            "int",
            0,
            "Most tokens one chat reply may use, thinking included. 0 = no cap.",
        ),
        _s(
            "context_window",
            "int",
            0,
            "The model's context window in tokens; drives the meter and "
            "compaction. 0 asks the model server (vLLM, llama.cpp, Ollama, "
            "Anthropic and Gemini report it) and falls back to 32768.",
        ),
        _s("max_steps", "int", 25, "Model calls per turn."),
        _s(
            "result_cap_tokens",
            "int",
            4000,
            "Tokens of one function result shown to the model; the rest is "
            "kept and read with read_result.",
        ),
        _s("daily_turns", "int", 0, "Turns per person per day. 0 = no limit."),
        _s(
            "learning",
            "bool",
            True,
            "Whether quiet chats are read for observations at all. Each person "
            "can still opt out.",
        ),
        _s(
            "learning_idle_minutes",
            "int",
            30,
            "Minutes a thread must be quiet before the learning pass reads it.",
        ),
        _s(
            "retention_days",
            "int",
            0,
            "Delete threads untouched for this many days. 0 keeps them.",
        ),
        _s(
            "groups_off",
            "list",
            [],
            'Function groups switched off on this instance, e.g. ["knowledge"].',
        ),
        _s(
            "surface_groups_off",
            "list",
            ["discord_channel:files"],
            'Groups switched off on one surface, as "surface:group"; '
            '"discord_channel:group" applies only where others read the reply.',
        ),
        _s(
            "max_risk",
            "choice",
            "read",
            "The most a function may do. Only read exists in this release.",
            choices=("read",),
        ),
        _s("redis_db", "int", 8, "Redis database for live streams (fulltext uses 7)."),
        _s(
            "parallel_calls",
            "bool",
            True,
            "Run the read-only calls of one step in parallel.",
        ),
    )
    beat = (
        Beat(
            "agent-learn-quiet-threads",
            "tools.agent.tasks.learn_from_quiet_threads",
            kwargs={"minute": "*/10"},
        ),
        Beat(
            "agent-resume-stuck-turns",
            "tools.agent.tasks.resume_stuck_turns",
            kwargs={"minute": "*/5"},
        ),
        Beat(
            "agent-retention-sweep",
            "tools.agent.tasks.retention_sweep",
            kwargs={"minute": "17", "hour": "4"},
        ),
    )
    mounts = (Mount("api/tools/agent/"),)
    health = "tools.agent.health:check"
