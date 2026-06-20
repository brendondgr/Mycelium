from django.db import migrations
from pgvector.django import VectorExtension


class Migration(migrations.Migration):
    """Enable the pgvector extension on Postgres.

    Turning the extension on now (Phase 0) means embedding columns can be
    added later for relevance scoring (Month 2 / Week 7) without a disruptive
    mid-sprint migration. ``VectorExtension`` issues
    ``CREATE EXTENSION IF NOT EXISTS vector`` and is a no-op on non-PostgreSQL
    backends (e.g. SQLite during tests).
    """

    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        VectorExtension(),
    ]
