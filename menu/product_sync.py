import logging
import os
import uuid

import requests

from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify

from menu.models import Product

logger = logging.getLogger(__name__)


# ==========================================================
# CONFIGURATION
# ==========================================================

REQUEST_TIMEOUT = 20
SYNC_ENDPOINT = "/api/v1/sync/events/"


# ==========================================================
# CLOUD CONFIGURATION
# ==========================================================

def get_cloud_base():
    return (
        getattr(settings, "CLOUD_API_URL", "") or ""
    ).strip().rstrip("/")


def get_cloud_token():
    """
    Legacy fallback: used only when no token is passed in.
    Prefers CLOUD_API_KEY / CLOUD_TOKEN settings, then a token file.
    """
    token = (
        getattr(settings, "CLOUD_API_KEY", "")
        or getattr(settings, "CLOUD_TOKEN", "")
        or ""
    ).strip()

    if token:
        return token

    token_file = getattr(
        settings,
        "CLOUD_TOKEN_FILE",
        os.getenv("CLOUD_TOKEN_FILE", ""),
    )

    if token_file and os.path.isfile(token_file):
        try:
            with open(token_file, "r", encoding="utf-8") as file:
                return file.read().strip()
        except OSError:
            logger.exception("Unable to read cloud token file.")

    return ""


def get_restaurant_uuid():
    value = getattr(settings, "RESTAURANT_UUID", None)

    if not value:
        raise ValueError(
            "RESTAURANT_UUID is missing from Django settings."
        )

    return str(uuid.UUID(str(value)))


def get_sync_endpoint():
    cloud_base = get_cloud_base()

    if not cloud_base:
        raise ValueError(
            "CLOUD_API_URL is missing from Django settings."
        )

    return f"{cloud_base}{SYNC_ENDPOINT}"


# ==========================================================
# PAYLOAD
# ==========================================================

def build_product_payload(product):
    product_uuid = str(uuid.UUID(str(product.uuid)))
    restaurant_uuid = get_restaurant_uuid()

    version = int(
        getattr(product, "local_version", 1)
        or getattr(product, "version", 1)
        or 1
    )

    if version < 1:
        raise ValueError("Product version must be positive.")

    name = (product.name or "").strip()

    if not name:
        raise ValueError("Product name cannot be empty.")

    event_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"sysbr:product:{product_uuid}:{version}",
    )

    category_uuid = None
    if getattr(product, "category_id", None):
        try:
            category_uuid = str(uuid.UUID(str(product.category.uuid)))
        except (ValueError, TypeError, AttributeError):
            category_uuid = None

    section_uuid = None
    if getattr(product, "section_id", None):
        try:
            section_uuid = str(uuid.UUID(str(product.section.uuid)))
        except (ValueError, TypeError, AttributeError):
            section_uuid = None

    return {
        "event_id": str(event_id),
        "restaurant": restaurant_uuid,
        "entity_type": "PRODUCT",
        "entity_id": product_uuid,
        "version": version,
        "payload": {
            "uuid": product_uuid,
            "source_id": product_uuid,
            "sku": product.sku or "",
            "name": name,
            "slug": slugify(name)[:180],
            "description": product.description or "",
            "category_uuid": category_uuid,
            "section_uuid": section_uuid,
            "price": str(product.price or "0.00"),
            "tax_rate": str(product.tax_rate or "0.00"),
            "is_active": product.is_active,
            "is_published": getattr(product, "is_published", True),
            "is_available": getattr(product, "is_available", True),
            "is_featured": getattr(product, "is_featured", False),
            "preparation_time_minutes": getattr(
                product, "preparation_time_minutes", None
            ),
            "sort_order": product.display_order,
        },
    }


# ==========================================================
# RESPONSE HELPERS
# ==========================================================

def get_response_body(response):
    try:
        return response.json()
    except ValueError:
        return response.text[:3000]


def mark_product_unsynced(product):
    Product.objects.filter(pk=product.pk).update(
        is_synced=False,
    )


# ==========================================================
# PUBLISH ONE PRODUCT
# ==========================================================

def publish_product(product, token=None):
    try:
        endpoint = get_sync_endpoint()
        token = token or get_cloud_token()

        if not token:
            raise ValueError(
                "No cloud token is configured."
            )

        payload = build_product_payload(product)

    except (ValueError, TypeError, AttributeError) as exc:
        logger.error(
            "Product %s cannot be prepared for sync: %s",
            product.pk,
            exc,
        )
        mark_product_unsynced(product)
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

    except requests.RequestException as exc:
        logger.exception(
            "Cloud request failed for product %s.",
            product.pk,
        )
        print("Network error:", str(exc))
        mark_product_unsynced(product)
        return False

    response_body = get_response_body(response)

    if not response.ok:
        logger.error(
            "Product sync failed. HTTP %s. "
            "Product=%s UUID=%s Response=%s",
            response.status_code,
            product.pk,
            product.uuid,
            str(response_body)[:3000],
        )

        print("Product synchronization failed.")
        print("HTTP status:", response.status_code)
        print("Endpoint:", endpoint)
        print("Server response:", response_body)

        mark_product_unsynced(product)
        return False

    # A successful HTTP response means the server accepted the request.
    # Update only sync metadata; do not increment the product version.
    synced_at = timezone.now()

    Product.objects.filter(pk=product.pk).update(
        is_synced=True,
        last_synced_at=synced_at,
    )

    product.is_synced = True
    product.last_synced_at = synced_at

    logger.info(
        "Product synchronized: %s (%s), version=%s",
        product.name,
        product.uuid,
        payload["version"],
    )

    print("Product published successfully.")
    print("HTTP status:", response.status_code)
    print("Product:", product.name)
    print("UUID:", product.uuid)
    print("Version:", payload["version"])
    print("Server response:", response_body)

    return True


# ==========================================================
# PUBLISH ALL UNSYNCED PRODUCTS
# ==========================================================

def publish_unsynced_products(token=None):
    published = 0
    failed = 0

    products = Product.objects.filter(
        is_synced=False,
    ).order_by("created_at")

    total = products.count()

    print("Unsynced products:", total)

    for product in products.iterator():
        print(
            f"\nPublishing product: {product.name} "
            f"({product.uuid})"
        )

        if publish_product(product, token=token):
            published += 1
        else:
            failed += 1

    print("\n========== SYNC SUMMARY ==========")
    print("Total:", total)
    print("Published:", published)
    print("Failed:", failed)
    print("==================================")

    return published


# ==========================================================
# PUBLISH ALL PRODUCTS (force refresh)
# ==========================================================

def publish_all_products(token=None):
    """
    Force-publish every product, ignoring is_synced.
    Returns (published, failed, total).
    """
    published = 0
    failed = 0

    products = Product.objects.all().order_by("created_at")
    total = products.count()

    for product in products.iterator():
        if publish_product(product, token=token):
            published += 1
        else:
            failed += 1

    return published, failed, total