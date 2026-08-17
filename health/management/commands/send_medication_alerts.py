"""
Raise medication reminders, missed-dose alerts and restock warnings.

Django only runs when a request arrives, so nothing wakes up at 8 AM on
its own. This command is the thing that does, and is meant to be run every
15 minutes by Windows Task Scheduler (or cron on Linux):

    python manage.py send_medication_alerts

Running it more often than necessary is harmless -- every rule is
idempotent, so a notification is raised once no matter how many times the
command fires.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from health import alerts


class Command(BaseCommand):
    help = 'Send due, missed and restock medication alerts.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--patient', type=str, default=None,
            help='Limit to one patient, by email. Useful while testing.')
        parser.add_argument(
            '--quiet', action='store_true',
            help='Only print when something was actually sent.')

    def handle(self, *args, **options):
        patient = None
        if options['patient']:
            patient = User.objects.filter(email__iexact=options['patient']).first()
            if patient is None:
                self.stderr.write(self.style.ERROR(
                    f"No user with email {options['patient']}"))
                return

        counts = alerts.run_medication_alerts(patient=patient)
        total = sum(counts.values())

        if total == 0 and options['quiet']:
            return

        stamp = timezone.localtime().strftime('%d %b %Y %H:%M')
        line = (f"[{stamp}] reminders={counts['reminders']} "
                f"missed={counts['missed']} restock={counts['restock']}")
        style = self.style.SUCCESS if total else self.style.NOTICE
        self.stdout.write(style(line))
