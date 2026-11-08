"""Does this call need somebody the team does not have?

A grant that requires a co-investigator in environmental health is not a grant
the lab cannot win — it is a grant the lab cannot apply for **alone**, and the
difference between hearing that sixty days out and hearing it two days out is the
whole value of the alert. Recruiting a collaborator is weeks of work; noticing a
deadline is minutes.

The comparison is required expertise (extracted from the call's own text, plan
3.5) against what each candidate member **states** about themselves — their
declared research areas and skills. Two rules constrain it:

**Consented scope only.** Candidates are the people the target's own
recommendation layer may already name
(:func:`tools.recommendation.member_fit.scope_members`): a lab's members for a lab
project, a project's own members otherwise. This matcher introduces no new
visibility. In particular, it never reads the fellowship-eligibility fields —
citizenship and career stage are answers to a different question, given for a
different purpose, and naming a person for a grant on the strength of them would
be a disclosure nobody agreed to.

**Stated, not inferred.** Matching against what a person published would be more
accurate and is not the point. The report is going to say "Brendon is best suited
— his profile lists knowledge graphs", and that sentence has to be true of the
profile, because that is what the person controls and what they can correct.

A gap is only reported when the call actually states a requirement. Silence in the
source means no gap, not an unknown one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings

from apps.content.matchers.similarity import embed_many, similarity


@dataclass
class MemberMatch:
    """One person against one required expertise."""

    username: str
    display_name: str
    score: float
    #: The stated phrase that matched — what the report is allowed to cite.
    stated: str = ""


@dataclass
class TeamGap:
    """What one call requires, and who on the team has it."""

    content_id: str
    requirement: str
    #: Best first; only members above the threshold.
    covered_by: list[MemberMatch] = field(default_factory=list)

    @property
    def is_gap(self) -> bool:
        return not self.covered_by

    def as_dict(self) -> dict:
        return {
            "content_id": self.content_id,
            "requirement": self.requirement,
            "covered_by": [
                {
                    "username": match.username,
                    "name": match.display_name,
                    "stated": match.stated,
                    "score": round(match.score, 4),
                }
                for match in self.covered_by
            ],
            "is_gap": self.is_gap,
        }


def required_expertise(content) -> list[str]:
    """What a call says an applicant team must include. ``[]`` when it says none.

    Read from the call's required requirement slots once they have been read
    (``apps.collab.slots``: grounded in the call's own text, a role kept as a
    requirement nobody's profile can meet), and until then from the verified
    extraction (``ai_fields``) — never from the raw source: a requirement
    invented by a model is the one failure here that costs a team a grant they
    were eligible for.
    """
    from apps.collab.models import RequirementSlots

    row = RequirementSlots.objects.filter(
        content_id=getattr(content, "pk", None)
    ).first()
    if row is not None and row.status != RequirementSlots.Status.THIN:
        return [slot["text"] for slot in row.required][:4]
    metadata = getattr(content, "metadata", None) or {}
    fields = metadata.get("ai_fields")
    if not isinstance(fields, dict):
        return []
    raw = fields.get("required_expertise")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for entry in raw[:4]:
        text = " ".join(str(entry).split())
        if text:
            out.append(text)
    return out


def _stated_expertise(user) -> list[str]:
    """What this person says they do — declared areas and skills, nothing else."""
    interests = getattr(getattr(user, "profile", None), "interests", None) or {}
    out: list[str] = []
    for key in ("areas", "skills"):
        for entry in interests.get(key) or []:
            text = " ".join(str(entry).split())
            if text:
                out.append(text)
    return out[:40]


def team_gaps(
    target_filter: dict,
    contents,
    *,
    threshold: float | None = None,
) -> list[TeamGap]:
    """Every requirement in ``contents``, and who on the team covers it.

    ``target_filter`` is the usual ``{"target_lab": lab}`` / ``{"target_project":
    project}`` pair, passed straight to ``scope_members`` so the candidate set is
    exactly the one the rest of the product already names.
    """
    from tools.recommendation.member_fit import scope_members

    from apps.core.people import display_name

    floor = settings.PROJECT_ALERT_SLOT_THRESHOLD if threshold is None else threshold
    wanted = [(content, required_expertise(content)) for content in contents]
    wanted = [(content, needs) for content, needs in wanted if needs]
    if not wanted:
        return []

    members = scope_members(target_filter)
    stated = {user.get_username(): _stated_expertise(user) for user in members}
    names = {user.get_username(): display_name(user) for user in members}

    texts = [need for _content, needs in wanted for need in needs]
    texts += [phrase for phrases in stated.values() for phrase in phrases]
    vectors = embed_many(texts)

    gaps: list[TeamGap] = []
    for content, needs in wanted:
        for need in needs:
            matches: list[MemberMatch] = []
            for username, phrases in stated.items():
                best = max(
                    (
                        (similarity(need, phrase, vectors=vectors), phrase)
                        for phrase in phrases
                    ),
                    default=(0.0, ""),
                )
                if best[0] >= floor:
                    matches.append(
                        MemberMatch(
                            username=username,
                            display_name=names.get(username, username),
                            score=best[0],
                            stated=best[1],
                        )
                    )
            matches.sort(key=lambda match: -match.score)
            gaps.append(
                TeamGap(
                    content_id=str(content.id),
                    requirement=need,
                    covered_by=matches[:3],
                )
            )
    return gaps
