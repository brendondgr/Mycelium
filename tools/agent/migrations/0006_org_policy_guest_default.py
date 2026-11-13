"""An org that never chose a Discord guest level now gives guests public
material only (``""`` = not chosen). Rows already stored keep their value."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0005_thread_demo_visitor"),
    ]

    operations = [
        migrations.AlterField(
            model_name="agentorgpolicy",
            name="discord_guests",
            field=models.CharField(blank=True, default="", max_length=12),
        ),
    ]
