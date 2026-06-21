"""Helpers for the briefing's polymorphic relationships (§9).

Project scope, relevance target, subscription scope, and seat payer are each
modeled as several nullable typed foreign-key columns guarded by a database
check constraint that exactly one is set — preserving referential integrity and
indexability instead of reaching for ``GenericForeignKey``.
"""

from django.core.exceptions import ValidationError
from django.db.models import Q


def exactly_one(*fields: str) -> Q:
    """Return a check-constraint condition: exactly one of ``fields`` is set."""
    condition = Q()
    for chosen in fields:
        clause = Q(**{f"{chosen}__isnull": False})
        for other in fields:
            if other != chosen:
                clause &= Q(**{f"{other}__isnull": True})
        condition |= clause
    return condition


def validate_exactly_one(instance, *fields: str) -> None:
    """Raise ``ValidationError`` unless exactly one of ``fields`` is set.

    Mirrors :func:`exactly_one` at the application layer so admin and forms get
    a friendly error before the database constraint fires. Checks the FK
    ``*_id`` attribute to avoid extra queries.
    """
    set_count = sum(
        1 for field in fields if getattr(instance, f"{field}_id", None) is not None
    )
    if set_count != 1:
        raise ValidationError(
            f"Exactly one of [{', '.join(fields)}] must be set; got {set_count}."
        )
