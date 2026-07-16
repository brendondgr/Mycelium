"""EncryptedTextField round-trips and never stores plaintext."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from apps.integrations.models import DiscordIdentity

User = get_user_model()


class EncryptedTextFieldTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("enc-user", password="x")

    def test_token_round_trips_but_is_ciphertext_at_rest(self):
        identity = DiscordIdentity.objects.create(
            user=self.user,
            discord_user_id="111",
            link_method=DiscordIdentity.LinkMethod.OAUTH,
            access_token="super-secret-bearer",
        )
        # Read back through the ORM: plaintext.
        fetched = DiscordIdentity.objects.get(pk=identity.pk)
        self.assertEqual(fetched.access_token, "super-secret-bearer")

        # Read the raw column: never the plaintext.
        with connection.cursor() as cur:
            cur.execute(
                "SELECT access_token FROM integrations_discordidentity WHERE id=%s",
                [identity.pk],
            )
            raw = cur.fetchone()[0]
        self.assertNotIn("super-secret-bearer", raw)
        self.assertTrue(raw.startswith("fernet:"))

    def test_blank_token_stays_blank(self):
        identity = DiscordIdentity.objects.create(
            user=self.user,
            discord_user_id="222",
            link_method=DiscordIdentity.LinkMethod.ACTIVATION_CODE,
        )
        self.assertEqual(identity.access_token, "")
        with connection.cursor() as cur:
            cur.execute(
                "SELECT access_token FROM integrations_discordidentity WHERE id=%s",
                [identity.pk],
            )
            raw = cur.fetchone()[0]
        self.assertEqual(raw, "")
