
import json
import logging

import requests

from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

logger = logging.getLogger(__name__)


# ============================================================
# CLOUD API CONFIGURATION
# ============================================================

CLOUD_API_BASE = "https://admin.sysbr.net/api/restaurant"

RESTAURANT_LOGIN_API = f"{CLOUD_API_BASE}/login/"
RESTAURANT_ME_API = f"{CLOUD_API_BASE}/me/"
RESTAURANT_LOGOUT_API = f"{CLOUD_API_BASE}/logout/"

LOGIN_TEMPLATE = "online/account/login.html"
DASHBOARD_TEMPLATE = "online/dasboard.html"


# ============================================================
# EDITABLE FIELD CONFIGURATION
# ============================================================

EDITABLE_RESTAURANT_FIELDS = {
    "name",
    "slug",
    "description",
    "slogan",
    "logo_url",
    "cover_image_url",
    "address",
    "city",
    "country_code",
    "default_language",
    "default_currency",
    "timezone_name",
    "supported_languages",
    "translations",
    "social_links",
}

EDITABLE_USER_FIELDS = {
    "full_name",
    "email",
}

JSON_FIELDS = {
    "supported_languages",
    "translations",
    "social_links",
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def safe_response_json(response):
    """Return the response JSON, or an empty dictionary if invalid."""
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except (ValueError, requests.exceptions.JSONDecodeError):
        return {}


def build_edit_fields(data, editable_fields):
    """
    Convert API dictionary data into fields that can be rendered
    by the Django dashboard template.
    """
    fields = []

    for key, value in data.items():
        if isinstance(value, (dict, list)):
            display_value = json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
            )
        else:
            display_value = "" if value is None else str(value)

        fields.append({
            "key": key,
            "value": display_value,
            "editable": key in editable_fields,
            "is_json": key in JSON_FIELDS,
        })

    return fields


def dashboard_context(
    restaurant_user=None,
    restaurant=None,
    cloud_data=None,
    cloud_error="",
):
    """Build consistent context for every dashboard response."""
    restaurant_user = restaurant_user or {}
    restaurant = restaurant or {}
    cloud_data = cloud_data or {}

    return {
        "restaurant_user": restaurant_user,
        "restaurant": restaurant,
        "cloud_data": cloud_data,
        "cloud_error": cloud_error,
        "restaurant_fields": build_edit_fields(
            restaurant,
            EDITABLE_RESTAURANT_FIELDS,
        ),
        "user_fields": build_edit_fields(
            restaurant_user,
            EDITABLE_USER_FIELDS,
        ),
    }


