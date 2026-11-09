"""The instance configuration layer: ``mycelium.toml`` plus deployment profiles.

Everything an operator decides about *their* Mycelium — who may sign up, whether
billing exists, how much a person or lab may track, which optional features run,
how much the nightly run may spend — resolves here, in four layers, each
overriding the one before:

1. built-in defaults (:data:`SETTINGS`),
2. the deployment **profile** (``personal`` / ``lab`` / ``department`` /
   ``institution``, :data:`PROFILES`),
3. ``mycelium.toml`` at the repository root,
4. environment variables (each setting names the one it answers to).

Secrets never live here: API keys, passwords and the sign-up access code stay in
``.env``.

This module is deliberately **standard library only** and imports nothing from
Django, so ``settings.py`` and the host-side ``ops/mycelium config`` CLI read the
exact same definitions — there is one list of keys, one set of profiles, and one
merge rule. ``settings.py`` re-exports the resolved values under the names the
code already reads (``AMBIENT_ENABLED``, ``SIGNUP_GRANT_TIER``, ...), so a call
site never has to know which layer a value came from.
"""

from __future__ import annotations

import os
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: ``limit`` values use ``None`` for "unlimited".
UNLIMITED = None

CONFIG_FILENAME = "mycelium.toml"
PROFILE_NAMES = ("personal", "lab", "department", "institution")
DEFAULT_PROFILE = "lab"

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
_UNLIMITED_WORDS = {"unlimited", "none", "off", "-1"}


class ConfigError(ValueError):
    """The configuration is invalid; the message names the key and the fix."""


@dataclass(frozen=True)
class Setting:
    """One governed key.

    ``kind`` is ``bool`` | ``int`` | ``limit`` (an int or unlimited) | ``str`` |
    ``choice`` | ``list``. ``suggested`` is the number the generated file shows
    in a comment for a limit that ships unlimited, so an operator who wants the
    limit back has a sensible value to start from.
    """

    key: str
    kind: str
    default: Any
    help: str
    env: str | None = None
    choices: tuple[str, ...] = ()
    suggested: Any = None

    @property
    def section(self) -> str:
        return self.key.rsplit(".", 1)[0]

    @property
    def name(self) -> str:
        return self.key.rsplit(".", 1)[1]


# --------------------------------------------------------------------------- #
# The keys
# --------------------------------------------------------------------------- #

_TIER_DEFAULTS: dict[str, dict[str, int | None]] = {
    # Today's per-tier numbers, moved out of apps.billing.entitlements. They only
    # apply while billing.mode = "subscriptions".
    "free": {"clusters": 3, "topics_per_cluster": 2, "watch_topics": 6,
             "personal_projects": 2, "members": 1, "leads": 1},
    "spore": {"clusters": 6, "topics_per_cluster": 10, "watch_topics": 20,
              "personal_projects": 5, "members": 1, "leads": 1},
    "lab": {"clusters": 6, "topics_per_cluster": 15, "watch_topics": 15,
            "personal_projects": 5, "members": 15, "leads": 5},
    "canopy": {"clusters": 6, "topics_per_cluster": 15, "watch_topics": 15,
               "personal_projects": 5, "members": None, "leads": None},
}

_TIER_HELP = {
    "clusters": "interest clusters (one literature search each)",
    "topics_per_cluster": "search terms per cluster",
    "watch_topics": "watch topics in total",
    "personal_projects": "active personal projects",
    "members": "seats on one plan",
    "leads": "PIs (lab leads) per lab",
}


def _tier_settings() -> list[Setting]:
    out = []
    for tier, values in _TIER_DEFAULTS.items():
        for name, value in values.items():
            out.append(
                Setting(
                    f"limits.tiers.{tier}.{name}",
                    "limit",
                    value,
                    f"{tier.title()} tier: {_TIER_HELP[name]}.",
                )
            )
    return out


