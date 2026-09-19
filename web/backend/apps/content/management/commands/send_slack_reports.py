"""Queue today's Slack reports (ambient Plan 11). A no-op while Slack is off.

manage.py send_slack_reports
"""

import json

from django.core.management.base import BaseCommand

from apps.content.slack_reports import send


class Command(BaseCommand):
    help = "Queue daily and weekly reports for Slack readers and labs."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(send()))
