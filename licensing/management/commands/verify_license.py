from django.core.management.base import BaseCommand

from licensing.tasks import daily_license_check


class Command(BaseCommand):
    help = "Daily license check: verify with server and update warning state."

    def handle(self, *args, **opts):
        summary = daily_license_check()

        if summary["valid"]:
            self.stdout.write(self.style.SUCCESS(
                f"License OK ({summary['reason']}) — "
                f"{summary['days_remaining']} day(s) remaining."
            ))
        elif summary["offline"]:
            self.stdout.write(self.style.WARNING(
                f"Offline — {summary['error']}"
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f"License invalid: {summary.get('error') or summary['reason']}"
            ))

        if summary["warning_level"]:
            self.stdout.write(self.style.WARNING(
                f"⚠  Warning level: {summary['warning_level']} "
                f"({summary['days_remaining']} day(s) left)"
            ))