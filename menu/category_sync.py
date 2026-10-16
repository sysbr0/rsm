import logging
import os
import uuid

import requests

from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify

from menu.models import Category

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

def build_category_payload(category):
    category_uuid = str(uuid.UUID(str(category.uuid)))
    restaurant_uuid = get_restaurant_uuid()

    version = int(getattr(category, "version", 1) or 1)

    if version < 1:
        raise ValueError("Category version must be positive.")

    name = (category.name or "").strip()

    if not name:
        raise ValueError("Category name cannot be empty.")

    event_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"sysbr:category:{category_uuid}:{version}",
    )

    return {
        "event_id": str(event_id),
        "restaurant": restaurant_uuid,
        "entity_type": "CATEGORY",
        "entity_id": category_uuid,
        "version": version,
        "payload": {
            "uuid": category_uuid,
            "name": name,
            "slug": slugify(name)[:150],
            "description": category.description or "",
            "sort_order": category.display_order,
            "is_active": category.is_active,
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


def mark_category_unsynced(category):
    Category.objects.filter(pk=category.pk).update(
        is_synced=False,
    )


# ==========================================================
# PUBLISH ONE CATEGORY
# ==========================================================

def publish_category(category, token=None):
    try:
        endpoint = get_sync_endpoint()
        token = token or get_cloud_token()

        if not token:
            raise ValueError(
                "No cloud token is configured."
            )

        payload = build_category_payload(category)

    except (ValueError, TypeError, AttributeError) as exc:
        logger.error(
            "Category %s cannot be prepared for sync: %s",
            category.pk,
            exc,
        )
        mark_category_unsynced(category)
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
            "Cloud request failed for category %s.",
            category.pk,
        )
        print("Network error:", str(exc))
        mark_category_unsynced(category)
        return False

    response_body = get_response_body(response)

    if not response.ok:
        logger.error(
            "Category sync failed. HTTP %s. "
            "Category=%s UUID=%s Response=%s",
            response.status_code,
            category.pk,
            category.uuid,
            str(response_body)[:3000],
        )

        print("Category synchronization failed.")
        print("HTTP status:", response.status_code)
        print("Endpoint:", endpoint)
        print("Server response:", response_body)

        mark_category_unsynced(category)
        return False

    synced_at = timezone.now()

    Category.objects.filter(pk=category.pk).update(
        is_synced=True,
        last_synced_at=synced_at,
    )

    category.is_synced = True
    category.last_synced_at = synced_at

    logger.info(
        "Category synchronized: %s (%s), version=%s",
        category.name,
        category.uuid,
        payload["version"],
    )

    print("Category published successfully.")
    print("HTTP status:", response.status_code)
    print("Category:", category.name)
    print("UUID:", category.uuid)
    print("Version:", payload["version"])
    print("Server response:", response_body)

    return True


# ==========================================================
# PUBLISH ALL UNSYNCED CATEGORIES
# ==========================================================

def publish_unsynced_categories(token=None):
    published = 0
    failed = 0

    categories = Category.objects.filter(
        is_synced=False,
    ).order_by("created_at")

    total = categories.count()

    print("Unsynced categories:", total)

    for category in categories.iterator():
        print(
            f"\nPublishing category: {category.name} "
            f"({category.uuid})"
        )

        if publish_category(category, token=token):
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
# PUBLISH ALL CATEGORIES (force refresh)
# ==========================================================

def publish_all_categories(token=None):
    """
    Force-publish every category, ignoring is_synced.
    Returns (published, failed, total).
    """
    published = 0
    failed = 0

    categories = Category.objects.all().order_by("created_at")
    total = categories.count()

    for category in categories.iterator():
        if publish_category(category, token=token):
            published += 1
        else:
            failed += 1

    return published, failed, total