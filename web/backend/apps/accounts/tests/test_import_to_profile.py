"""Phase C+E — draft -> intake agent -> confirm -> Profile.interests validates."""

import pytest
from django.contrib.auth.models import User
from rest_framework.exceptions import ValidationError

from apps.accounts.intake import AuthorProfileDraft, IntakeAgent
from apps.accounts.interests import validate_interests


def _draft() -> AuthorProfileDraft:
    return AuthorProfileDraft(
        display_name="Ada Lovelace",
        institution="Analytical Engine Institute",
        areas=["computational mathematics", "theory of computation"],
        keywords=["recursion"],
        external_ids={"openalex": "A5023888391"},
        evidence=[{"title": "Notes on the Analytical Engine"}],
    )


def _run(agent: IntakeAgent, state, answers: dict[str, str]):
    """Answer each pending question using the field key -> answer map."""
    while agent.question(state) is not None:
        field = state.pending[0]
        state = agent.answer(state, answers.get(field.key, "none"))
    return state


# -- agent mechanics ----------------------------------------------------------


def test_empty_draft_yields_form_only_flow() -> None:
    agent = IntakeAgent()
    state = agent.start()
    # Nothing seeded: the agent must ask, starting with research areas.
    assert agent.question(state) is not None
    assert state.pending[0].key == "areas"


def test_seeded_draft_skips_known_fields() -> None:
    agent = IntakeAgent()
    state = agent.start(draft=_draft())
    asked = [f.key for f in state.pending]
    # areas came from the draft, so the agent does not ask for them again.
    assert "areas" not in asked


def test_loop_is_capped() -> None:
    agent = IntakeAgent(max_turns=2)
    state = agent.start()
    assert len(state.pending) <= 2


def test_answers_fill_contract_fields() -> None:
    agent = IntakeAgent()
    state = agent.start(draft=_draft())
    state = _run(
        agent,
        state,
        {
            "eligibility": "postdoc",
            "funding_needs": "NSF",
            "exclusions": "none",
        },
    )
    assert state.done
    assert state.interests["eligibility"]["career_stage"] == "postdoc"
    assert state.interests["funding_needs"] == ["NSF"]


# -- the full path: draft -> confirm -> Profile -------------------------------


@pytest.mark.django_db
def test_import_draft_confirms_and_saves_valid_profile() -> None:
    agent = IntakeAgent()
    state = agent.start(draft=_draft())
    state = _run(agent, state, {"eligibility": "pi"})

    # Confirmation summary shown before save.
    summary = agent.summary(state)
    assert "computational mathematics" in summary

    interests = agent.finalize(state)  # validates against the contract

    user = User.objects.create_user(username="ada", password="pass-123")
    profile = user.profile
    profile.interests = interests
    profile.save()
    profile.refresh_from_db()

    # Stored interests still pass the gate, and carry the imported areas.
    validate_interests(profile.interests)
    assert "computational mathematics" in profile.interests["areas"]
    assert profile.interests["sources"]["openalex"] == "A5023888391"
    # The embedding hook (Phase F) wrote the canonical text on save.
    # Profile embeds statement + keywords only (areas are excluded).
    assert profile.embedding_text != ""


@pytest.mark.django_db
def test_finalize_rejects_a_profile_without_areas() -> None:
    agent = IntakeAgent()
    state = agent.start()  # nothing seeded
    # Skip every question, including areas -> contract has no areas.
    state = _run(agent, state, {})
    with pytest.raises(ValidationError):
        agent.finalize(state)