SETTINGS: tuple[Setting, ...] = (
    # ---- instance --------------------------------------------------------
    Setting(
        "instance.profile", "choice", DEFAULT_PROFILE,
        "Who this instance serves. Sets the starting value of every other key; "
        "anything below overrides it.",
        env="MYCELIUM_PROFILE", choices=PROFILE_NAMES,
    ),
    # ---- billing ---------------------------------------------------------
    Setting(
        "billing.mode", "choice", "off",
        "off: no plans, tiers or seats; everyone gets [limits] and labs and "
        "departments start active. subscriptions: today's tiered plans, seats "
        "and the [limits.tiers.*] numbers.",
        env="BILLING_MODE", choices=("off", "subscriptions"),
    ),
    Setting(
        "billing.enforce_features", "bool", False,
        "Under subscriptions, let a tier withhold features (LLM scoring, reports, "
        "team workspace...). Off grants every feature to everyone and keeps only "
        "the tier limits.",
        env="BILLING_ENFORCE_ENTITLEMENTS",
    ),
    Setting(
        "billing.signup_tier", "choice", "spore",
        "Under subscriptions, the personal tier a new account starts on.",
        env="SIGNUP_GRANT_TIER", choices=("free", "spore"),
    ),
    # ---- limits (billing off) -------------------------------------------
    Setting("limits.clusters", "limit", UNLIMITED,
            "Interest clusters per person. Mylo runs one literature search per "
            "cluster each night.", env="LIMIT_CLUSTERS", suggested=6),
    Setting("limits.topics_per_cluster", "limit", UNLIMITED,
            "Search terms per cluster.", env="LIMIT_TOPICS_PER_CLUSTER",
            suggested=10),
    Setting("limits.watch_topics", "limit", UNLIMITED,
            "Watch topics per person, across all clusters.",
            env="LIMIT_WATCH_TOPICS", suggested=20),
    Setting("limits.personal_projects", "limit", UNLIMITED,
            "Active personal projects per person (each is scored nightly).",
            env="LIMIT_PERSONAL_PROJECTS", suggested=5),
    Setting("limits.lab_projects", "limit", UNLIMITED,
            "Active projects per lab. Applies under subscriptions too.",
            env="LIMIT_LAB_PROJECTS", suggested=10),
    Setting("limits.department_projects", "limit", UNLIMITED,
            "Active projects per department. Applies under subscriptions too.",
            env="LIMIT_DEPARTMENT_PROJECTS", suggested=30),
    Setting("limits.lab_members", "limit", UNLIMITED,
            "Members per lab.", env="LIMIT_LAB_MEMBERS", suggested=15),
    Setting("limits.lab_leads", "limit", UNLIMITED,
            "PIs (lab leads) per lab.", env="LIMIT_LAB_LEADS", suggested=5),
    *_tier_settings(),
    # ---- signup ----------------------------------------------------------
    Setting(
        "signup.mode", "choice", "invite",
        "closed: only an admin creates accounts. invite: an invite link or email "
        "from someone inside. code: the shared access code in .env "
        "(SIGNUP_ACCESS_CODE), or an invite. domain: any address at "
        "signup.allowed_domains, or an invite (needs email). open: anyone.",
        env="SIGNUP_MODE", choices=("closed", "invite", "code", "domain", "open"),
    ),
    Setting("signup.allowed_domains", "list", [],
            "Email domains admitted by signup.mode = \"domain\", e.g. "
            "[\"fsu.edu\"]. A subdomain of a listed domain counts.",
            env="SIGNUP_ALLOWED_DOMAINS"),
    Setting("signup.verify_email", "bool", False,
            "Mail a code that must be answered before an account can create a "
            "lab or department or invite people. Needs an [email] provider. "
            "Off: accounts are active as soon as they exist.",
            env="SIGNUP_VERIFY_EMAIL"),
    Setting("signup.require_institution_email", "bool", False,
            "Refuse sign-up from an address that matches no known institution "
            "(invited addresses are exempt).",
            env="SIGNUP_REQUIRE_INSTITUTION_EMAIL"),
    # ---- email -----------------------------------------------------------
    Setting(
        "email.provider", "choice", "none",
        "none: mail is printed to the backend log, never sent. resend: the "
        "Resend API (RESEND_API_KEY in .env). smtp: any SMTP server "
        "(EMAIL_HOST_PASSWORD in .env).",
        env="EMAIL_PROVIDER", choices=("none", "resend", "smtp"),
    ),
    Setting("email.from", "str", "Mycelium <mycelium@localhost>",
            "The From address. Its domain must be verified with your provider.",
            env="DEFAULT_FROM_EMAIL"),
    Setting("email.reply_to", "str", "",
            "Optional Reply-To. Blank means replies go to the From address.",
            env="EMAIL_REPLY_TO"),
    Setting("email.smtp_host", "str", "", "SMTP server host.", env="EMAIL_HOST"),
    Setting("email.smtp_port", "int", 587, "SMTP server port.", env="EMAIL_PORT"),
    Setting("email.smtp_user", "str", "", "SMTP user name.",
            env="EMAIL_HOST_USER"),
    Setting("email.smtp_tls", "bool", True, "Use STARTTLS for SMTP.",
            env="EMAIL_USE_TLS"),
    # ---- features --------------------------------------------------------
    Setting("features.ambient", "bool", False,
            "Mylo listens in consenting Discord/Slack channels to keep profiles "
            "current.", env="AMBIENT_ENABLED"),
    Setting("features.ambient_deliberate", "bool", False,
            "Nightly reasoning over what was heard (needs features.ambient).",
            env="AMBIENT_DELIBERATE_ENABLED"),
    Setting("features.ambient_drift", "bool", False,
            "Let confirmed explorations join a person's paper search.",
            env="AMBIENT_DRIFT_ENABLED"),
    Setting("features.ambient_transcripts", "bool", False,
            "Accept uploaded meeting transcripts as evidence.",
            env="AMBIENT_TRANSCRIPTS_ENABLED"),
    Setting("features.collab_search", "bool", False,
            "Outward collaborator search across consenting people.",
            env="COLLAB_SEARCH_ENABLED"),
    Setting("features.project_alerts", "bool", False,
            "Alerts when a finding bears on a project.",
            env="PROJECT_ALERTS_ENABLED"),
    Setting("features.announcements", "bool", False,
            "Discord threads for newly fitting grants, fellowships, conferences.",
            env="OPPORTUNITY_ANNOUNCEMENTS_ENABLED"),
    Setting("features.high_signal", "bool", False,
            "Out-of-band messages for exceptionally strong matches.",
            env="HIGH_SIGNAL_DELIVERY_ENABLED"),
    Setting("features.rerank", "bool", False,
            "Rerank each slate's head with a second model.",
            env="RERANK_ENABLED"),
    Setting("features.slack", "bool", False, "The Slack integration.",
            env="SLACK_ENABLED"),
    Setting("features.teams", "bool", False, "The Microsoft Teams integration.",
            env="TEAMS_ENABLED"),
    # ---- llm ---------------------------------------------------------------
    Setting("llm.max_tokens", "int", 0,
            "Most tokens one model reply may use, thinking included. 0 sends no "
            "cap, so a reasoning model is never starved before it answers; set "
            "a number only if your endpoint needs one.",
            env="LLM_MAX_TOKENS"),
    Setting("llm.default", "str", "local",
            "The model server every component uses unless [llm.routes] sends "
            "it elsewhere. \"local\" is the endpoint in .env (LLM_BASE_URL, "
            "LLM_MODEL) unless you declare [llm.providers.local] yourself."),
    Setting("llm.allow_cloud", "bool", False,
            "Let a cloud server (OpenAI, Anthropic, Gemini, DeepSeek or another "
            "public API) be called. Off: a cloud server never loads and no text "
            "leaves this host for one."),
    Setting("llm.fallback", "list", [],
            "Servers tried, in order, when the routed one is down. Empty: no "
            "fallback. A cloud server listed here is still skipped while "
            "allow_cloud is false."),
    # ---- decision model ---------------------------------------------------
    Setting(
        "decision.backend", "choice", "auto",
        "Which decision model re-orders the top of each theme's slate. jev: "
        "TypeSafe's hosted model (TYPESAFE_API_KEY in .env; sends profile and "
        "item text off this host). port: a model you serve yourself at "
        "port_url (llama.cpp, vLLM or a decide server). off: no decision "
        "model, the plain ranking stands. auto: jev with a key, else port with "
        "a URL, else off.",
        env="DECISION_BACKEND", choices=("auto", "jev", "port", "off"),
    ),
    Setting("decision.port_url", "str", "",
            "Where the self-hosted decision model answers, e.g. "
            "\"http://127.0.0.1:8080\" (a trailing /v1 is fine). A key, if the "
            "server wants one, goes in .env as DECISION_PORT_API_KEY.",
            env="DECISION_PORT_URL"),
    Setting(
        "decision.port_protocol", "choice", "auto",
        "decide: a decision server's POST /v1/decide. openai: an "
        "OpenAI-compatible chat server read through logprobs (llama.cpp's "
        "llama-server, vLLM). auto: detected from GET /v1/models.",
        env="DECISION_PORT_PROTOCOL", choices=("auto", "decide", "openai"),
    ),
    Setting("decision.port_model", "str", "",
            "The model to ask on that server. Blank: the server's default "
            "(decide) or the first one it lists (openai).",
            env="DECISION_PORT_MODEL"),
    Setting("decision.port_timeout", "int", 30,
            "Seconds to wait for one decision from the port.",
            env="DECISION_PORT_TIMEOUT"),
    # ---- tools (universal policy; each tool adds its own [tools.<name>]) --
    Setting("tools.strict", "bool", False,
            "Stop startup when any tool fails to load, instead of setting the "
            "broken tool (and whatever depends on it) aside. Tests and CI turn "
            "this on.",
            env="MYCELIUM_TOOLS_STRICT"),
    Setting("tools.disabled", "list", [],
            "Tools to keep switched off without deleting their folders, e.g. "
            "[\"screening\"]. A core tool cannot be disabled.",
            env="MYCELIUM_TOOLS_DISABLED"),
    # ---- nightly (cost controls) ----------------------------------------
    Setting("nightly.model_calls", "limit", UNLIMITED,
            "Most language-model calls one nightly run may make. Past it the run "
            "keeps ranking without model write-ups.",
            env="NIGHTLY_MODEL_CALLS", suggested=5000),
    Setting("nightly.llm_concurrency", "int", 32,
            "Opportunity-scoring calls in flight at once.",
            env="OPPORTUNITY_LLM_CONCURRENCY"),
    Setting("nightly.writeup_concurrency", "int", 32,
            "Paper and opportunity write-up calls in flight at once.",
            env="WRITEUP_LLM_CONCURRENCY"),
    Setting("nightly.rerank_concurrency", "int", 12,
            "Rerank calls in flight at once.", env="TYPESAFE_RERANK_CONCURRENCY"),
    Setting("nightly.cluster_writeup_budget", "int", 40,
            "Write-ups per theme per target per night.",
            env="CLUSTER_WRITEUP_BUDGET"),
    Setting("nightly.member_fit_llm_limit", "int", 10,
            "Model-written 'who is this for' lines per lab feed.",
            env="MEMBER_FIT_LLM_LIMIT"),
    Setting("nightly.knowledge_work_facets", "int", 200,
            "People's own papers read into the knowledge graph per night.",
            env="KNOWLEDGE_WORK_FACETS_NIGHTLY_CAP"),
    Setting("nightly.knowledge_field_lookups", "int", 200,
            "OpenAlex field lookups per night.",
            env="KNOWLEDGE_FIELD_LOOKUPS_NIGHTLY_CAP"),
    Setting("nightly.collab_slots", "int", 200,
            "Funding calls read for team requirements per night.",
            env="COLLAB_SLOTS_NIGHTLY_CAP"),
    Setting("nightly.ambient_extract_per_lab", "int", 200,
            "Conversations read per lab per day.",
            env="AMBIENT_EXTRACT_DAILY_CAP_PER_LAB"),
    Setting("nightly.ambient_extract_concurrency", "int", 8,
            "Conversation reads in flight at once.",
            env="AMBIENT_EXTRACT_CONCURRENCY"),
    Setting("nightly.ambient_explain", "int", 200,
            "Profile-change explanations written per night.",
            env="AMBIENT_EXPLAIN_NIGHTLY_CAP"),
)

