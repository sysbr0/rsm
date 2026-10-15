import requests
from django.conf import settings
from django.utils import timezone


def sync_product_to_cloud(product):
    cloud_url = f"{settings.CLOUD_API_URL}/api/v1/sync/events/"
    headers = {
        "Authorization": f"Bearer {settings.CLOUD_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "event_id": str(product.id),  # Idempotent event key
        "restaurant_id": settings.RESTAURANT_UUID,
        "entity_type": "PRODUCT",
        "entity_id": str(product.id),
        "version": product.version,
        "data": {
            "source_id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "price": str(product.price),
            "is_active": product.is_active,
            "sort_order": product.display_order,
            "description": product.description,
        },
    }

    try:
        response = requests.post(cloud_url, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201]:
            product.is_synced = True
            product.last_synced_at = timezone.now()
            product.save(update_fields=["is_synced", "last_synced_at"])
    except Exception as e:
        # Retry logic via Celery or background worker
        pass