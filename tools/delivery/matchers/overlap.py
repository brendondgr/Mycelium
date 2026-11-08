"""Does this paper threaten what the project claims is new?

The most valuable thing a research feed can tell someone is not "here is a
relevant paper". It is "someone has published the thing you were going to
publish" — and the second most valuable is "no, they have not, and here is
precisely where you still differ".

The comparison is narrow on purpose. A paper's **headline claim**
(:class:`~tools.recommendation.models.ItemComprehension`'s ``claim``) against the
project's **claimed contribution**, and the paper's method-and-setting against the
project's method-and-data. Those two, not the whole abstract against the whole
project, because everything in a reader's feed is already about their topic —
topical similarity carries no information at this point in the pipeline, and using
it would flag the entire feed.

Raw cosine, never RRF (plan 3.2): nothing is being ranked here, and a rank fusion
cannot answer "are these two sentences saying the same thing".

The threshold ships unmeasured and the feature ships off (``PROJECT_ALERTS_ENABLED``).
A similarity threshold set by taste fires constantly or never, and both teach a
reader to stop opening the report.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from tools.delivery.matchers.similarity import embed_many, similarity


@dataclass
class OverlapVerdict:
    """How close one item is to a project's claim, and on which axis."""

    content_id: str
    claim_similarity: float = 0.0
    approach_similarity: float = 0.0
    #: What the project still has that the item does not — the "where you still
    #: differ" line. Deterministic: the project's planned components and data the
    #: item's précis never mentions.
    differences: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.differences is None:
            self.differences = []

    @property
    def score(self) -> float:
        """The axis that fires. The claim dominates; the approach corroborates.

        A paper making the same claim by a different route is the threat; one
        using the same method to answer a different question is a neighbour, and
        a report that called it a threat would be crying wolf.
        """
        return max(self.claim_similarity, 0.6 * self.approach_similarity)

    def fires(self, threshold: float | None = None) -> bool:
        floor = (
            settings.PROJECT_ALERT_OVERLAP_THRESHOLD if threshold is None else threshold
        )
        return self.score >= floor

    def as_dict(self) -> dict:
        return {
            "content_id": self.content_id,
            "claim_similarity": round(self.claim_similarity, 4),
            "approach_similarity": round(self.approach_similarity, 4),
            "differences": list(self.differences),
        }


def _approach(precis) -> str:
    parts = [getattr(precis, "method", ""), getattr(precis, "setting", "")]
    return " ".join(part for part in parts if part)


def _project_approach(slow: dict, dropped: tuple[str, ...] = ()) -> str:
    from tools.delivery.matchers.developments import any_names

    methods = [m for m in (slow.get("method") or []) if not any_names(dropped, str(m))]
    parts = methods + list(slow.get("data") or [])
    return " ".join(parts)


def _differences(slow: dict, precis) -> list[str]:
    """What the project still has that this item's précis does not mention.

    Deterministic and deliberately literal — a token check, not a judgement. The
    model writes the sentence; this decides what the sentence is allowed to be
    about, so that "where you still differ" cannot become a comforting invention.
    """
    haystack = " ".join(
        filter(
            None,
            (
                getattr(precis, "problem", ""),
                getattr(precis, "method", ""),
                getattr(precis, "setting", ""),
                getattr(precis, "claim", ""),
                getattr(precis, "reusable", ""),
            ),
        )
    ).casefold()
    out: list[str] = []
    for candidate in list(slow.get("planned_components") or []) + list(
        slow.get("data") or []
    ):
        text = str(candidate).strip()
        if text and text.casefold() not in haystack:
            out.append(text)
    return out[:6]


def overlap_rows(
    project, precis_by_content: dict, *, dropped_methods: tuple[str, ...] = ()
) -> list[OverlapVerdict]:
    """Compare every précis against one project's claimed contribution.

    ``precis_by_content`` is ``{content_id: ItemComprehension}``. Returns a
    verdict per item, including the ones well below any threshold: the caller
    decides what fires, and the numbers are worth having for calibration.

    An empty list when the project has not said what it claims — which is the
    honest answer, and the reason the state panel exists.

    ``dropped_methods`` are methods a development says the project dropped
    (ambient Plan 05): a stated method one of them names no longer counts
    toward the approach compared, so a paper using an abandoned method stops
    reading as a threat. The stated field itself is untouched.
    """
    slow = getattr(getattr(project, "state", None), "slow", None) or {}
    contribution = str(slow.get("claimed_contribution") or "").strip()
    approach = _project_approach(slow, dropped_methods)
    if not contribution and not approach:
        return []

    texts = [contribution, approach]
    for precis in precis_by_content.values():
        texts.append(getattr(precis, "claim", ""))
        texts.append(_approach(precis))
    vectors = embed_many(texts)

    rows: list[OverlapVerdict] = []
    for content_id, precis in precis_by_content.items():
        rows.append(
            OverlapVerdict(
                content_id=str(content_id),
                claim_similarity=similarity(
                    contribution, getattr(precis, "claim", ""), vectors=vectors
                ),
                approach_similarity=similarity(
                    approach, _approach(precis), vectors=vectors
                ),
                differences=_differences(slow, precis),
            )
        )
    rows.sort(key=lambda row: -row.score)
    return rows