BY_KEY: dict[str, Setting] = {s.key: s for s in SETTINGS}

SECTION_HELP = {
    "instance": "Which deployment profile this instance starts from.",
    "billing": "Subscriptions are a self-contained module: with mode = \"off\" "
               "nothing about plans, tiers or seats applies.",
    "limits": "Per-person and per-organization limits while billing is off. "
              "\"unlimited\" or a number; a number turns that one limit on.",
    "limits.tiers": "Per-tier limits, used only when billing.mode = "
                    "\"subscriptions\".",
    "signup": "Who can create an account, and whether email must be verified.",
    "email": "How mail leaves the instance. Keys and passwords stay in .env.",
    "features": "Optional features, all off unless switched on.",
    "decision": "The decision model that re-orders the head of each theme's "
                "slate: TypeSafe's hosted Jev, a model you serve on a port, or "
                "none.",
    "nightly": "Cost controls for the nightly run: how many model calls and how "
               "much parallelism it may use.",
    "llm": "The language model servers. The local endpoint lives in .env "
           "(LLM_BASE_URL, LLM_MODEL) and is the server named \"local\"; more "
           "servers are declared as [llm.providers.<name>] sections and chosen "
           "per component in [llm.routes]. Keys stay in .env.",
    "tools": "The modular tools under tools/. These keys govern all of them; each "
             "installed tool also reads its own [tools.<name>] section below.",
}


