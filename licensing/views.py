import platform

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone

from .checker import LicenseChecker
from .models import LocalLicense
from .services import (
    get_last_local_license,
    get_license_server_url,
    sync_license_from_server,
)


# ==========================================================
# LICENSE STATUS VIEW
# ==========================================================

def license_status_view(request):
    license_obj = get_last_local_license()

    if license_obj is None:
        messages.info(request, "No license found. Please activate one first.")
        return redirect("license_activate")

    if request.method == "POST" and request.POST.get("action") == "reverify":
        result = sync_license_from_server()

        if result["valid"]:
            LicenseChecker.invalidate_cache()
            messages.success(request, "License successfully verified with server.")
        elif result["offline"]:
            messages.warning(
                request,
                f"Working offline: {result.get('error', 'Unable to reach server.')}",
            )
        else:
            LicenseChecker.invalidate_cache()
            messages.error(request, result.get("error", "Verification failed."))

        return redirect("license_status")

    now = timezone.now()
    days_left = None
    is_expired = False

    if license_obj.expires_at:
        delta = license_obj.expires_at - now
        days_left = delta.days
        is_expired = delta.total_seconds() <= 0

    return render(
        request,
        "licensing/status.html",
        {
            "license": license_obj,
            "machine_name": platform.node(),
            "server_url": get_license_server_url(),
            "now": now,
            "days_left": days_left,
            "is_expired": is_expired,
        },
    )


# ==========================================================
# ACTIVATION VIEW
# ==========================================================

def activate_license_view(request):
    existing_license = get_last_local_license()

    if request.method == "GET":
        return render(
            request,
            "licensing/activate.html",
            {
                "existing_license": existing_license,
                "machine_name": platform.node(),
                "license_key_value": "",
            },
        )

    license_key = (request.POST.get("license_key") or "").strip()

    if not license_key:
        messages.error(request, "Please enter your license key.")
        return render(
            request,
            "licensing/activate.html",
            {
                "existing_license": existing_license,
                "machine_name": platform.node(),
                "license_key_value": license_key,
            },
        )

    result = sync_license_from_server(license_key=license_key)

    if not result["valid"]:
        messages.error(
            request,
            result.get("error", "License activation failed. Please check your key."),
        )
        return render(
            request,
            "licensing/activate.html",
            {
                "existing_license": existing_license,
                "machine_name": platform.node(),
                "license_key_value": license_key,
            },
        )

    license_obj = result["license"]
    expires_label = (
        license_obj.expires_at.strftime("%b %d, %Y")
        if license_obj.expires_at
        else "Lifetime / Perpetual"
    )

    LicenseChecker.invalidate_cache()

    messages.success(
        request,
        f"License activated successfully! "
        f"Plan: {license_obj.plan or 'N/A'} · Expires: {expires_label}.",
    )

    return redirect("license_status")