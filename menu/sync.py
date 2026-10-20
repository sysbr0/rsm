import requests
import os
from django.conf import settings
from django.utils import timezone

from menu.models import Category as LocalCategory

CLOUD_BASE = (
    getattr(settings, "CLOUD_API_URL", "") or getattr(settings, "LICENSE_SERVER_URL", "")
).rstrip("/")
CLOUD_TOKEN = getattr(settings, "CLOUD_API_KEY", "") or ""


def fetch_cloud_categories(restaurant_uuid: str) -> list[dict]:
    if not CLOUD_BASE:
        raise RuntimeError("CLOUD_API_URL or LICENSE_SERVER_URL is not configured.")

    headers = {
        "Authorization": f"Bearer {CLOUD_TOKEN}" if CLOUD_TOKEN else "",
    }
    params = {"restaurant": restaurant_uuid}

    endpoints = [
        "/api/categories/",
        "/api/v1/categories/",
        "/api/v1/sync/categories/",
    ]

    last_error = None

    for endpoint in endpoints:
        url = f"{CLOUD_BASE}{endpoint}"
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=20)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            data = resp.json()
            return data["results"] if isinstance(data, dict) and "results" in data else data
        except requests.RequestException as exc:
            last_error = exc
            continue

    if last_error:
        raise last_error

    raise RuntimeError(f"No valid categories endpoint found on {CLOUD_BASE}")


def pull_categories(restaurant_uuid: str) -> dict:
    cloud_rows = fetch_cloud_categories(restaurant_uuid)
    created = 0
    updated = 0
    skipped = 0

    for row in cloud_rows:
        cloud_uuid = (row.get("uuid") or row.get("source_id") or row.get("entity_id") or "").strip()
        if not cloud_uuid:
            skipped += 1
            continue

        values = {
            "name": row.get("name") or "Unnamed",
            "description": row.get("description") or "",
            "display_order": row.get("sort_order") or row.get("display_order") or 0,
            "is_active": row.get("is_active", True),
          
            "is_synced": True,
            "last_synced_at": timezone.now(),
        }

        obj = LocalCategory.objects.filter(uuid=cloud_uuid).first()
        if obj is None:
            LocalCategory.objects.create(uuid=cloud_uuid, **values)
            created += 1
        else:
            LocalCategory.objects.filter(pk=obj.pk).update(**values)
            updated += 1

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }


# ------------------------------------------------------------------
# Publish (push) local Category changes to the cloud events endpoint
# ------------------------------------------------------------------
import logging
logger = logging.getLogger(__name__)

CLOUD_EVENTS_URL = f"{CLOUD_BASE}/api/v1/sync/events/"


def build_category_payload(category) -> dict:
    """Pure read. Returns the JSON to POST for a Category instance."""
    return {
        "event_id": f"category:{category.uuid}:{getattr(category, 'version', 1)}",
        "restaurant_id": getattr(settings, 'RESTAURANT_UUID', ''),
        "entity_type": "CATEGORY",
        "entity_id": category.uuid,
        "version": getattr(category, 'version', 1),
        "occurred_at": category.updated_at.isoformat() if getattr(category, 'updated_at', None) else timezone.now().isoformat(),
        "data": {
            "source_id": category.uuid,
            "name": category.name,
            "description": category.description,
            "sort_order": category.display_order,
            "is_active": category.is_active,
            "icon_url": category.icon.url if getattr(category, 'icon', None) else None,
            # Extra identifiers to help the cloud match records during testing
            "local_pk": str(getattr(category, 'pk', '')),
            "slug": getattr(category, 'slug', None),
            "match_candidates": {
                "uuid": category.uuid,
                "local_pk": str(getattr(category, 'pk', '')),
                "name": category.name,
                "slug": getattr(category, 'slug', None),
            },
        },
    }


def publish_category(category) -> bool:
    """Push a Category to the cloud events endpoint.

    On success: update only bookkeeping fields on the local model (is_synced, last_synced_at).
    """
    token = CLOUD_TOKEN

    # If no static CLOUD token is configured, try service login using env creds.
    # Next, try reading a token file (written by web login) if present.
    if not token:
        token_file = getattr(settings, "CLOUD_TOKEN_FILE", os.getenv("CLOUD_TOKEN_FILE"))
        if token_file and os.path.exists(token_file):
            try:
                with open(token_file, "r") as f:
                    token = f.read().strip()
            except Exception:
                logger.exception("Could not read cloud token file %s", token_file)
    if not token:
        service_email = os.getenv("CLOUD_SERVICE_EMAIL")
        service_password = os.getenv("CLOUD_SERVICE_PASSWORD")
        if service_email and service_password:
            login_url = f"{CLOUD_BASE}/api/restaurant/login/"
            try:
                r = requests.post(
                    login_url,
                    json={"email": service_email, "password": service_password},
                    headers={"Accept": "application/json"},
                    timeout=10,
                )
                r.raise_for_status()
                j = r.json()
                token = j.get("access") or j.get("token")
            except requests.RequestException:
                logger.exception("Service login to cloud failed; no CLOUD_TOKEN configured.")

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = build_category_payload(category)

    try:
        resp = requests.post(CLOUD_EVENTS_URL, json=payload, headers=headers, timeout=15)
        if not resp.ok:
            logger.warning(
                "Cloud push failed for category %s: HTTP %s - %s",
                getattr(category, 'uuid', '?'),
                resp.status_code,
                resp.text[:1000],
            )
            LocalCategory.objects.filter(pk=category.pk).update(is_synced=False)
            return False
    except requests.RequestException as exc:
        body = getattr(getattr(exc, 'response', None), 'text', None) or ''
        logger.exception(
            "Cloud push failed for category %s: exception=%s body=%s",
            getattr(category, 'uuid', '?'),
            exc,
            body[:1000],
        )
        # mark as not synced (no-op if already False)
        LocalCategory.objects.filter(pk=category.pk).update(is_synced=False)
        return False

    LocalCategory.objects.filter(pk=category.pk).update(
        is_synced=True,
        last_synced_at=timezone.now(),
    )
    logger.info("Category %s pushed successfully", getattr(category, 'uuid', '?'))
    return True