# --------------------------------------------------------------------------- #
# Profiles — only the keys that differ from the defaults
# --------------------------------------------------------------------------- #

PROFILES: dict[str, dict[str, Any]] = {
    # One person on their own machine: no limits, no sign-up, nothing to verify.
    "personal": {
        "signup.mode": "closed",
    },
    # A lab on its own computers: no limits, colleagues join by invite.
    "lab": {},
    # A department: still unlimited (the suggested numbers are in the file as
    # comments), invite-based, with tighter nightly parallelism.
    "department": {
        "nightly.llm_concurrency": 16,
        "nightly.writeup_concurrency": 16,
    },
    # A whole school or university: the hosted configuration — subscriptions on
    # with today's tier numbers, a shared access code, verified email via Resend.
    "institution": {
        "billing.mode": "subscriptions",
        "limits.lab_projects": 10,
        "limits.department_projects": 30,
        "signup.mode": "code",
        "signup.verify_email": True,
        "email.provider": "resend",
    },
}

PROFILE_HELP = {
    "personal": "Just you. No limits, no sign-up, no email needed.",
    "lab": "One lab. No limits; colleagues join through an invite.",
    "department": "Several labs. No limits by default; invite-based.",
    "institution": "A whole school. Subscriptions, tier limits, a shared "
                   "sign-up code and verified email.",
}


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def _coerce(setting: Setting, raw: Any, origin: str) -> Any:
    """Turn a TOML or env value into the setting's type, or raise ConfigError."""
    where = f"{setting.key} (from {origin})"
    kind = setting.kind
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise ConfigError(f"{where}: expected true or false, got {raw!r}.")
    if kind == "int":
        if isinstance(raw, bool):
            raise ConfigError(f"{where}: expected a whole number, got {raw!r}.")
        try:
            return int(str(raw).strip())
        except ValueError:
            raise ConfigError(
                f"{where}: expected a whole number, got {raw!r}."
            ) from None
    if kind == "limit":
        if raw is None:
            return UNLIMITED
        if isinstance(raw, bool):
            raise ConfigError(
                f"{where}: expected a number or \"unlimited\", got {raw!r}."
            )
        text = str(raw).strip().lower()
        if text in _UNLIMITED_WORDS or text == "":
            return UNLIMITED
        try:
            value = int(text)
        except ValueError:
            raise ConfigError(
                f"{where}: expected a number or \"unlimited\", got {raw!r}."
            ) from None
        if value < 0:
            raise ConfigError(f"{where}: a limit cannot be negative.")
        return value
    if kind == "choice":
        text = str(raw).strip().lower()
        if text not in setting.choices:
            raise ConfigError(
                f"{where}: {raw!r} is not one of {', '.join(setting.choices)}."
            )
        return text
    if kind == "list":
        if isinstance(raw, (list, tuple)):
            items = [str(item) for item in raw]
        else:
            items = str(raw).split(",")
        return [item.strip().lower() for item in items if item.strip()]
    return "" if raw is None else str(raw)


