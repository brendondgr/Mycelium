"""Does this item unblock the project?

A project's state names what is standing in its way — "no labeled evaluation
set", "single unblinded rater", "no external baseline". A précis names what an
outside researcher could concretely take from a paper: a dataset, a protocol, a
baseline, a negative result (:class:`~tools.recommendation.models.ItemComprehension`'s
``reusable``).

Matching one against the other is the highest-value thing in this package,
because the answer is directly actionable in a way "this is relevant" never is.
It is also the cheapest, because ``reusable`` was written to be exactly this: a
statement of what is on offer, not a summary of the paper.

Compared against ``reusable`` alone, deliberately. The whole abstract would match
a blocker about evaluation sets for any paper that evaluates anything, which is
all of them.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from tools.delivery.matchers.similarity import embed_many, similarity


@dataclass
class BlockerMatch:
    """One item offering something one blocker needs."""

    content_id: str
    blocker_id: str
    blocker_text: str
    score: float
    #: What the item says is reusable — the sentence the report quotes.
    offer: str = ""

    def fires(self, threshold: float | None = None) -> bool:
        floor = (
            settings.PROJECT_ALERT_BLOCKER_THRESHOLD if threshold is None else threshold
        )
        return self.score >= floor

    def as_dict(self) -> dict:
        return {
            "content_id": self.content_id,
            "blocker_id": self.blocker_id,
            "blocker_text": self.blocker_text,
            "score": round(self.score, 4),
            "offer": self.offer,
        }


def blocker_rows(
    project, precis_by_content: dict, *, closed: tuple[str, ...] = ()
) -> list[BlockerMatch]:
    """Every (item, blocker) pair worth a number, strongest first.

    Empty when the project lists no blockers — which is a real state and not a
    failure, though it is usually a project that has not been asked.

    ``closed`` are the topics of blockers a development says have closed
    (ambient Plan 05): a stated blocker one of them names is left out, so
    "this unblocks you" stops firing for something already unblocked. The
    stated text itself is untouched — changing it is Plan 08's proposal.
    """
    from tools.delivery.matchers.developments import any_names

    slow = getattr(getattr(project, "state", None), "slow", None) or {}
    blockers = [
        row
        for row in (slow.get("blockers") or [])
        if str(row.get("text") or "").strip()
        and not any_names(closed, str(row.get("text") or ""))
    ]
    if not blockers:
        return []

    offers = {
        str(content_id): str(getattr(precis, "reusable", "") or "").strip()
        for content_id, precis in precis_by_content.items()
    }
    offers = {key: value for key, value in offers.items() if value}
    if not offers:
        return []

    vectors = embed_many([row["text"] for row in blockers] + list(offers.values()))

    rows = [
        BlockerMatch(
            content_id=content_id,
            blocker_id=blocker.get("id", ""),
            blocker_text=blocker["text"],
            score=similarity(blocker["text"], offer, vectors=vectors),
            offer=offer,
        )
        for content_id, offer in offers.items()
        for blocker in blockers
    ]
    rows.sort(key=lambda row: -row.score)
    return rows
