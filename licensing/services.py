import logging
import platform
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import LocalLicense

logger = logging.getLogger(__name__)

# ==========================================================
# CONFIG
# ==========================================================

LICENSE_CHECK_ENDPOINT = "/api/licenses/check/"
OFFLINE_GRACE_PERIOD_DAYS = 7


# ==========================================================
# URL HELPERS
# ==========================================================

def get_license_server_url():
    base = getattr(settings, "LICENSE_SERVER_URL", "") or ""
    return f"{base.rstrip('/')}{LICENSE_CHECK_ENDPOINT}"


# ==========================================================
# DATETIME HELPERS
# ==========================================================

def parse_server_datetime(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


# ==========================================================
# LOCAL LICENSE HELPERS
# ==========================================================

def get_last_local_license():
    return LocalLicense.objects.order_by("-created_at").first()


# ==========================================================
# OFFLINE EVALUATION
# ==========================================================

def evaluate_offline_validity(license_obj, error_msg="Server unavailable"):
    if not license_obj:
        return {
            "valid": False,
            "offline": True,
            "reason": "NO_LICENSE",
            "license": None,
            "error": "Server unavailable and no local license found.",
        }

    now = timezone.now()

    if not license_obj.is_active or license_obj.status not in LocalLicense.VALID_STATUSES:
        return {
            "valid": False,
            "offline": True,
            "reason": "LOCALLY_INACTIVE",
            "license": license_obj,
            "error": "License is inactive locally.",
        }

    if license_obj.expires_at and now >= license_obj.expires_at:
        license_obj.is_active = False
        license_obj.status = LocalLicense.STATUS_EXPIRED
        license_obj.save(update_fields=["is_active", "status", "updated_at"])
        return {
            "valid": False,
            "offline": True,
            "reason": "EXPIRED",
            "license": license_obj,
            "error": "License has expired.",
        }

    if license_obj.last_verified_at:
        max_offline_until = license_obj.last_verified_at + timedelta(
            days=OFFLINE_GRACE_PERIOD_DAYS
        )
        if now > max_offline_until:
            return {
                "valid": False,
                "offline": True,
                "reason": "OFFLINE_GRACE_PERIOD_EXPIRED",
                "license": license_obj,
                "error": (
                    "Offline grace period expired. "
                    "Internet connection required to re-verify."
                ),
            }

    return {
        "valid": True,
        "offline": True,
        "reason": "OFFLINE_VALID",
        "status": license_obj.status,
        "license": license_obj,
        "error": error_msg,
    }


# ==========================================================
# SYNC
# ==========================================================

def sync_license_from_server(license_key=None):
    license_obj = get_last_local_license()

    # ---- Resolve installation id + key ----
    if license_obj:
        installation_id = str(license_obj.installation_id)
        key_to_check = license_key or license_obj.license_key
    else:
        key_to_check = license_key
        installation_id = str(uuid.uuid4())

    if not key_to_check:
        return {
            "valid": False,
            "offline": False,
            "reason": "NO_LICENSE",
            "license": None,
            "error": "No license key provided.",
        }

    payload = {
        "license_key": key_to_check,
        "installation_id": installation_id,
        "machine_name": platform.node(),
    }

    now = timezone.now()

    # ---- Server call ----
    try:
        response = requests.post(
            get_license_server_url(),
            data=payload,
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.warning("License server unreachable: %s", exc)
        return evaluate_offline_validity(license_obj, error_msg=str(exc))

    try:
        data = response.json()
    except ValueError:
        logger.warning("License server returned non-JSON: %s", response.text[:200])
        return evaluate_offline_validity(
            license_obj,
            error_msg=f"Invalid server response (HTTP {response.status_code}).",
        )

    # ---- Server rejected ----
    if not response.ok or not data.get("valid"):
        if license_obj:
            license_obj.is_active = False
            license_obj.status = data.get("status", "INVALID")
            license_obj.save(update_fields=["is_active", "status", "updated_at"])

        return {
            "valid": False,
            "offline": False,
            "reason": data.get("status", "INVALID_LICENSE"),
            "license": license_obj,
            "error": data.get("error", "License verification failed."),
            "data": data,
        }

    # ---- Merge server values ----
    server_status      = data.get("status", LocalLicense.STATUS_ACTIVE)
    server_license_key = data.get("license_key", key_to_check)
    server_customer    = data.get("customer_name", "")
    server_product     = data.get("product", "")
    server_plan        = data.get("plan", "")
    server_expires_at  = parse_server_datetime(data.get("expires_at"))
    server_time        = parse_server_datetime(data.get("server_time"))

    if not license_obj:
        license_obj = LocalLicense(installation_id=installation_id)

    license_obj.license_key      = server_license_key
    license_obj.customer_name    = server_customer
    license_obj.product          = server_product
    license_obj.plan             = server_plan
    license_obj.status           = server_status
    license_obj.expires_at       = server_expires_at
    license_obj.last_verified_at = server_time or now
    license_obj.is_active        = True
    license_obj.save()

    # Invalidate cached checker state
    try:
        from .checker import LicenseChecker
        LicenseChecker.invalidate_cache()
    except ImportError:
        pass

    return {
        "valid": True,
        "offline": False,
        "reason": "ACTIVE",
        "status": server_status,
        "license": license_obj,
        "data": data,
    }