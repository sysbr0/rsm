from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import LocalLicense


@receiver(post_save, sender=LocalLicense)
def _license_changed(sender, instance, **kwargs):
    cache.delete("license:is_valid")
    cache.delete("license:object")
    cache.delete("license:warning")


@receiver(post_delete, sender=LocalLicense)
def _license_deleted(sender, instance, **kwargs):
    cache.delete("license:is_valid")
    cache.delete("license:object")
    cache.delete("license:warning")