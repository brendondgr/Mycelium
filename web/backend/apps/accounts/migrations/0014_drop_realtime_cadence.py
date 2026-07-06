# Generated for removal of the real-time watch cadence.

from django.db import migrations, models


def realtime_to_weekly(apps, schema_editor):
    """Move any existing real-time watches to weekly before the choice is dropped."""
    for model_name in ("WatchPreference", "LabWatchPreference"):
        Model = apps.get_model("accounts", model_name)
        Model.objects.filter(cadence="realtime").update(cadence="weekly")


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_labwatchpreference'),
    ]

    operations = [
        migrations.RunPython(realtime_to_weekly, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='watchpreference',
            name='cadence',
            field=models.CharField(choices=[('daily', 'Daily'), ('weekly', 'Weekly')], default='weekly', max_length=20),
        ),
        migrations.AlterField(
            model_name='labwatchpreference',
            name='cadence',
            field=models.CharField(choices=[('daily', 'Daily'), ('weekly', 'Weekly')], default='weekly', max_length=20),
        ),
    ]
