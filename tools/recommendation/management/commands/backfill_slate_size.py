"""Record each stored slate's own length on the rows that belong to it.

Slates began carrying ``of`` — how many items a theme's shortlist actually held
— only after the feed cards started printing a denominator ("10th of 25"). Every
row written before that carries a rank with no total, and the card falls back to
the bare ordinal until the nightly run rewrites it. Rather than wait a night per
category, this recovers the number from the rows themselves: a theme's slate
length *is* the count of rows carrying that theme's id, per target and category.

Idempotent, and safe against a concurrent nightly run — it only ever writes a
count it just derived from the rows as they stand.
"""

from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from tools.recommendation.models import RelevanceScore
from tools.recommendation.slates import cluster_entries

#: The four fields a `RelevanceScore` can hang off; a row uses exactly one.
TARGET_FIELDS = (
    "target_user_id",
    "target_project_id",
    "target_lab_id",
    "target_department_id",
)


def _target_key(score: RelevanceScore) -> tuple:
    return tuple(getattr(score, field) for field in TARGET_FIELDS)


class Command(BaseCommand):
    help = (
        "Backfill the per-theme slate length on relevance rows written before "
        "slates recorded it, so feed cards can show '10th of 25'."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be written without touching any row.",
        )

    def handle(self, *args, **options) -> None:
        dry_run = bool(options["dry_run"])

        rows = list(
            RelevanceScore.objects.exclude(signals__cluster_slates=None).only(
                "signals", "content", *TARGET_FIELDS
            ).select_related("content")
        )

        # Pass one: the realised length of every (target, category, theme) slate.
        lengths: Counter = Counter()
        for score in rows:
            key = (_target_key(score), score.content.type)
            for cluster_id in cluster_entries(score.signals):
                lengths[(key, cluster_id)] += 1

        # Pass two: write each row's own themes back with their slate's length.
        changed: list[RelevanceScore] = []
        per_type: dict[str, int] = defaultdict(int)
        for score in rows:
            entries = cluster_entries(score.signals)
            if not entries:
                continue
            key = (_target_key(score), score.content.type)
            touched = False
            for cluster_id, entry in entries.items():
                if not isinstance(entry, dict):
                    continue
                total = lengths.get((key, cluster_id))
                if total and entry.get("of") != total:
                    entry["of"] = total
                    touched = True
            if not touched:
                continue
            score.signals["cluster_slates"] = entries
            ranked = [e for e in entries.values() if isinstance(e.get("rank"), int)]
            if ranked:
                best = min(ranked, key=lambda entry: entry["rank"])
                if isinstance(best.get("of"), int):
                    score.signals["top_rank_of"] = best["of"]
            changed.append(score)
            per_type[score.content.type] += 1

        if not dry_run and changed:
            RelevanceScore.objects.bulk_update(changed, ["signals"], batch_size=500)

        prefix = "Would update" if dry_run else "Updated"
        for content_type in sorted(per_type):
            self.stdout.write(f"{prefix} {per_type[content_type]} {content_type} rows")
        self.stdout.write(
            self.style.SUCCESS(f"{prefix} {len(changed)} rows in total")
        )
