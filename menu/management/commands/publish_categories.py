# management/commands/publish_categories.py
from django.core.management.base import BaseCommand
from menu.models import Category
from menu.sync import publish_category


class Command(BaseCommand):
    help = "Publish categories to cloud"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true",
                            help="Re-push even if is_synced=True")
        parser.add_argument("--uuid", help="Only this uuid")

    def handle(self, *args, **opts):
        qs = Category.objects.all()
        if not opts["force"]:
            qs = qs.filter(is_synced=False)
        if opts["uuid"]:
            qs = qs.filter(uuid=opts["uuid"])

        ok = fail = 0
        for c in qs:
            if publish_category(c):
                ok += 1
                self.stdout.write(self.style.SUCCESS(f"  ✔ {c.name}"))
            else:
                fail += 1
                self.stdout.write(self.style.ERROR(f"  ✘ {c.name}"))

        self.stdout.write(self.style.SUCCESS(f"\nOK={ok} FAIL={fail}"))