from django.apps import AppConfig


class LicensingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "licensing"

    def ready(self):
        from . import signals  # noqa: F401