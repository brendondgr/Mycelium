from django.db import migrations

# The one canonical add-on today: the Mylo-server capability. It grants
# Feature.BOT_SERVER, which no tier grants on its own (architecture A4). Price is
# informational (Lab $10 / Canopy $25 on the pricing page); charging is deferred.
BOT_SERVER_SLUG = "bot_server"
BOT_SERVER_FEATURE = "bot_server"


def seed_bot_server(apps, schema_editor):
    AddOn = apps.get_model("billing", "AddOn")
    AddOn.objects.update_or_create(
        slug=BOT_SERVER_SLUG,
        defaults={
            "name": "Mylo for your server",
            "feature": BOT_SERVER_FEATURE,
            "description": (
                "Invite Mylo into your Discord server so it can post research "
                "updates to your channels."
            ),
            "price_cents": 1000,
        },
    )


def unseed_bot_server(apps, schema_editor):
    AddOn = apps.get_model("billing", "AddOn")
    AddOn.objects.filter(slug=BOT_SERVER_SLUG).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0002_addon_subscriptionaddon"),
    ]

    operations = [
        migrations.RunPython(seed_bot_server, unseed_bot_server),
    ]
