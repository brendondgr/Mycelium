"""Ambient Plan 10, step 11: the labelled record as a dataset.

    manage.py export_ambient_dataset --salt <secret> --out <dir>

Writes JSON Lines, one file per table: the answers (``ValidationRecord``), the
verdicts on observations (``ObservationFeedback``), and the decisions with
their reasoning trace (``Finding``). Person ids are replaced by a salted hash,
the same person hashing the same way within one salt, so a dataset can be
joined on its own and on nothing else. The only text is Mylo's own —
summaries, topics and explanations. There is no message text to redact. A
correction a person typed is their own wording and is left out.

The research folder stores the manifest and aggregates, not these files.
"""

import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.ambient.models import Finding, ObservationFeedback, ValidationRecord


def _hasher(salt: str):
    def person(pk) -> str | None:
        if pk is None:
            return None
        return hashlib.sha256(f"{salt}:{pk}".encode()).hexdigest()[:16]

    return person


class Command(BaseCommand):
    help = "Export the ambient labelled record, with person ids hashed."

    def add_arguments(self, parser):
        parser.add_argument("--salt", required=True)
        parser.add_argument("--out", required=True)

    def handle(self, *args, **options):
        salt = options["salt"]
        if len(salt) < 8:
            raise CommandError("Use a salt of at least 8 characters.")
        person = _hasher(salt)
        out = Path(options["out"])
        out.mkdir(parents=True, exist_ok=True)
        counts = {}

        def write(name, rows):
            path = out / f"{name}.jsonl"
            n = 0
            with path.open("w") as handle:
                for row in rows:
                    handle.write(json.dumps(row, default=str) + "\n")
                    n += 1
            counts[name] = n

        write(
            "answers",
            (
                {
                    "id": r.pk,
                    "person": person(r.user_id),
                    "kind": r.kind,
                    "understanding_kind": r.understanding_kind,
                    "topic": r.topic,
                    "explanation": r.explanation,
                    "choices": [c.get("key") for c in (r.choices or [])],
                    "surface": r.surface,
                    "verdict": r.verdict,
                    "choice": (r.choice or "").split(":", 1)[0],
                    "renamed": bool(r.correction),
                    "finding": _without_ids(r.finding_snapshot),
                    "asked_at": r.asked_at,
                    "answered_at": r.answered_at,
                }
                for r in ValidationRecord.objects.order_by("pk").iterator()
            ),
        )
        write(
            "observation_verdicts",
            (
                {
                    "id": r.pk,
                    "observation": r.observation_id,
                    "person": person(getattr(r, "user_id", None)),
                    "verdict": r.verdict,
                    "channel": r.channel,
                    "created_at": r.created_at,
                }
                for r in ObservationFeedback.objects.order_by("pk").iterator()
            ),
        )
        write(
            "decisions",
            (
                {
                    "id": r.pk,
                    "person": person(r.user_id),
                    "topic": r.topic,
                    "understanding_kind": r.understanding_kind,
                    "relation": r.relation,
                    "visibility": r.visibility,
                    "outcome": r.outcome,
                    "reason": r.reason,
                    "facts": r.facts,
                    "influence": r.influence,
                    "budget": _without_ids(r.budget),
                    "trace": r.trace,
                    "observations": list(r.observation_ids or []),
                    "explanation": r.explanation,
                    "decided_at": r.decided_at,
                }
                for r in Finding.objects.order_by("pk").iterator()
            ),
        )
        (out / "counts.json").write_text(json.dumps(counts, indent=1))
        self.stdout.write(json.dumps(counts))


def _without_ids(value):
    """A snapshot with any person id dropped (snapshots are about findings,
    and a stray ``user`` key would undo the hashing)."""
    if not isinstance(value, dict):
        return value
    return {k: v for k, v in value.items() if k not in ("user", "user_id", "speaker")}
