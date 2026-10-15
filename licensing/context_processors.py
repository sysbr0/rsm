from django.core.cache import cache

from .checker import LicenseChecker


def license_context(request):
    # Only touch the DB if the template branch actually renders.
    # `license_valid` is already on the request from middleware.
    valid = getattr(request, "license_valid", None)

    # Lazy: only fetch the full object when the license is invalid
    # OR when the warning banner might need to render.
    lic = None
    warning = None

    if valid:
        # Only fetch the license object if the base template actually
        # references `license` — which happens rarely and is cached.
        warning = cache.get("license:warning")
        if warning is not None:
            lic = LicenseChecker.get_license()

    return {
        "license":          lic,
        "license_valid":    bool(valid),
        "license_warning":  warning,
    }