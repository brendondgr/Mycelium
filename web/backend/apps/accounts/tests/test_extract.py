"""LLM-driven profile field extraction: structured output + fallback."""

import json

from apps.accounts.intake import extract_profile_fields

TEXT = (
    "Ada Lovelace, Analytical Engine Institute. Works: Notes on the Analytical "
    "Engine; On Recursion. Interests: computational mathematics."
)

LLM_JSON = json.dumps(
    {
        "statement": "I research computational mathematics and early computing.",
        "areas": ["computational mathematics", "theory of computation"],
        "keywords": ["recursion", "analytical engine"],
        "methods": ["formal proofs"],
        "skills": ["mechanical computation"],
    }
)


def test_llm_json_fills_every_field() -> None:
    fields = extract_profile_fields(TEXT, complete=lambda _p: LLM_JSON)
    assert fields["statement"].startswith("I research")
    assert "computational mathematics" in fields["areas"]
    assert "recursion" in fields["keywords"]
    assert fields["methods"] == ["formal proofs"]
    assert fields["skills"] == ["mechanical computation"]


def test_code_fenced_json_is_parsed() -> None:
    fenced = f"```json\n{LLM_JSON}\n```"
    fields = extract_profile_fields(TEXT, complete=lambda _p: fenced)
    assert "theory of computation" in fields["areas"]


def test_prompt_includes_the_text() -> None:
    seen: dict[str, str] = {}

    def fake(prompt: str) -> str:
        seen["p"] = prompt
        return LLM_JSON

    extract_profile_fields(TEXT, complete=fake)
    assert "Analytical Engine" in seen["p"]


def test_non_json_answer_uses_fallback() -> None:
    sentinel = {
        "statement": "fallback",
        "areas": ["fb"],
        "keywords": [],
        "methods": [],
        "skills": [],
    }
    fields = extract_profile_fields(
        TEXT, complete=lambda _p: "sorry, no json", fallback=lambda: sentinel
    )
    assert fields["statement"] == "fallback"
    assert fields["areas"] == ["fb"]


def test_llm_exception_uses_fallback() -> None:
    def boom(_p: str) -> str:
        raise RuntimeError("endpoint down")

    fields = extract_profile_fields(
        TEXT, complete=boom, fallback=lambda: {"areas": ["x"]}
    )
    # Fallback output is normalized to the full five-field shape.
    assert fields["areas"] == ["x"]
    assert fields["keywords"] == []
    assert fields["statement"] == ""


def test_empty_signal_llm_falls_back() -> None:
    empty_json = json.dumps({"statement": "", "areas": [], "keywords": []})
    fields = extract_profile_fields(
        TEXT, complete=lambda _p: empty_json, fallback=lambda: {"areas": ["fb"]}
    )
    assert fields["areas"] == ["fb"]


def test_no_fallback_returns_empty_shape() -> None:
    fields = extract_profile_fields("", complete=lambda _p: LLM_JSON)
    assert fields == {
        "statement": "",
        "areas": [],
        "keywords": [],
        "methods": [],
        "skills": [],
    }


def test_lists_are_coerced_and_deduped() -> None:
    messy = json.dumps(
        {
            "areas": ["AI", "ai", "  AI  ", 42, "Robotics"],
            "skills": "python",  # not a list -> []
        }
    )
    fields = extract_profile_fields(TEXT, complete=lambda _p: messy)
    assert fields["areas"] == ["AI", "42", "Robotics"]
    assert fields["skills"] == []
