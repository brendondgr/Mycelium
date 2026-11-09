"""The instance configuration layer (``config/instance.py``).

Pure: every test hands ``resolve`` its own environment and file values, so the
developer's own ``mycelium.toml`` and ``.env`` never leak in.
"""

from pathlib import Path

import pytest

from config import instance as I

NOWHERE = Path("/nonexistent-mycelium-root")
REPO_ROOT = Path(__file__).resolve().parents[4]


def resolve(env=None, file=None):
    return I.resolve(NOWHERE, env or {}, file_values=file or {})


def test_default_profile_is_lab_with_no_limits_and_no_billing():
    cfg = resolve()
    assert cfg.profile == "lab"
    assert cfg["billing.mode"] == "off"
    assert cfg["signup.mode"] == "invite"
    assert cfg["signup.verify_email"] is False
    for key in ("clusters", "watch_topics", "personal_projects", "lab_projects",
                "department_projects", "lab_members", "lab_leads"):
        assert cfg[f"limits.{key}"] is I.UNLIMITED
    assert cfg.sources["billing.mode"] == "default"


def test_institution_profile_reproduces_the_hosted_configuration():
    cfg = resolve(file={"instance.profile": "institution"})
    assert cfg["billing.mode"] == "subscriptions"
    assert cfg["signup.mode"] == "code"
    assert cfg["signup.verify_email"] is True
    assert cfg["email.provider"] == "resend"
    assert cfg["billing.signup_tier"] == "spore"
    assert cfg["limits.tiers.free.clusters"] == 3
    assert cfg["limits.tiers.free.topics_per_cluster"] == 2
    assert cfg["limits.tiers.spore.watch_topics"] == 20
    assert cfg["limits.tiers.lab.members"] == 15
    assert cfg["limits.tiers.canopy.members"] is I.UNLIMITED
    assert cfg["limits.lab_projects"] == 10
    assert cfg["limits.department_projects"] == 30
    assert cfg.sources["billing.mode"] == "profile:institution"


def test_layers_override_in_order_default_profile_file_env():
    file = {"instance.profile": "institution", "signup.mode": "invite"}
    cfg = resolve(file=file)
    assert cfg["signup.mode"] == "invite"
    assert cfg.sources["signup.mode"] == I.CONFIG_FILENAME

    cfg = resolve(env={"SIGNUP_MODE": "open"}, file=file)
    assert cfg["signup.mode"] == "open"
    assert cfg.sources["signup.mode"] == "env:SIGNUP_MODE"


def test_env_profile_beats_file_profile():
    cfg = resolve(env={"MYCELIUM_PROFILE": "personal"},
                  file={"instance.profile": "institution"})
    assert cfg.profile == "personal"
    assert cfg["signup.mode"] == "closed"


def test_blank_env_value_does_not_override():
    cfg = resolve(env={"SIGNUP_MODE": "  "}, file={"signup.mode": "open"})
    assert cfg["signup.mode"] == "open"


@pytest.mark.parametrize("raw", ["unlimited", "none", "", None])
def test_limit_accepts_unlimited_spellings(raw):
    file = {} if raw is None else {"limits.clusters": raw}
    assert resolve(file=file)["limits.clusters"] is I.UNLIMITED


def test_limit_number_turns_the_limit_on():
    assert resolve(file={"limits.clusters": 4})["limits.clusters"] == 4
    assert resolve(env={"LIMIT_CLUSTERS": "7"})["limits.clusters"] == 7


@pytest.mark.parametrize(
    "file",
    [
        {"limits.clusters": -1.5},
        {"limits.clusters": "lots"},
        {"limits.clusters": True},
        {"signup.mode": "sometimes"},
        {"features.ambient": "maybe"},
        {"nightly.llm_concurrency": "fast"},
        {"limits.cluster": 3},  # typo: unknown key
    ],
)
def test_bad_values_fail_naming_the_key(file):
    with pytest.raises(I.ConfigError) as exc:
        resolve(file=file)
    assert list(file)[0].split(".")[0] in str(exc.value)


def test_legacy_email_enabled_means_resend():
    cfg = resolve(env={"EMAIL_ENABLED": "true"})
    assert cfg["email.provider"] == "resend"
    assert cfg.sources["email.provider"] == "env:EMAIL_ENABLED"
    # The new name wins over the old one.
    cfg = resolve(env={"EMAIL_ENABLED": "true", "EMAIL_PROVIDER": "smtp"})
    assert cfg["email.provider"] == "smtp"


