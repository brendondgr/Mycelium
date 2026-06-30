"""Phase G (integration) — the build chain's preconditions hold in order.

A smoke test that walks the chain so running things out of order fails loudly
(brief test 8): the contract gates writes (A before C/E), an empty draft yields a
form-only flow (C before E), and a null-embedding target is not scorable
(F before scoring).
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.exceptions import ValidationError

from apps.accounts.intake import IntakeAgent
from apps.accounts.interests import validate_interests
from apps.content.guards import (
    TargetNotScorable,
    ensure_embedding_ready,
    is_scorable,
)


def test_import_refuses_an_unvalidated_contract() -> None:
    # A before C/E: writing interests without going through the contract fails.
    with pytest.raises(ValidationError):
        validate_interests({"skills": ["Python"]})  # missing required areas


def test_empty_draft_yields_a_form_only_flow() -> None:
    # C before E: with no seed draft, the agent falls back to the question form.
    agent = IntakeAgent()
    state = agent.start()
    assert agent.question(state) is not None
    assert state.pending[0].key == "areas"


@pytest.mark.django_db
def test_scoring_refuses_a_null_embedding_target() -> None:
    # F before scoring: a fresh profile has no embedding and is not scorable.
    user = User.objects.create_user(username="u", password="p")
    profile = user.profile
    assert profile.embedding is None
    assert is_scorable(profile) is False
    with pytest.raises(TargetNotScorable):
        ensure_embedding_ready(profile)


def test_scoring_allows_a_target_with_an_embedding() -> None:
    class _Target:
        embedding = [0.1, 0.2, 0.3]

    assert ensure_embedding_ready(_Target()) is not None
