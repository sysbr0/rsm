import platform

import requests

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import LocalLicense


LICENSE_CHECK_ENDPOINT = "/api/licenses/check/"


def get_license_server_url():
    return (
        f"{settings.LICENSE_SERVER_URL.rstrip('/')}"
        f"{LICENSE_CHECK_ENDPOINT}"
    )


def parse_server_datetime(value):
    """
    Convert the server ISO datetime into a Django-aware datetime.
    """

    if not value:
        return None

    parsed = parse_datetime(value)

    if parsed is None:
        return None

    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(
            parsed,
            timezone.get_current_timezone(),
        )

    return parsed


def get_last_local_license():
    """
    Return the most recently created local license.

    The latest license is used as the license that belongs
    to this installation.
    """

    return (
        LocalLicense.objects
        .order_by("-created_at")
        .first()
    )


def sync_license_from_server():
    """
    Check the latest local license against the central
    license server and synchronize the local model.

    Flow:

        LocalLicense
             ↓
        Central API
             ↓
        Server response
             ↓
        Update LocalLicense
    """

    # --------------------------------------------------
    # Get latest local license
    # --------------------------------------------------

    license_obj = get_last_local_license()

    # --------------------------------------------------
    # No license installed
    # --------------------------------------------------

    if not license_obj:
        return {
            "valid": False,
            "offline": False,
            "reason": "NO_LICENSE",
            "license": None,
        }

    # --------------------------------------------------
    # Prepare API request
    # --------------------------------------------------

    payload = {
        "license_key": license_obj.license_key,
        "installation_id": str(
            license_obj.installation_id
        ),
        "machine_name": platform.node(),
    }

    # --------------------------------------------------
    # Contact central license server
    # --------------------------------------------------

    try:
        response = requests.post(
            get_license_server_url(),
            data=payload,
            timeout=15,
        )

    except requests.RequestException as exc:
        return {
            "valid": False,
            "offline": True,
            "reason": "SERVER_UNAVAILABLE",
            "license": license_obj,
            "error": str(exc),
        }

    # --------------------------------------------------
    # Parse response
    # --------------------------------------------------

    try:
        data = response.json()

    except ValueError:
        return {
            "valid": False,
            "offline": True,
            "reason": "INVALID_SERVER_RESPONSE",
            "license": license_obj,
        }

    # --------------------------------------------------
    # Server response values
    # --------------------------------------------------

    server_status = data.get(
        "status",
        license_obj.status,
    )

    server_license_key = data.get(
        "license_key",
        license_obj.license_key,
    )

    server_customer_name = data.get(
        "customer_name",
        license_obj.customer_name,
    )

    server_product = data.get(
        "product",
        license_obj.product,
    )

    server_plan = data.get(
        "plan",
        license_obj.plan,
    )

    server_expires_at = parse_server_datetime(
        data.get("expires_at")
    )

    # --------------------------------------------------
    # IMPORTANT:
    # Synchronize the local model even when the
    # license is expired / suspended / revoked.
    # --------------------------------------------------

    license_obj.license_key = server_license_key

    license_obj.customer_name = server_customer_name

    license_obj.product = server_product

    license_obj.plan = server_plan

    license_obj.status = server_status

    if server_expires_at:
        license_obj.expires_at = server_expires_at

    license_obj.last_verified_at = timezone.now()

    # --------------------------------------------------
    # Determine whether license is active
    # --------------------------------------------------

    is_valid = bool(
        data.get("valid")
        and server_status == "ACTIVE"
        and (
            not license_obj.expires_at
            or license_obj.expires_at > timezone.now()
        )
    )

    license_obj.is_active = is_valid

    license_obj.save()

    # --------------------------------------------------
    # License is valid
    # --------------------------------------------------

    if is_valid:
        return {
            "valid": True,
            "offline": False,
            "reason": "ACTIVE",
            "status": server_status,
            "license": license_obj,
            "data": data,
        }

    # --------------------------------------------------
    # License expired
    # --------------------------------------------------

    if server_status == "EXPIRED":

        return {
            "valid": False,
            "offline": False,
            "reason": "EXPIRED",
            "status": "EXPIRED",
            "license": license_obj,
            "data": data,
        }

    # --------------------------------------------------
    # License suspended
    # --------------------------------------------------

    if server_status == "SUSPENDED":

        return {
            "valid": False,
            "offline": False,
            "reason": "SUSPENDED",
            "status": "SUSPENDED",
            "license": license_obj,
            "data": data,
        }

    # --------------------------------------------------
    # License revoked
    # --------------------------------------------------

    if server_status == "REVOKED":

        return {
            "valid": False,
            "offline": False,
            "reason": "REVOKED",
            "status": "REVOKED",
            "license": license_obj,
            "data": data,
        }

    # --------------------------------------------------
    # Installation disabled / limit / other error
    # --------------------------------------------------

    return {
        "valid": False,
        "offline": False,
        "reason": data.get(
            "error",
            "INVALID_LICENSE",
        ),
        "status": server_status,
        "license": license_obj,
        "data": data,
    }