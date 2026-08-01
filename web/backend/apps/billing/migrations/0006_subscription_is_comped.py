from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0005_seat_ends_at_subscription_activated_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="is_comped",
            field=models.BooleanField(
                default=False,
                help_text="Complimentary plan — entitled but never billed.",
            ),
        ),
    ]