def _flatten(table: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for name, value in table.items():
        key = f"{prefix}{name}"
        if isinstance(value, Mapping):
            flat.update(_flatten(value, f"{key}."))
        else:
            flat[key] = value
    return flat


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


@dataclass
class Instance:
    """The resolved configuration: every key's value and the layer it came from."""

    values: dict[str, Any]
    sources: dict[str, str]
    profile: str
    path: Path | None
    warnings: list[str] = field(default_factory=list)
    #: Each installed tool's resolved ``[tools.<name>]`` section
    #: (:class:`tools._framework.config.ToolConfig`), keyed by tool name.
    tools: dict[str, Any] = field(default_factory=dict)
    #: The model servers (``[llm.providers.*]`` plus the synthesised
    #: ``local``) and the per-component routes (``[llm.routes]``).
    llm: LLMServers | None = None

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def problems(self, environ: Mapping[str, str] | None = None) -> list[str]:
        """Combinations that cannot work. Empty when the configuration is sound."""
        env = os.environ if environ is None else environ
        out: list[str] = []
        provider = self.values["email.provider"]
        if self.values["signup.mode"] == "domain":
            if not self.values["signup.allowed_domains"]:
                out.append(
                    "signup.mode = \"domain\" needs at least one entry in "
                    "signup.allowed_domains."
                )
            if provider == "none":
                out.append(
                    "signup.mode = \"domain\" proves an address by mailing it, so "
                    "it needs email.provider = \"resend\" or \"smtp\"."
                )
        if self.values["signup.verify_email"] and provider == "none":
            out.append(
                "signup.verify_email = true needs email.provider = \"resend\" or "
                "\"smtp\"; with no provider nobody can receive the code."
            )
        if self.values["signup.mode"] == "code" and not env.get(
            "SIGNUP_ACCESS_CODE", ""
        ).strip():
            out.append(
                "signup.mode = \"code\" needs SIGNUP_ACCESS_CODE set in .env."
            )
        if provider == "resend" and not env.get("RESEND_API_KEY", "").strip():
            out.append("email.provider = \"resend\" needs RESEND_API_KEY in .env.")
        if provider == "smtp" and not self.values["email.smtp_host"]:
            out.append("email.provider = \"smtp\" needs email.smtp_host.")
        if self.llm is not None:
            out.extend(self.llm.problems(env))
        return out


def config_path(root: Path, environ: Mapping[str, str]) -> Path | None:
    """Where ``mycelium.toml`` is read from; ``MYCELIUM_CONFIG=none`` reads none."""
    override = environ.get("MYCELIUM_CONFIG", "").strip()
    if override.lower() == "none":
        return None
    if override:
        return Path(override)
    return root / CONFIG_FILENAME


def read_file(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            return _flatten(tomllib.load(handle))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path.name} is not valid TOML: {exc}") from exc


# Old names that give way to an explicit mycelium.toml value. .env.example
# shipped RERANK_METHOD=typesafe to every deployment, so its presence says
# nothing about what the operator chose; a [decision] backend in the file does.
_LEGACY_BELOW_FILE = frozenset({"decision.backend"})


def _legacy_env(environ: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    """Old env names that still mean something, as {key: (raw, env_name)}.

    ``EMAIL_ENABLED=true`` predates ``EMAIL_PROVIDER`` and meant "send through
    Resend"; honour it so an existing deployment keeps mailing. The same for
    ``RERANK_METHOD``.
    """
    out: dict[str, tuple[str, str]] = {}
    # RERANK_METHOD predates [decision] backend: typesafe meant Jev, local meant
    # no decision model.
    if not environ.get("DECISION_BACKEND", "").strip():
        method = environ.get("RERANK_METHOD", "").strip().lower()
        if method:
            legacy = {"typesafe": "jev", "local": "off"}
            if method not in ("auto", "jev", "port", "off"):
                # An unknown old value never stopped a boot; it meant local.
                method = legacy.get(method, "off")
            out["decision.backend"] = (method, "RERANK_METHOD")
    if not environ.get("EMAIL_PROVIDER", "").strip():
        enabled = environ.get("EMAIL_ENABLED", "").strip().lower()
        if enabled in _TRUE:
            out["email.provider"] = ("resend", "EMAIL_ENABLED")
        elif enabled in _FALSE:
            out["email.provider"] = ("none", "EMAIL_ENABLED")
    return out


def resolve(
    root: Path,
    environ: Mapping[str, str] | None = None,
    *,
    file_values: Mapping[str, Any] | None = None,
) -> Instance:
    """Merge defaults → profile → ``mycelium.toml`` → environment.

    ``file_values`` replaces reading the file (the CLI uses it to preview an
    edit before writing it).
    """
    env = os.environ if environ is None else environ
    path = config_path(root, env)
    raw_file = dict(read_file(path) if file_values is None else file_values)

    raw_file, tool_file = _split_tool_keys(raw_file)
    raw_file, server_file, route_file = _split_llm_keys(raw_file)
    unknown = sorted(k for k in raw_file if k not in BY_KEY)
    if unknown:
        raise ConfigError(
            f"Unknown key(s) in {CONFIG_FILENAME}: {', '.join(unknown)}. "
            "Run `ops/mycelium config explain` for the full list."
        )

    # The profile decides the layer under the file, so resolve it first.
    profile_setting = BY_KEY["instance.profile"]
    profile, profile_source = DEFAULT_PROFILE, "default"
    if "instance.profile" in raw_file:
        profile = _coerce(profile_setting, raw_file["instance.profile"],
                          CONFIG_FILENAME)
        profile_source = CONFIG_FILENAME
    env_profile = env.get("MYCELIUM_PROFILE", "").strip()
    if env_profile:
        profile = _coerce(profile_setting, env_profile, "MYCELIUM_PROFILE")
        profile_source = "env:MYCELIUM_PROFILE"

    layer = PROFILES[profile]
    legacy = _legacy_env(env)
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for setting in SETTINGS:
        key = setting.key
        if key == "instance.profile":
            values[key], sources[key] = profile, profile_source
            continue
        value, source = setting.default, "default"
        if key in layer:
            value, source = layer[key], f"profile:{profile}"
        if key in raw_file:
            value = _coerce(setting, raw_file[key], CONFIG_FILENAME)
            source = CONFIG_FILENAME
        raw_env = env.get(setting.env, "") if setting.env else ""
        if setting.env and raw_env.strip() != "":
            value = _coerce(setting, raw_env, setting.env)
            source = f"env:{setting.env}"
        elif key in legacy and not (key in _LEGACY_BELOW_FILE and key in raw_file):
            raw, name = legacy[key]
            value, source = _coerce(setting, raw, name), f"env:{name}"
        values[key] = value
        sources[key] = source

    tools, warnings = _resolve_tool_sections(
        tool_file,
        {k: v for k, v in layer.items() if k.startswith("tools.")},
        env,
        values["tools.disabled"],
    )
    llm = resolve_llm(values, server_file, route_file, env)
    warnings.extend(llm.warnings)
    return Instance(values=values, sources=sources, profile=profile,
                    path=path if path and path.is_file() else None,
                    warnings=warnings, tools=tools, llm=llm)


# --------------------------------------------------------------------------- #
# Model servers — [llm.providers.<name>] and [llm.routes]
# --------------------------------------------------------------------------- #

#: Server kinds. Each is served by apps/core/llmkit; the OpenAI-shaped ones
#: (everything but anthropic, gemini and ollama) go through the shared
#: OpenAI-compatible client the components were tuned on.
LLM_KINDS = ("openai_compatible", "vllm", "llamacpp", "ollama", "openai",
             "anthropic", "gemini", "deepseek")
#: Kinds that speak the OpenAI chat-completions wire format.
LLM_OPENAI_KINDS = ("openai_compatible", "vllm", "llamacpp", "openai", "deepseek")
#: Kinds that are a public API by definition.
LLM_CLOUD_KINDS = ("openai", "anthropic", "gemini", "deepseek")
#: Kinds with no sensible default address: the host must say where it is.
LLM_URL_KINDS = ("openai_compatible", "vllm", "llamacpp", "ollama")
#: The key variable a hosted kind reads when the section names none.
LLM_DEFAULT_KEY_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
                       "gemini": "GEMINI_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
LLM_LOCATIONS = ("local", "remote", "cloud")
#: Public API hosts (suffix match) that make a server ``cloud``.
LLM_CLOUD_HOSTS = (
    "api.openai.com", "openai.azure.com", "api.anthropic.com",
    "googleapis.com", "api.deepseek.com", "openrouter.ai", "api.together.xyz",
    "api.together.ai", "api.groq.com", "api.mistral.ai", "api.fireworks.ai",
    "api.perplexity.ai", "api.x.ai", "api.cohere.com", "inference.ai.azure.com",
    "api-inference.huggingface.co", "router.huggingface.co",
)

#: Fields a ``[llm.providers.<name>]`` section may set, and their types.
LLM_SERVER_FIELDS: dict[str, str] = {
    "kind": "str", "base_url": "str", "api_key_env": "str", "model": "str",
    "label": "str", "enabled": "bool", "location": "str", "timeout": "float",
    "connect_timeout": "float", "context_window": "int", "reasoning": "str",
    "model_allow": "list", "model_deny": "list",
}
_REASONING_LEVELS = ("none", "low", "medium", "high")
_SERVER_PREFIX = "llm.providers."
_ROUTE_PREFIX = "llm.routes."

_LLM_EXAMPLE = [
    "",
    "# More model servers. \"local\" above is the endpoint in .env; declare",
    "# [llm.providers.local] only to change its label or location. A server",
    "# names the variable that holds its key; the key itself lives in .env.",
    "#",
    "# [llm.providers.claude]",
    "# kind = \"anthropic\"                # " + " | ".join(LLM_KINDS),
    "# api_key_env = \"ANTHROPIC_API_KEY\"",
    "# model = \"...\"                     # one the server lists (llm_check)",
    "# enabled = true                     # cloud also needs allow_cloud = true",
    "#",
    "# [llm.routes]                       # component = \"server\" or \"server:model\"",
    "# agent = \"claude\"",
]


@dataclass
class LLMServers:
    """The resolved model servers and routes. Holds key *names*, never keys."""

    servers: dict[str, dict[str, Any]]
    routes: dict[str, str]
    default: str
    allow_cloud: bool
    fallback: list[str]
    warnings: list[str] = field(default_factory=list)

    def callable(self, name: str) -> bool:
        """Whether ``name`` may be called: declared, enabled, cloud allowed."""
        server = self.servers.get(name)
        if server is None or not server["enabled"]:
            return False
        if server["location"] == "cloud" and not self.allow_cloud:
            # The synthesised local server is whatever .env already pointed
            # at; turning on the cloud switch must not be needed to keep an
            # existing install working.
            return bool(server.get("synthesized"))
        return True

    def problems(self, environ: Mapping[str, str]) -> list[str]:
        out: list[str] = []
        for name, server in self.servers.items():
            where = f"[llm.providers.{name}]"
            if server["kind"] not in LLM_KINDS:
                out.append(f"{where} kind = {server['kind']!r} is not one of "
                           f"{', '.join(LLM_KINDS)}.")
                continue
            if not server["enabled"]:
                continue
            if server["kind"] in LLM_URL_KINDS and not server["base_url"]:
                out.append(f"{where} kind = \"{server['kind']}\" needs base_url.")
            if (server["location"] == "cloud" and not self.allow_cloud
                    and not server.get("synthesized")):
                out.append(f"{where} is a cloud server but llm.allow_cloud = "
                           "false; it will not be called. Set llm.allow_cloud = "
                           "true or enabled = false.")
            key_env = server["api_key_env"]
            if (key_env and not server.get("synthesized")
                    and not str(environ.get(key_env, "")).strip()):
                out.append(f"{where} api_key_env = \"{key_env}\" is not set in "
                           ".env.")
            if not server["model"] and not server.get("synthesized"):
                out.append(f"{where} has no model. Pick one the server lists "
                           "(`manage.py llm_check`).")
        names = [("llm.default", self.default)]
        names += [(f"llm.routes.{c}", r.partition(":")[0])
                  for c, r in self.routes.items()]
        for key, name in names:
            server = self.servers.get(name)
            if server is None:
                out.append(f"{key} names {name!r}, which is not a declared "
                           f"server ({', '.join(sorted(self.servers))}).")
            elif not server["enabled"]:
                out.append(f"{key} names {name!r}, which is disabled.")
        for name in self.fallback:
            if name not in self.servers:
                out.append(f"llm.fallback names {name!r}, which is not a "
                           "declared server.")
        return out


def derive_location(kind: str, base_url: str) -> str:
    """``local``, ``remote`` or ``cloud``, from the kind and the address.

    Hosted kinds and known public API hosts are ``cloud``; loopback, private
    ranges, ``host.docker.internal`` and single-label names (a Compose
    service on this host) are ``local``; anything else is ``remote``.
    """
    import ipaddress
    from urllib.parse import urlsplit

    if kind in LLM_CLOUD_KINDS and not base_url:
        return "cloud"
    host = (urlsplit(base_url if "//" in base_url else f"//{base_url}")
            .hostname or "").lower().rstrip(".")
    if not host:
        return "cloud" if kind in LLM_CLOUD_KINDS else "local"
    if any(host == h or host.endswith("." + h) for h in LLM_CLOUD_HOSTS):
        return "cloud"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if ip.is_loopback or ip.is_private or ip.is_link_local:
            return "local"
        return "cloud" if kind in LLM_CLOUD_KINDS else "remote"
    if (host in ("localhost", "host.docker.internal") or "." not in host
            or host.endswith((".localhost", ".local", ".internal", ".lan",
                              ".home.arpa"))):
        return "local"
    return "cloud" if kind in LLM_CLOUD_KINDS else "remote"


def _split_llm_keys(flat: Mapping[str, Any]):
    """Separate ``llm.providers.<name>.<field>`` and ``llm.routes.<component>``."""
    rest: dict[str, Any] = {}
    servers: dict[str, dict[str, Any]] = {}
    routes: dict[str, Any] = {}
    for key, value in flat.items():
        if key.startswith(_SERVER_PREFIX):
            name, _, sub = key[len(_SERVER_PREFIX):].partition(".")
            if not sub:
                raise ConfigError(f"{key}: a server is a table, "
                                  f"[llm.providers.{name}].")
            servers.setdefault(name, {})[sub] = value
        elif key.startswith(_ROUTE_PREFIX):
            routes[key[len(_ROUTE_PREFIX):]] = value
        else:
            rest[key] = value
    return rest, servers, routes


def _server_value(name: str, sub: str, raw: Any) -> Any:
    where = f"llm.providers.{name}.{sub}"
    if sub in ("api_key", "key", "token", "password", "secret"):
        raise ConfigError(f"{where}: keys never go in {CONFIG_FILENAME}. Put the "
                          "key in .env and name its variable with api_key_env.")
    kind = LLM_SERVER_FIELDS.get(sub)
    if kind is None:
        raise ConfigError(f"{where}: unknown field. A server takes "
                          f"{', '.join(LLM_SERVER_FIELDS)}.")
    if kind == "float":
        try:
            if isinstance(raw, bool):
                raise ValueError
            return float(raw)
        except (TypeError, ValueError):
            raise ConfigError(f"{where}: expected a number, got {raw!r}.") from None
    if kind == "list":
        items = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
        return [str(item).strip() for item in items if str(item).strip()]
    value = _coerce(Setting(where, kind, None, ""), raw, CONFIG_FILENAME)
    if sub == "location" and value not in LLM_LOCATIONS:
        raise ConfigError(f"{where}: {raw!r} is not one of "
                          f"{', '.join(LLM_LOCATIONS)}.")
    if sub == "reasoning" and value not in _REASONING_LEVELS:
        raise ConfigError(f"{where}: {raw!r} is not one of "
                          f"{', '.join(_REASONING_LEVELS)}.")
    if sub == "kind":
        value = value.strip().lower()
    return value


def _env_float(environ: Mapping[str, str], name: str, default: float) -> float:
    try:
        return float(str(environ.get(name, "")).strip() or default)
    except ValueError:
        return default


def resolve_llm(values: Mapping[str, Any], server_file: Mapping[str, Mapping],
                route_file: Mapping[str, Any],
                environ: Mapping[str, str]) -> LLMServers:
    """The server table: the synthesised ``local`` plus every declared one.

    ``local`` is built from the ``LLM_*`` variables the backend has always read,
    so an install with no ``[llm.providers]`` resolves to exactly today's
    endpoint. A ``[llm.providers.local]`` section overrides it field by field.
    """
    servers: dict[str, dict[str, Any]] = {}
    for name in ["local", *[n for n in server_file if n != "local"]]:
        fields = {sub: _server_value(name, sub, raw)
                  for sub, raw in (server_file.get(name) or {}).items()}
        synthesized = name == "local" and "kind" not in fields and \
            "base_url" not in fields
        if name == "local":
            base = {
                "kind": "openai_compatible",
                "base_url": str(environ.get("LLM_BASE_URL", "")).strip()
                or "http://localhost:8001/v1",
                "api_key_env": "LLM_API_KEY",
                "model": str(environ.get("LLM_MODEL", "")).strip(),
                "label": "Local model",
                "timeout": _env_float(environ, "LLM_TIMEOUT", 60.0),
                "connect_timeout": _env_float(environ, "LLM_CONNECT_TIMEOUT", 5.0),
            }
            if not synthesized:
                # A declared local server is the host's own, not the .env one.
                base = {"label": "Local model"}
            fields = {**base, **fields}
        kind = str(fields.get("kind") or "openai_compatible")
        base_url = str(fields.get("base_url") or "")
        stated = fields.get("location")
        server = {
            "name": name,
            "kind": kind,
            "base_url": base_url,
            "api_key_env": fields.get("api_key_env")
            or LLM_DEFAULT_KEY_ENV.get(kind, ""),
            "model": str(fields.get("model") or ""),
            "label": str(fields.get("label") or name.replace("_", " ").title()),
            "label_stated": "label" in (server_file.get(name) or {}),
            "enabled": bool(fields.get("enabled", True)),
            "location": stated or derive_location(kind, base_url),
            "location_stated": bool(stated),
            "timeout": float(fields.get("timeout") or 60.0),
            "connect_timeout": float(fields.get("connect_timeout") or 5.0),
            "context_window": int(fields.get("context_window") or 0),
            "reasoning": fields.get("reasoning") or "",
            "model_allow": list(fields.get("model_allow") or []),
            "model_deny": list(fields.get("model_deny") or []),
            "synthesized": synthesized,
        }
        servers[name] = server
    routes = {}
    for component, raw in route_file.items():
        text = str(raw).strip()
        if not text or text.startswith(":"):
            raise ConfigError(f"llm.routes.{component}: expected \"server\" or "
                              f"\"server:model\", got {raw!r}.")
        routes[component] = text
    llm = LLMServers(
        servers=servers,
        routes=routes,
        default=str(values.get("llm.default") or "local").strip(),
        allow_cloud=bool(values.get("llm.allow_cloud")),
        fallback=list(values.get("llm.fallback") or []),
    )
    local = servers["local"]
    if local["synthesized"] and local["location"] == "cloud":
        llm.warnings.append(
            "The local server (LLM_BASE_URL) is a cloud endpoint: every "
            "component's text leaves this host. Declare it as its own server "
            "if that is not intended.")
    return llm


def llm_key_kind(key: str) -> str | None:
    """The value type of a dynamic ``llm.providers.*`` / ``llm.routes.*`` key."""
    if key.startswith(_ROUTE_PREFIX) and len(key) > len(_ROUTE_PREFIX):
        return "str"
    if key.startswith(_SERVER_PREFIX):
        _name, _, sub = key[len(_SERVER_PREFIX):].partition(".")
        return LLM_SERVER_FIELDS.get(sub)
    return None


def parse_llm_value(key: str, raw: str) -> Any:
    """A command-line string as the TOML value a dynamic llm key takes."""
    if key.startswith(_ROUTE_PREFIX):
        return str(raw).strip()
    name, _, sub = key[len(_SERVER_PREFIX):].partition(".")
    return _server_value(name, sub, raw)


# --------------------------------------------------------------------------- #
# Per-tool sections — delegated to tools/_framework/config.py
# --------------------------------------------------------------------------- #


def _tool_framework():
    """``tools._framework`` (config, discovery), or None if ``tools/`` is absent.

    The repository root is put on ``sys.path`` the same way settings.py does,
    so the host CLI, Django and the tests all see one tools directory.
    """
    root = Path(__file__).resolve().parents[3]
    if (root / "tools" / "_framework").is_dir() and str(root) not in sys.path:
        sys.path.append(str(root))
    try:
        from tools._framework import config, discovery
    except ImportError:
        return None
    return config, discovery


def _split_tool_keys(flat: Mapping[str, Any]):
    fw = _tool_framework()
    if fw is None:
        rest = {k: v for k, v in flat.items() if not k.startswith("tools.")
                or k in BY_KEY}
        return rest, {}
    return fw[0].split_tool_keys(flat)


def _resolve_tool_sections(file_values, profile_flat, environ, disabled):
    fw = _tool_framework()
    if fw is None:
        return {}, []
    config, discovery = fw
    _rest, profile_values = config.split_tool_keys(profile_flat)
    classes = [d.cls for d in discovery.discover().values() if d.cls is not None]
    return config.resolve_tools(
        classes,
        file_values=file_values,
        profile_values=profile_values,
        environ=environ,
        disabled=disabled,
    )


# --------------------------------------------------------------------------- #
# Rendering ``mycelium.toml``
# --------------------------------------------------------------------------- #


def _toml_value(value: Any) -> str:
    if value is UNLIMITED:
        return '"unlimited"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(f'"{item}"' for item in value) + "]"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _wrap(text: str, width: int = 78, prefix: str = "# ") -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        if line and len(prefix) + len(line) + 1 + len(word) > width:
            lines.append(prefix + line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    if line:
        lines.append(prefix + line)
    return lines


def render(profile: str, overrides: Mapping[str, Any] | None = None) -> str:
    """A complete, commented ``mycelium.toml`` for ``profile``.

    Every key is written with the value the profile gives it, so the file reads
    as the whole configuration rather than a diff. A limit that is unlimited
    carries its suggested number in a comment.
    """
    if profile not in PROFILES:
        raise ConfigError(f"Unknown profile {profile!r}.")
    overrides = dict(overrides or {})
    layer = {**PROFILES[profile], **overrides, "instance.profile": profile}
    out = [
        "# Mycelium instance configuration.",
        "#",
        "# Generated by `ops/mycelium config init`. Edit freely: every value here",
        "# overrides the profile it started from, and an environment variable of",
        "# the name shown overrides this file. Secrets (API keys, passwords, the",
        "# sign-up access code) belong in .env, never here.",
        "#",
        "# `ops/mycelium config show` prints what is in effect and why;",
        "# `ops/mycelium config validate` checks the combination works.",
        "",
    ]
    current, current_help = None, None
    for setting in SETTINGS:
        section = setting.section
        if section != current:
            if current == "llm":
                out.extend(_LLM_EXAMPLE)
            if current is not None:
                out.append("")
            help_key = "limits.tiers" if section.startswith("limits.tiers") else section
            if help_key != current_help:
                out.extend(_wrap(SECTION_HELP.get(help_key, "")))
                current_help = help_key
            out.append(f"[{section}]")
            current = section
        value = layer.get(setting.key, setting.default)
        if not section.startswith("limits.tiers"):
            out.extend(_wrap(setting.help))
        line = f"{setting.name} = {_toml_value(value)}"
        notes = []
        if setting.kind == "limit" and value is UNLIMITED and setting.suggested:
            notes.append(f"suggested: {setting.suggested}")
        if setting.env:
            notes.append(f"env {setting.env}")
        if setting.choices and setting.kind == "choice":
            notes.append(" | ".join(setting.choices))
        if notes:
            line = f"{line:<40} # {'; '.join(notes)}"
        out.append(line)
    out.extend(_render_tool_sections())
    out.append("")
    return "\n".join(out)


def _render_tool_sections() -> list[str]:
    """One ``[tools.<name>]`` section per installed tool.

    ``enabled`` is written as a value; every other key is written commented
    out at its default, so the file documents what can be set without pinning
    a tool's defaults into the operator's file.
    """
    fw = _tool_framework()
    if fw is None:
        return []
    out: list[str] = []
    for item in fw[1].discover().values():
        cls = item.cls
        if cls is None:
            continue
        out.append("")
        out.extend(_wrap(f"{cls.name}: {cls.summary}".strip()))
        out.append(f"[tools.{cls.name}]")
        out.append("enabled = true")
        for setting in cls.settings:
            if setting.secret:
                out.append(f"# {setting.key}: secret, set ${setting.env} in .env")
                continue
            value = setting.default
            text = (str(value) if isinstance(value, float)
                    else _toml_value(value))
            line = f"# {setting.key} = {text}"
            if setting.env:
                line = f"{line:<40} # env {setting.env}"
            out.append(line)
    return out
