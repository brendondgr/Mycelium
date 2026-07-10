"""Enable pg_trgm and index the title for the fuzzy (typo-tolerant) channel.

The trigram word-similarity channel (:mod:`apps.content.search`) recovers a query
with a typo by matching against the item title. ``TrigramExtension`` turns on
``pg_trgm`` (a no-op off PostgreSQL, like the pgvector extension); the GIN
trigram index on the title expression lets the ``%>`` word-similarity operator
use an index instead of scanning the whole corpus. Both are PostgreSQL-only.
"""

from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations

# Index the same title expression the search annotation builds, so the planner
# can use it for the ``%>`` word-similarity prefilter.
_CREATE_TRGM_INDEX = """
CREATE INDEX IF NOT EXISTS content_contentitem_title_trgm
    ON content_contentitem USING gin (
        (COALESCE(metadata->>'title', metadata->>'name', '')) gin_trgm_ops
    );
"""
_DROP_TRGM_INDEX = "DROP INDEX IF EXISTS content_contentitem_title_trgm;"


def create_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_CREATE_TRGM_INDEX)


def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_DROP_TRGM_INDEX)


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0004_contentitem_search_vector'),
    ]

    operations = [
        TrigramExtension(),
        migrations.RunPython(create_index, drop_index),
    ]
