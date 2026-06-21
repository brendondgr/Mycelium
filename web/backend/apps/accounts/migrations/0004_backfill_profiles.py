from django.conf import settings
from django.db import migrations


def create_missing_profiles(apps, schema_editor):
    """Ensure every existing user has a profile (briefing decision D5)."""
    Profile = apps.get_model("accounts", "Profile")
    User = apps.get_model(settings.AUTH_USER_MODEL)
    for user in User.objects.all():
        Profile.objects.get_or_create(user=user)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_profile"),
    ]

    operations = [
        migrations.RunPython(create_missing_profiles, migrations.RunPython.noop),
    ]
