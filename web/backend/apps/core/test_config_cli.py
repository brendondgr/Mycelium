"""The host-side ``ops/mycelium config`` CLI (``ops/setup/config_cli.py``)."""

import importlib.util
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def _cli():
    path = ROOT / "ops" / "setup" / "config_cli.py"
    spec = importlib.util.spec_from_file_location("mycelium_config_cli", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cli = _cli()
inst = cli.inst


def test_edit_keeps_comments_and_replaces_in_place():
    text = inst.render("lab")
    edited = cli.edit_file(text, {"limits.clusters": 4, "signup.mode": "open"}, set())
    flat = inst._flatten(tomllib.loads(edited))
    assert flat["limits.clusters"] == 4
    assert flat["signup.mode"] == "open"
    # The comment on the line survived, and nothing else moved.
    line = next(row for row in edited.splitlines() if row.startswith("clusters = 4"))
    assert "env LIMIT_CLUSTERS" in line
    assert len(edited.splitlines()) == len(text.splitlines())
    # The tier table's own `clusters` key was not touched.
    assert flat["limits.tiers.free.clusters"] == 3


def test_edit_appends_missing_keys_and_sections():
    edited = cli.edit_file('[instance]\nprofile = "lab"\n',
                           {"limits.clusters": 2, "instance.profile": "personal"},
                           set())
    flat = inst._flatten(tomllib.loads(edited))
    assert flat == {"instance.profile": "personal", "limits.clusters": 2}


def test_edit_removes_keys():
    text = '[limits]\nclusters = 4\nwatch_topics = 9\n'
    edited = cli.edit_file(text, {}, {"limits.clusters"})
    assert inst._flatten(tomllib.loads(edited)) == {"limits.watch_topics": 9}


def test_unlimited_round_trips():
    edited = cli.edit_file("[limits]\nclusters = 4\n", {"limits.clusters": None}, set())
    assert 'clusters = "unlimited"' in edited


def test_recommend_maps_people_to_profiles():
    assert cli.recommend(1, None, None, False, False)["profile"] == "personal"
    assert cli.recommend(12, None, None, False, False)["profile"] == "lab"
    assert cli.recommend(150, None, None, False, False)["profile"] == "department"
    assert cli.recommend(5000, None, None, False, False)["profile"] == "institution"
    assert cli.recommend(5000, "lab", None, False, False)["profile"] == "lab"


def test_recommend_without_mail_turns_verification_off():
    result = cli.recommend(5000, None, "none", False, False)
    assert result["set"]["email.provider"] == "none"
    assert result["set"]["signup.verify_email"] is False


def test_recommend_budget_for_paid_models():
    result = cli.recommend(10, None, None, True, False)
    assert result["set"]["nightly.model_calls"] == 1500
    # The recommendation must be something the loader accepts.
    file = {"instance.profile": result["profile"], **result["set"]}
    inst.resolve(Path("/nonexistent"), {}, file_values=file)


def test_dotenv_parsing(tmp_path):
    env = tmp_path / ".env"
    env.write_text('# c\nA=1\nB="two words"\n\nC=\n')
    assert cli.read_dotenv(env) == {"A": "1", "B": "two words", "C": ""}
