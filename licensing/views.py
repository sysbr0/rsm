from django.shortcuts import render


from django.contrib import messages
from django.shortcuts import redirect, render

from .models import LocalLicense
from .services import activate_license


def activate_license_view(request):
    print("======================================")
    print("activate_license_view called")
    print("======================================")

    if request.method == "POST":

        license_key = request.POST.get("license_key", "").strip()

        print("Received license key:", repr(license_key))

        if not license_key:
            messages.error(
                request,
                "Please enter your license key.",
            )
            return redirect("license_activate")

        try:
            result = activate_license(license_key)

            print("Activation result:")
            print(result)

        except Exception as exc:
            print("ACTIVATION EXCEPTION:")
            print(repr(exc))

            messages.error(
                request,
                f"License activation error: {exc}",
            )

            return redirect("license_activate")

        if result.get("success"):

            messages.success(
                request,
                "License activated successfully.",
            )

            return redirect("license_status")

        messages.error(
            request,
            result.get(
                "message",
                "License activation failed.",
            ),
        )

        return redirect("license_activate")

    # GET request
    license_obj = (
        LocalLicense.objects
        .order_by("-created_at")
        .first()
    )

    print("Local license:", license_obj)

    if license_obj:
        print("License key:", license_obj.license_key)
        print("Installation ID:", license_obj.installation_id)
        print("Status:", license_obj.status)
        print("Active:", license_obj.is_active)

    return render(
        request,
        "licensing/activate.html",
        {
            "license": license_obj,
        },
    )
```
