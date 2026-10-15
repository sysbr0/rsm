from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Product
from .sync import sync_product_to_cloud


@receiver(post_save, sender=Product)
def on_product_save(sender, instance, **kwargs):
    if not instance.is_synced:
        sync_product_to_cloud(instance)