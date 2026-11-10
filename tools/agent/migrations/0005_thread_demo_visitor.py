from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0004_discord_turn_message_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentthread",
            name="demo_visitor",
            field=models.CharField(
                blank=True, db_index=True, default="", max_length=64
            ),
        ),
    ]
