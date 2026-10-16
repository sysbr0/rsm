import requests
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

    headers = {"Authorization": f"Bearer {CLOUD_TOKEN}" if CLOUD_TOKEN else ""}
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

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"No valid cloud categories endpoint found for {CLOUD_BASE}")


def pull_categories(restaurant_uuid: str) -> dict:
    """Pull categories from cloud and upsert into the local Category model."""
    cloud_rows = fetch_cloud_categories(restaurant_uuid)
    created, updated, skipped = 0, 0, 0

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

    return {"created": created, "updated": updated, "skipped": skipped}