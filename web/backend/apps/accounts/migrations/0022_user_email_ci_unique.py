"""A database constraint behind the "emails are unique" rule.

``RegisterSerializer`` has always rejected a duplicate address, but a check made
in Python and a uniqueness guarantee are not the same thing: two sign-ups racing
each other both pass the query and both insert. Password reset now looks an
account up *by* its email, so a duplicate is no longer a cosmetic problem — it
decides whose account a reset link opens.

Expressed as raw SQL because the model being constrained is ``auth.User``, which
this app does not own. The index is on ``LOWER(email)`` to match the
case-insensitive lookups, and partial on ``email <> ''`` because Django leaves
the column blank rather than null for accounts created without one (fixtures,
``createsuperuser --noinput``, service accounts).
"""

from django.db import migrations

CREATE = """
CREATE UNIQUE INDEX IF NOT EXISTS accounts_user_email_ci_uniq
ON auth_user (LOWER(email))
WHERE email <> '';
"""

DROP = "DROP INDEX IF EXISTS accounts_user_email_ci_uniq;"


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0021_emailverification"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE, reverse_sql=DROP),
    ]
