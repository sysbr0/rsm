import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from local_app.models import LocalCategory


CLOUD_BASE = settings.CLOUD_BASE_URL           # e.g. "https://admin.sysbr.net"
CLOUD_TOKEN = settings.CLOUD_API_TOKEN         # "Token abc..." or "Bearer ..."


def fetch_cloud_categories(restaurant_uuid: str) -> list[dict]:
    url = f"{CLOUD_BASE}/api/categories/"
    headers = {"Authorization": CLOUD_TOKEN}
    params = {"restaurant": restaurant_uuid}

    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    # Handle both paginated and non-paginated responses
    return data["results"] if isinstance(data, dict) and "results" in data else data


def pull_categories(restaurant_uuid: str) -> dict:
    """
    Pull all categories from cloud and upsert into LocalCategory
    using cloud_uuid as the matching key.
    """
    cloud_rows = fetch_cloud_categories(restaurant_uuid)
    created, updated, skipped = 0, 0, 0

    for row in cloud_rows:
        cloud_uuid = row["uuid"]

        obj = LocalCategory.objects.filter(cloud_uuid=cloud_uuid).first()

        if obj is None:
            LocalCategory.objects.create(
                cloud_uuid=cloud_uuid,
                name=row["name"],
                slug=row["slug"],
                description=row.get("description", ""),
                is_active=row.get("is_active", True),
                is_published=row.get("is_published", True),
                sort_order=row.get("sort_order", 0),
                sync_status="SYNCED",
                cloud_synced_at=timezone.now(),
            )
            created += 1
        else:
            obj.name = row["name"]
            obj.slug = row["slug"]
            obj.description = row.get("description", "")
            obj.is_active = row.get("is_active", True)
            obj.is_published = row.get("is_published", True)
            obj.sort_order = row.get("sort_order", 0)
            obj.sync_status = "SYNCED"
            obj.cloud_synced_at = timezone.now()
            obj.save()
            updated += 1

    return {"created": created, "updated": updated, "skipped": skipped}