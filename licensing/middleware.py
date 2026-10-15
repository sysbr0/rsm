from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch

from .checker import LicenseChecker


def _get_exempt_paths():
    """
    Static exemptions + the URLs of the licensing views themselves.
    Prevents the middleware from guarding its own redirect target.
    """
    paths = [
        "/users/login/",
        "/users/logout/",
        "/admin/",
        "/static/",
        "/media/",
        "/favicon.ico",
    ]
    for name in ("license_status", "license_activate"):
        try:
            paths.append(reverse(name))
        except NoReverseMatch:
            pass
    return tuple(paths)


class LicenseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_paths = _get_exempt_paths()

    def __call__(self, request):
        # Anonymous → let Django's login gate handle it
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Exempt paths → always allow
        if any(request.path.startswith(p) for p in self.exempt_paths):
            return self.get_response(request)

        # License check
        valid = LicenseChecker.is_licensed()
        request.license_valid = valid

        if not valid:
            return redirect("license_activate")

        return self.get_response(request)