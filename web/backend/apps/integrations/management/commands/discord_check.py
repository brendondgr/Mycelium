"""Print the OAuth values this stack will actually send to Discord.

The reason this command exists: when a redirect_uri is not in the Discord app's
registered list, Discord refuses it on *its own* page ("Invalid OAuth2
redirect_uri") and never calls back, so the failure leaves no trace in this
stack's logs and the value that caused it is never written down anywhere. The
only way to fix it is to know the exact string being sent — which is what this
prints.

Paste the two Redirect URIs verbatim into Discord Developer Portal ->
your app -> OAuth2 -> Redirects. Byte-for-byte: scheme, host, no trailing slash.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.integrations.services import oauth


class Command(BaseCommand):
    help = "Show the Discord OAuth redirect URIs and config this stack will send."

    def handle(self, *args, **options):
        pinned_user = settings.DISCORD_OAUTH_REDIRECT_URI
        pinned_guild = settings.DISCORD_GUILD_REDIRECT_URI
        user_uri = oauth.user_redirect_uri()
        guild_uri = oauth.guild_redirect_uri()

        self.stdout.write(
            self.style.MIGRATE_HEADING("Register these in the Discord Developer Portal")
        )
        self.stdout.write("  (your app -> OAuth2 -> Redirects), byte-for-byte:\n")
        self.stdout.write(self.style.SUCCESS(f"    {user_uri}"))
        self.stdout.write(self.style.SUCCESS(f"    {guild_uri}"))

        self.stdout.write(self.style.MIGRATE_HEADING("\nHow that origin was resolved"))
        for label, value in (
            ("PUBLIC_HOSTNAME", settings.PUBLIC_HOSTNAME),
            ("PUBLIC_BASE_URL", settings.PUBLIC_BASE_URL),
            ("DISCORD_CALLBACK_ORIGIN", settings.DISCORD_CALLBACK_ORIGIN),
            ("DISCORD_OAUTH_REDIRECT_URI (pin)", pinned_user),
            ("DISCORD_GUILD_REDIRECT_URI (pin)", pinned_guild),
        ):
            self.stdout.write(f"  {label:34s} {value or '(unset)'}")

        if not settings.DISCORD_CALLBACK_ORIGIN and not pinned_user:
            self.stdout.write(
                self.style.WARNING(
                    "\n  No fixed origin. The redirect_uri is derived per\n"
                    "  request, so it varies with the host the browser used —\n"
                    "  including the internal proxy hop. Set PUBLIC_HOSTNAME\n"
                    "  (or DISCORD_CALLBACK_ORIGIN)."
                )
            )
        elif settings.DISCORD_CALLBACK_ORIGIN.startswith("http://"):
            self.stdout.write(
                self.style.WARNING(
                    "\n  The callback origin is plain http. Fine locally; a public\n"
                    "  deployment should be https or Discord users will be sent over\n"
                    "  an unencrypted hop."
                )
            )

        self.stdout.write(self.style.MIGRATE_HEADING("\nOther required app settings"))
        self.stdout.write(
            "  DISCORD_CLIENT_ID                  "
            + (settings.DISCORD_CLIENT_ID or "(unset)")
        )
        self.stdout.write(
            "  DISCORD_CLIENT_SECRET              "
            + ("set" if settings.DISCORD_CLIENT_SECRET else self.style.ERROR("UNSET"))
        )
        self.stdout.write(
            "  DISCORD_BOT_TOKEN                  "
            + ("set" if settings.DISCORD_BOT_TOKEN else self.style.ERROR("UNSET"))
        )
        self.stdout.write(
            "  DISCORD_INVITE_URL                 "
            + (settings.DISCORD_INVITE_URL or "(unset)")
        )

        self.stdout.write(self.style.MIGRATE_HEADING("\nAlso confirm in the portal"))
        self.stdout.write(
            "  * Installation -> Installation Contexts includes 'User Install'\n"
            "    (the personal link sends integration_type=1).\n"
            "  * OAuth2 -> 'Requires OAuth2 Code Grant' is ON\n"
            "    (the server install is a code grant, not the callback-less bot flow)."
        )