@pytest.mark.parametrize(
    "old,new",
    [("typesafe", "jev"), ("local", "off"), ("port", "port"), ("banana", "off")],
)
def test_legacy_rerank_method_maps_to_decision_backend(old, new):
    cfg = resolve(env={"RERANK_METHOD": old})
    assert cfg["decision.backend"] == new
    assert cfg.sources["decision.backend"] == "env:RERANK_METHOD"
    # The new name wins over the old one.
    cfg = resolve(env={"RERANK_METHOD": "typesafe", "DECISION_BACKEND": "port"})
    assert cfg["decision.backend"] == "port"


def test_decision_backend_defaults_to_auto():
    assert resolve()["decision.backend"] == "auto"


def test_list_values_from_file_and_env():
    assert resolve(file={"signup.allowed_domains": ["FSU.edu", " x.org "]})[
        "signup.allowed_domains"
    ] == ["fsu.edu", "x.org"]
    assert resolve(env={"SIGNUP_ALLOWED_DOMAINS": "a.edu, b.edu"})[
        "signup.allowed_domains"
    ] == ["a.edu", "b.edu"]


def test_problems_catch_combinations_that_cannot_work():
    assert resolve().problems({}) == []

    cfg = resolve(file={"signup.mode": "domain"})
    problems = " ".join(cfg.problems({}))
    assert "allowed_domains" in problems and "email.provider" in problems

    cfg = resolve(file={"signup.verify_email": True})
    assert any("verify_email" in p for p in cfg.problems({}))

    cfg = resolve(file={"signup.mode": "code"})
    assert any("SIGNUP_ACCESS_CODE" in p for p in cfg.problems({}))
    assert cfg.problems({"SIGNUP_ACCESS_CODE": "abc"}) == []


def test_every_profile_renders_to_a_file_that_resolves_back():
    import tomllib

    for profile in I.PROFILE_NAMES:
        text = I.render(profile)
        flat = I._flatten(tomllib.loads(text))
        cfg = resolve(file=flat)
        expected = resolve(env={"MYCELIUM_PROFILE": profile})
        assert cfg.values == expected.values, profile


def test_committed_example_matches_the_schema():
    example = REPO_ROOT / "mycelium.example.toml"
    assert example.read_text() == I.render(I.DEFAULT_PROFILE), (
        "mycelium.example.toml is stale: regenerate it with "
        "`ops/mycelium config init --profile lab --output mycelium.example.toml`"
    )


def test_config_file_can_be_switched_off():
    assert I.config_path(NOWHERE, {"MYCELIUM_CONFIG": "none"}) is None
    assert I.config_path(NOWHERE, {}) == NOWHERE / I.CONFIG_FILENAME


# --------------------------------------------------------------------------- #
# Model servers: [llm], [llm.providers.<name>], [llm.routes]
# --------------------------------------------------------------------------- #

LOCAL_ENV = {"LLM_BASE_URL": "http://host.docker.internal:4000/v1",
             "LLM_MODEL": "qwen", "LLM_API_KEY": "secret-local-key"}


def test_no_provider_section_resolves_exactly_the_env_endpoint():
    cfg = resolve(env=LOCAL_ENV)
    assert list(cfg.llm.servers) == ["local"]
    local = cfg.llm.servers["local"]
    assert local["base_url"] == LOCAL_ENV["LLM_BASE_URL"]
    assert local["model"] == "qwen"
    assert local["kind"] == "openai_compatible"
    assert local["location"] == "local"
    assert local["synthesized"] is True
    assert cfg.llm.default == "local" and cfg.llm.routes == {}
    assert cfg.llm.allow_cloud is False and cfg.llm.fallback == []
    assert cfg.llm.callable("local")
    assert cfg.problems(LOCAL_ENV) == []
    # The key's variable is named; its value is nowhere in the table.
    assert "secret-local-key" not in repr(cfg.llm)


def test_declared_local_overrides_label_and_keeps_the_env_endpoint():
    cfg = resolve(env=LOCAL_ENV, file={"llm.providers.local.label": "Lab GPU",
                                       "llm.providers.local.location": "remote"})
    local = cfg.llm.servers["local"]
    assert local["label"] == "Lab GPU" and local["location"] == "remote"
    assert local["base_url"] == LOCAL_ENV["LLM_BASE_URL"] and local["synthesized"]


