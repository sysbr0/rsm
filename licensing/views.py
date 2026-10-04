import platform
import requests

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import LocalLicense
from .services import (
    get_license_server_url,
    parse_server_datetime,
)


def activate_license_view(request):

    # ==================================================
    # GET
    # ==================================================

    if request.method == "GET":
        return render(
            request,
            "licensing/activate.html",
        )

    # ==================================================
    # POST
    # ==================================================

    license_key = request.POST.get(
        "license_key",
        "",
    ).strip()

    if not license_key:

        messages.error(
            request,
            "Please enter your license key.",
        )

        return render(
            request,
            "licensing/activate.html",
        )

    # ==================================================
    # Prepare installation information
    # ==================================================

    # Use the existing installation ID if available.
    existing_license = (
        LocalLicense.objects
        .order_by("-created_at")
        .first()
    )

    if existing_license:

        installation_id = str(
            existing_license.installation_id
        )

    else:

        # If your LocalLicense model has a default UUID,
        # this can be replaced with your model's creation
        # logic.
        from uuid import uuid4

        installation_id = str(uuid4())

    payload = {
        "license_key": license_key,
        "installation_id": installation_id,
        "machine_name": platform.node(),
    }

    # ==================================================
    # Contact central license server
    # ==================================================

    try:

        response = requests.post(
            get_license_server_url(),
            data=payload,
            timeout=15,
        )

    except requests.RequestException:

        messages.error(
            request,
            "Unable to connect to the license server. "
            "Please check your internet connection.",
        )

        return render(
            request,
            "licensing/activate.html",
        )

    # ==================================================
    # HTTP error
    # ==================================================

    if not response.ok:

        try:
            data = response.json()
        except ValueError:
            data = {}

        error_message = data.get(
            "error",
            "License activation failed.",
        )

        messages.error(
            request,
            error_message,
        )

        return render(
            request,
            "licensing/activate.html",
        )

    # ==================================================
    # Parse response
    # ==================================================

    try:

        data = response.json()

    except ValueError:

        messages.error(
            request,
            "The license server returned an invalid response.",
        )

        return render(
            request,
            "licensing/activate.html",
        )

    # ==================================================
    # Check server validity
    # ==================================================

    if not data.get("valid"):

        messages.error(
            request,
            data.get(
                "error",
                "The license key is not valid.",
            ),
        )

        return render(
            request,
            "licensing/activate.html",
        )

    # ==================================================
    # Read server data
    # ==================================================

    server_license_key = data.get(
        "license_key",
        license_key,
    )

    server_status = data.get(
        "status",
        "ACTIVE",
    )

    customer_name = data.get(
        "customer_name",
        "",
    )

    product = data.get(
        "product",
        "",
    )

    plan = data.get(
        "plan",
        "",
    )

    expires_at = parse_server_datetime(
        data.get("expires_at")
    )

    # ==================================================
    # Create / update local license
    # ==================================================

    if existing_license:

        license_obj = existing_license

        license_obj.license_key = server_license_key
        license_obj.customer_name = customer_name
        license_obj.product = product
        license_obj.plan = plan
        license_obj.status = server_status
        license_obj.expires_at = expires_at
        license_obj.is_active = True
        license_obj.last_verified_at = timezone.now()

        license_obj.save()

    else:

        license_obj = LocalLicense.objects.create(
            license_key=server_license_key,
            installation_id=installation_id,
            customer_name=customer_name,
            product=product,
            plan=plan,
            status=server_status,
            expires_at=expires_at,
            is_active=True,
            last_verified_at=timezone.now(),
        )

    # ==================================================
    # Success
    # ==================================================

    messages.success(
        request,
        "License activated successfully.",
    )

    return redirect("license_status")