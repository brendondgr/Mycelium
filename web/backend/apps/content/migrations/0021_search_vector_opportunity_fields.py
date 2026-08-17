# Re-issues the FTS trigger function from 0004 (plan Phase 9, open-collector
# migration). The open collector's ``mapping.py`` carries two identifying
# fields Pivot never did — a grant's funder-issued ``opportunity_number`` and
# a conference's ``acronym`` — and neither was searchable: a reader typing
# "PAR-25-144" or "SIGMOD" got no hit unless that exact string happened to
# also appear in the title/name. The trigger function hard-codes every
# metadata key it reads (0004's own docstring says so), so a new searchable
# key means re-issuing the function, not a schema change.
#
# Everything 0004 already indexed keeps working unchanged: this only widens
# the weight-C (auxiliary) clause by two more coalesced fields. Title (A) and
# abstract-family (B) are untouched.

from django.db import migrations

# Same shape as 0004's function, extended: ``aux_text`` gains
# ``opportunity_number`` (grants) and ``acronym`` (conferences) at weight C,
# alongside the existing sponsor/agency/venue/keywords/subjects/topics/
# location/country fields. Both new keys are absent on the content type that
# doesn't carry them, and ``concat_ws`` already skips absent values — the same
# graceful-degradation the original function relies on for every other
# type-specific field.
_CREATE_FUNCTION = r"""
CREATE OR REPLACE FUNCTION content_item_search_vector_refresh()
RETURNS trigger AS $$
DECLARE
    md jsonb := COALESCE(NEW.metadata, '{}'::jsonb);
    title_text text;
    body_text text;
    authors_text text := '';
    aux_text text;
BEGIN
    title_text := COALESCE(md->>'title', md->>'name', '');
    body_text := COALESCE(
        md->>'abstract', md->>'ai_summary', md->>'search_text',
        md->>'description', ''
    );
    IF jsonb_typeof(md->'authors') = 'array' THEN
        authors_text := COALESCE((
            SELECT string_agg(elem, ' ')
            FROM jsonb_array_elements_text(md->'authors') AS elem
        ), '');
    END IF;
    aux_text := concat_ws(' ',
        authors_text,
        md->>'sponsor', md->>'agency', md->>'venue',
        md->>'keywords', md->>'matched_subjects', md->>'matched_topics',
        md->>'location', md->>'country',
        md->>'opportunity_number', md->>'acronym'
    );
    NEW.search_vector :=
        setweight(to_tsvector('english', title_text), 'A') ||
        setweight(to_tsvector('english', body_text), 'B') ||
        setweight(to_tsvector('english', aux_text), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# The previous (0004) function body, restored on reverse — same weights, minus
# the two new aux fields.
_REVERT_FUNCTION = r"""
CREATE OR REPLACE FUNCTION content_item_search_vector_refresh()
RETURNS trigger AS $$
DECLARE
    md jsonb := COALESCE(NEW.metadata, '{}'::jsonb);
    title_text text;
    body_text text;
    authors_text text := '';
    aux_text text;
BEGIN
    title_text := COALESCE(md->>'title', md->>'name', '');
    body_text := COALESCE(
        md->>'abstract', md->>'ai_summary', md->>'search_text',
        md->>'description', ''
    );
    IF jsonb_typeof(md->'authors') = 'array' THEN
        authors_text := COALESCE((
            SELECT string_agg(elem, ' ')
            FROM jsonb_array_elements_text(md->'authors') AS elem
        ), '');
    END IF;
    aux_text := concat_ws(' ',
        authors_text,
        md->>'sponsor', md->>'agency', md->>'venue',
        md->>'keywords', md->>'matched_subjects', md->>'matched_topics',
        md->>'location', md->>'country'
    );
    NEW.search_vector :=
        setweight(to_tsvector('english', title_text), 'A') ||
        setweight(to_tsvector('english', body_text), 'B') ||
        setweight(to_tsvector('english', aux_text), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# Re-writing metadata onto itself fires the (now-replaced) update trigger, so
# every existing row's vector picks up the two new weight-C fields without
# duplicating the weight logic in Python.
_BACKFILL = "UPDATE content_contentitem SET metadata = metadata;"


def widen_fts(apps, schema_editor):
    """Install the widened function and backfill — PostgreSQL only."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_CREATE_FUNCTION)
    schema_editor.execute(_BACKFILL)


def narrow_fts(apps, schema_editor):
    """Reverse: restore 0004's function and re-backfill to match."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REVERT_FUNCTION)
    schema_editor.execute(_BACKFILL)


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0020_daily_briefing_carried_origin'),
    ]

    operations = [
        migrations.RunPython(widen_fts, narrow_fts),
    ]
