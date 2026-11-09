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
            32768,
            "The model's context window in tokens; drives the meter and "
            "compaction (the endpoint does not report it reliably).",
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
        # Discord (plan D)
        _s(
            "discord_access",
            "choice",
            "public",
            "Who may ask Mylo in a bound Discord server: public (anyone who can "
            "post there; people without an account ask as guests), linked "
            "(linked accounts only) or entitled (linked accounts whose plan "
            "includes the agent).",
            choices=("public", "linked", "entitled"),
        ),
        _s(
            "discord_guest_level",
            "choice",
            "full",
            "The most any lab may let a guest see in its server: full, no_people "
            "(no people functions), public (the thread's post and the corpus) or "
            "off. A lab's own setting can only lower it.",
            choices=("full", "no_people", "public", "off"),
        ),
        _s(
            "discord_guest_daily_turns",
            "int",
            10,
            "Questions per guest per day in Discord. 0 = no limit.",
        ),
        _s(
            "discord_place_daily_turns",
            "int",
            200,
            "Questions per Discord server per day. 0 = no limit.",
        ),
        _s(
            "discord_channel_session_hours",
            "int",
            24,
            "Hours a person's conversation in an open channel may be quiet "
            "before the next question starts a new one.",
        ),
        _s(
            "discord_closed_thread_days",
            "int",
            30,
            "Days a closed announcement's conversation is kept before the "
            "retention sweep deletes it.",
        ),
        _s(
            "discord_ping_after_minutes",
            "int",
            10,
            "An answer slower than this is posted as a new reply that pings the "
            "asker; a quicker one silently replaces the status message.",
        ),
        _s(
            "discord_turn_timeout_minutes",
            "int",
            30,
            "A Discord question still unanswered after this long is given up on.",
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
