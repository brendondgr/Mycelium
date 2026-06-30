"""Natural-language statement synthesis: LLM seam + deterministic fallback."""

from apps.accounts.intake import AuthorProfileDraft, draft_statement


def _draft(**kwargs) -> AuthorProfileDraft:
    base = dict(
        display_name="Ada Lovelace",
        institution="Analytical Engine Institute",
        areas=["computational mathematics", "theory of computation"],
        keywords=["recursion", "algorithms"],
        evidence=[{"title": "Notes on the Analytical Engine"}],
    )
    base.update(kwargs)
    return AuthorProfileDraft(**base)


# -- deterministic fallback (no model) ----------------------------------------


def test_fallback_weaves_areas_keywords() -> None:
    # No `complete` seam and no configured model -> deterministic template.
    statement = draft_statement(_draft(), complete=lambda _prompt: None)
    assert statement
    assert "computational mathematics" in statement
    assert "recursion" in statement


def test_fallback_from_areas_only() -> None:
    draft = _draft(keywords=[], evidence=[])
    statement = draft_statement(draft, complete=lambda _prompt: None)
    assert "computational mathematics" in statement


def test_empty_draft_returns_empty_string() -> None:
    draft = AuthorProfileDraft(display_name="Nobody")  # no areas/keywords
    assert draft_statement(draft, complete=lambda _prompt: "anything") == ""


# -- the LLM seam -------------------------------------------------------------


def test_llm_text_is_used_when_present() -> None:
    seen: dict[str, str] = {}

    def fake_complete(prompt: str) -> str:
        seen["prompt"] = prompt
        return "I research quantum-safe cryptography and its deployment."

    statement = draft_statement(_draft(), complete=fake_complete)
    assert statement == "I research quantum-safe cryptography and its deployment."
    # The prompt carried the draft's signal so the model could ground its prose.
    assert "computational mathematics" in seen["prompt"]
    assert "Notes on the Analytical Engine" in seen["prompt"]


def test_blank_llm_answer_falls_back() -> None:
    statement = draft_statement(_draft(), complete=lambda _prompt: "   ")
    assert "computational mathematics" in statement


def test_llm_exception_falls_back() -> None:
    def boom(_prompt: str) -> str:
        raise RuntimeError("endpoint down")

    statement = draft_statement(_draft(), complete=boom)
    assert "computational mathematics" in statement


# -- shaping ------------------------------------------------------------------


def test_long_llm_text_is_truncated_on_a_word_boundary() -> None:
    long_text = "word " * 400  # ~2000 chars, far over the cap
    statement = draft_statement(_draft(), complete=lambda _p: long_text, max_chars=120)
    assert len(statement) <= 121  # 120 + the ellipsis
    assert statement.endswith("…")
    assert "word word" in statement