def cloud_headers(access_token):
    """Build authenticated cloud API headers."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }


# ============================================================
# CLOUD LOGIN
# ============================================================

@csrf_protect
@require_http_methods(["GET", "POST"])
def restaurant_login(request):
    # Do not log in again if a cloud session already exists.
    if request.session.get("restaurant_access_token"):
        return redirect("restaurant_dashboard")

    if request.method == "GET":
        return render(request, LOGIN_TEMPLATE)

    email = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")

    if not email or not password:
        messages.error(request, "Enter your email and password.")
        return render(request, LOGIN_TEMPLATE, status=400)

    try:
        response = requests.post(
            RESTAURANT_LOGIN_API,
            json={
                "email": email,
                "password": password,
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )

        data = safe_response_json(response)

        if response.status_code != 200:
            messages.error(
                request,
                data.get(
                    "detail",
                    "Login failed. Check your credentials.",
                ),
            )
            return render(
                request,
                LOGIN_TEMPLATE,
                status=400 if response.status_code < 500 else 502,
            )

        access_token = data.get("access")
        refresh_token = data.get("refresh")

        if not access_token:
            messages.error(
                request,
                "The cloud API returned no access token.",
            )
            return render(request, LOGIN_TEMPLATE, status=502)

        # Clear any old local session before starting a new cloud session.
        request.session.flush()

        request.session["restaurant_access_token"] = access_token

        if refresh_token:
            request.session["restaurant_refresh_token"] = refresh_token

        request.session["restaurant_user"] = data.get("user") or {}
        request.session["restaurant_profile"] = data.get("restaurant") or {}

        return redirect("restaurant_dashboard")

    except requests.RequestException:
        logger.exception("Cloud restaurant login request failed.")
        messages.error(
            request,
            "Could not connect to the cloud authentication server.",
        )
        return render(request, LOGIN_TEMPLATE, status=502)


# ============================================================
# CLOUD DASHBOARD
# ============================================================

@require_http_methods(["GET"])
def restaurant_dashboard(request):
    access_token = request.session.get("restaurant_access_token")

    if not access_token:
        return redirect("restaurant_login")

    try:
        response = requests.get(
            RESTAURANT_ME_API,
            headers=cloud_headers(access_token),
            timeout=15,
        )

        data = safe_response_json(response)

        if response.status_code == 401:
            request.session.flush()
            messages.warning(
                request,
                "Your cloud access token expired. Please log in again.",
            )
            return redirect("restaurant_login")

        if response.status_code == 403:
            messages.error(
                request,
                data.get(
                    "detail",
                    "Your cloud account cannot access this profile.",
                ),
            )
            return render(
                request,
                DASHBOARD_TEMPLATE,
                dashboard_context(
                    request.session.get("restaurant_user"),
                    request.session.get("restaurant_profile"),
                    data,
                    "Cloud access was denied.",
                ),
                status=403,
            )

        if response.status_code == 404:
            messages.warning(
                request,
                data.get(
                    "detail",
                    "No restaurant profile was found for this account.",
                ),
            )
            return render(
                request,
                DASHBOARD_TEMPLATE,
                dashboard_context(
                    request.session.get("restaurant_user"),
                    {},
                    data,
                ),
            )

        response.raise_for_status()

        cloud_data = data
        restaurant_user = cloud_data.get("user") or {}
        restaurant = cloud_data.get("restaurant") or {}

        # Refresh the cached profile with the latest cloud response.
        request.session["restaurant_user"] = restaurant_user
        request.session["restaurant_profile"] = restaurant

        return render(
            request,
            DASHBOARD_TEMPLATE,
            dashboard_context(
                restaurant_user,
                restaurant,
                cloud_data,
            ),
        )

    except requests.RequestException:
        logger.exception("Unable to refresh the cloud restaurant profile.")

        messages.warning(
            request,
            "Unable to refresh cloud data. Showing the last saved information.",
        )

        return render(
            request,
            DASHBOARD_TEMPLATE,
            dashboard_context(
                request.session.get("restaurant_user"),
                request.session.get("restaurant_profile"),
                cloud_error="Cloud data could not be refreshed.",
            ),
        )


# ============================================================
# SAVE RESTAURANT PROFILE TO THE CLOUD
# ============================================================

@csrf_protect
@require_POST
def restaurant_profile_update(request):
    access_token = request.session.get("restaurant_access_token")

    if not access_token:
        messages.error(
            request,
            "Please log in to your cloud account.",
        )
        return redirect("restaurant_login")

    restaurant_changes = {}
    user_changes = {}

    # Read only explicitly permitted restaurant fields.
    for field in EDITABLE_RESTAURANT_FIELDS:
        form_key = f"restaurant__{field}"

        if form_key not in request.POST:
            continue

        value = request.POST.get(form_key, "").strip()

        if field in JSON_FIELDS:
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                messages.error(
                    request,
                    f"Invalid JSON value for {field.replace('_', ' ')}.",
                )
                return redirect("restaurant_dashboard")

        restaurant_changes[field] = value

    # Read only explicitly permitted user fields.
    for field in EDITABLE_USER_FIELDS:
        form_key = f"user__{field}"

        if form_key in request.POST:
            user_changes[field] = request.POST.get(
                form_key,
                "",
            ).strip()

    if not restaurant_changes and not user_changes:
        messages.info(request, "No changes were submitted.")
        return redirect("restaurant_dashboard")

    payload = {
        "restaurant": restaurant_changes,
        "user": user_changes,
    }

    try:
        response = requests.patch(
            RESTAURANT_ME_API,
            json=payload,
            headers=cloud_headers(access_token),
            timeout=20,
        )

        data = safe_response_json(response)

        if response.status_code == 401:
            request.session.flush()
            messages.error(
                request,
                "Your cloud access token expired. Please log in again.",
            )
            return redirect("restaurant_login")

        if response.status_code == 403:
            messages.error(
                request,
                data.get(
                    "detail",
                    "Your cloud account is not permitted to make these changes.",
                ),
            )
            return redirect("restaurant_dashboard")

        if response.status_code == 404:
            messages.error(
                request,
                data.get(
                    "detail",
                    "The cloud restaurant profile could not be found.",
                ),
            )
            return redirect("restaurant_dashboard")

        if not response.ok:
            errors = (
                data.get("restaurant_errors")
                or data.get("user_errors")
                or data.get("detail")
                or "Could not save changes."
            )

            messages.error(request, str(errors))
            return redirect("restaurant_dashboard")

        # Store the updated cloud values in the local session.
        request.session["restaurant_user"] = data.get("user") or {}
        request.session["restaurant_profile"] = data.get("restaurant") or {}

        messages.success(
            request,
            data.get("detail", "Your changes were saved successfully."),
        )

    except requests.RequestException:
        logger.exception("Cloud restaurant profile update failed.")

        messages.error(
            request,
            "Could not connect to the cloud. Your changes were not saved.",
        )

    return redirect("restaurant_dashboard")


# ============================================================
# CLOUD LOGOUT
# ============================================================

@csrf_protect
@require_POST
def restaurant_logout(request):
    refresh_token = request.session.get("restaurant_refresh_token")
    access_token = request.session.get("restaurant_access_token")

    if refresh_token and access_token:
        try:
            response = requests.post(
                RESTAURANT_LOGOUT_API,
                json={"refresh": refresh_token},
                headers=cloud_headers(access_token),
                timeout=8,
            )

            if response.status_code not in (200, 400, 401):
                logger.warning(
                    "Cloud logout returned HTTP %s.",
                    response.status_code,
                )

        except requests.RequestException:
            # Clear the local session even if the cloud is unreachable.
            logger.warning(
                "Could not contact cloud API during logout.",
                exc_info=True,
            )

    request.session.flush()
    messages.success(request, "You have been logged out.")
    return redirect("restaurant_login")