def test_a_cloud_server_and_a_route():
    file = {"llm.providers.claude.kind": "anthropic",
            "llm.providers.claude.model": "claude-x",
            "llm.routes.agent": "claude",
            "llm.routes.intake.clusters": "local:other-model",
            "llm.allow_cloud": True}
    env = {**LOCAL_ENV, "ANTHROPIC_API_KEY": "k"}
    cfg = resolve(env=env, file=file)
    claude = cfg.llm.servers["claude"]
    assert claude["location"] == "cloud"
    assert claude["api_key_env"] == "ANTHROPIC_API_KEY"
    assert cfg.llm.routes == {"agent": "claude", "intake.clusters": "local:other-model"}
    assert cfg.llm.callable("claude")
    assert cfg.problems(env) == []


@pytest.mark.parametrize(
    "file,needle",
    [
        ({"llm.providers.x.kind": "banana", "llm.providers.x.model": "m"},
         "kind = 'banana'"),
        ({"llm.providers.x.kind": "vllm", "llm.providers.x.model": "m"},
         "needs base_url"),
        ({"llm.providers.x.kind": "anthropic", "llm.providers.x.model": "m",
          "llm.allow_cloud": True, "llm.providers.x.api_key_env": "NOPE_KEY"},
         "NOPE_KEY"),
        ({"llm.routes.agent": "ghost"}, "llm.routes.agent names 'ghost'"),
        ({"llm.providers.x.kind": "vllm", "llm.providers.x.base_url": "http://g:1",
          "llm.providers.x.model": "m", "llm.providers.x.enabled": False,
          "llm.routes.agent": "x"}, "which is disabled"),
        ({"llm.providers.x.kind": "openai", "llm.providers.x.model": "m",
          "llm.providers.x.api_key_env": "LLM_MODEL"}, "llm.allow_cloud = false"),
        ({"llm.default": "ghost"}, "llm.default names 'ghost'"),
        ({"llm.fallback": ["ghost"]}, "llm.fallback names 'ghost'"),
    ],
)
def test_each_bad_server_configuration_is_reported_by_name(file, needle):
    cfg = resolve(env=LOCAL_ENV, file=file)
    problems = " ".join(cfg.problems(LOCAL_ENV))
    assert needle in problems, problems


@pytest.mark.parametrize(
    "file",
    [
        {"llm.providers.x.api_key": "sk-123"},  # keys never go in the file
        {"llm.providers.x.colour": "blue"},  # unknown field
        {"llm.providers.x.location": "moon"},
        {"llm.providers.x.timeout": "slow"},
        {"llm.routes.agent": ""},
    ],
)
def test_bad_server_fields_fail_naming_the_key(file):
    with pytest.raises(I.ConfigError) as exc:
        resolve(env=LOCAL_ENV, file=file)
    assert "llm." in str(exc.value)
    assert "sk-123" not in str(exc.value)


def test_a_cloud_server_is_not_callable_until_allowed():
    file = {"llm.providers.g.kind": "gemini", "llm.providers.g.model": "m"}
    assert not resolve(env=LOCAL_ENV, file=file).llm.callable("g")
    file["llm.allow_cloud"] = True
    assert resolve(env=LOCAL_ENV, file=file).llm.callable("g")


def test_a_cloud_env_endpoint_keeps_working_but_is_named():
    env = {**LOCAL_ENV, "LLM_BASE_URL": "https://api.openai.com/v1"}
    cfg = resolve(env=env)
    assert cfg.llm.servers["local"]["location"] == "cloud"
    assert cfg.llm.callable("local")  # an existing install is not broken
    assert any("cloud endpoint" in w for w in cfg.warnings)


@pytest.mark.parametrize(
    "kind,url,location",
    [
        ("openai_compatible", "http://localhost:8000/v1", "local"),
        ("openai_compatible", "http://127.0.0.1:8000", "local"),
        ("openai_compatible", "http://host.docker.internal:4000/v1", "local"),
        ("openai_compatible", "http://llm-tunnel:9090/v1", "local"),
        ("vllm", "http://10.0.0.4:8000/v1", "local"),
        ("vllm", "http://192.168.1.20:8000/v1", "local"),
        ("vllm", "https://gpu.example.edu/v1", "remote"),
        ("openai_compatible", "https://openrouter.ai/api/v1", "cloud"),
        ("openai_compatible", "https://x.openai.azure.com/openai/v1", "cloud"),
        ("anthropic", "", "cloud"),
        ("gemini", "", "cloud"),
        ("deepseek", "https://api.deepseek.com", "cloud"),
    ],
)
def test_location_is_derived(kind, url, location):
    assert I.derive_location(kind, url) == location
