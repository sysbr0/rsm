import logging

from django.core.cache import cache
from django.utils import timezone

from .models import LocalLicense
from .services import get_last_local_license, sync_license_from_server

logger = logging.getLogger(__name__)

CACHE_KEY_WARNING = "license_warning_state"


def daily_license_check():
    """
    Daily task:
      1. Re-verify the local license with the server.
      2. Auto-expire if past grace period.
      3. Update the warning state cache for the UI banner.
    """
    summary = {
        "verified": False,
        "offline": False,
        "valid": False,
        "warning_level": "",
        "days_remaining": None,
        "reason": "",
        "error": "",
    }

    license_obj = get_last_local_license()

    if license_obj is None:
        summary["reason"] = "NO_LICENSE"
        summary["error"] = "No local license found."
        logger.warning("Daily license check: no local license.")
        cache.delete(CACHE_KEY_WARNING)
        return summary

    # ---- 1. Server sync ----
    result = sync_license_from_server()
    summary["verified"]      = True
    summary["offline"]       = result.get("offline", False)
    summary["valid"]         = result.get("valid", False)
    summary["reason"]        = result.get("reason", "")
    summary["error"]         = result.get("error", "")

    # ---- 2. Refresh from DB (sync may have updated it) ----
    license_obj.refresh_from_db()

    # ---- 3. Auto-expire enforcement ----
    if license_obj.expires_at and timezone.now() > license_obj.expires_at:
        if not license_obj.in_grace_period:
            if license_obj.is_active:
                license_obj.is_active = False
                license_obj.status = LocalLicense.STATUS_EXPIRED
                license_obj.save(update_fields=["is_active", "status", "updated_at"])
                logger.warning(
                    "License %s auto-expired (past grace period).",
                    license_obj.license_key,
                )
            summary["valid"]  = False
            summary["reason"] = "EXPIRED"

    # ---- 4. Warning state ----
    summary["days_remaining"] = license_obj.days_remaining
    summary["warning_level"]  = license_obj.warning_level

    if license_obj.warning_level:
        license_obj.last_warning_shown_at = timezone.now()
        license_obj.save(update_fields=["last_warning_shown_at", "updated_at"])

        cache.set(
            CACHE_KEY_WARNING,
            {
                "level":         license_obj.warning_level,
                "days_remaining": license_obj.days_remaining,
                "expires_at":    (
                    license_obj.expires_at.isoformat()
                    if license_obj.expires_at else None
                ),
                "message": _warning_message(license_obj),
            },
            timeout=60 * 60 * 24,   # 24h
        )
        logger.info(
            "License warning: %s — %s day(s) remaining.",
            license_obj.warning_level,
            license_obj.days_remaining,
        )
    else:
        cache.delete(CACHE_KEY_WARNING)

    logger.info("Daily license check complete: %s", summary)
    return summary


def _warning_message(license_obj) -> str:
    d = license_obj.days_remaining
    if d <= 0:
        return "Your license expires today."
    if d == 1:
        return "Your license expires tomorrow."
    return f"Your license expires in {d} days."


def get_active_warning():
    """
    Return the cached warning dict for the current license, or None.
    Falls back to live DB values on cache miss.
    """
    cached = cache.get(CACHE_KEY_WARNING)
    if cached:
        return cached

    lic = get_last_local_license()
    if not lic or not lic.warning_level:
        return None

    return {
        "level":         lic.warning_level,
        "days_remaining": lic.days_remaining,
        "expires_at":    lic.expires_at.isoformat() if lic.expires_at else None,
        "message":       _warning_message(lic),
    }