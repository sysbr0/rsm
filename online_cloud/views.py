
import json
import logging

import requests
import os
from django.conf import settings

from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.views import View

from menu.models import Category
from menu.category_sync import (
    publish_category,
    publish_unsynced_categories,
)

logger = logging.getLogger(__name__)


# ============================================================
# CLOUD API CONFIGURATION
# ============================================================

CLOUD_API_BASE = "https://admin.sysbr.net/api/restaurant"

RESTAURANT_LOGIN_API = f"{CLOUD_API_BASE}/login/"
RESTAURANT_ME_API = f"{CLOUD_API_BASE}/me/"
RESTAURANT_LOGOUT_API = f"{CLOUD_API_BASE}/logout/"

LOGIN_TEMPLATE = "online/account/login.html"
DASHBOARD_TEMPLATE = "online/dashboard.html"


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
    except (ValueError, json.JSONDecodeError, requests.exceptions.JSONDecodeError):
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

        # Store cloud user information.
        restaurant_user = data.get("user") or {}
        request.session["restaurant_user"] = restaurant_user

        # Store the restaurant profile.
        restaurant = data.get("restaurant") or {}
        request.session["restaurant_profile"] = restaurant

        # Store the restaurant profile ID and UUID.
        request.session["restaurant_profile_id"] = restaurant.get("id")
        request.session["restaurant_uuid"] = restaurant.get("uuid")

        logger.info(
            "Restaurant login successful. Profile ID: %s, UUID: %s",
            restaurant.get("id"),
            restaurant.get("uuid"),
        )

        # Persist a copy of the access token for management/CLI tools if configured.
        token_file = getattr(
            settings,
            "CLOUD_TOKEN_FILE",
            os.getenv("CLOUD_TOKEN_FILE"),
        )

        if token_file and access_token:
            try:
                parent = os.path.dirname(token_file)

                if parent:
                    os.makedirs(parent, exist_ok=True)

                with open(token_file, "w") as f:
                    f.write(access_token)

                try:
                    os.chmod(token_file, 0o600)
                except OSError:
                    pass

            except OSError:
                logger.exception(
                    "Could not write cloud token file %s",
                    token_file,
                )

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
            logger.warning(
                "Could not contact cloud API during logout.",
                exc_info=True,
            )

    # Clear local session, including restaurant ID and UUID.
    request.session.flush()

    messages.success(request, "You have been logged out.")
    return redirect("restaurant_login")








from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.views import View

from menu.models import Category, Product
from menu.category_sync import (
    publish_category,
    publish_unsynced_categories,
)
from menu.product_sync import (
    publish_product,
    publish_unsynced_products,
)


# ==========================================================
# COMBINED SYNC PAGE  (categories + products)
# ==========================================================

class CategorySyncPageView(View):
    """
    GET  /menu/sync/                     -> dashboard (categories + products)
    POST /menu/sync/                     -> sync ALL unsynced categories + products
    POST /menu/sync/category/<uuid>/     -> sync ONE category
    POST /menu/sync/product/<uuid>/      -> sync ONE product
    """

    template_name = "menu/sync_categories.html"

    # ------------------------------------------------------
    # GET
    # ------------------------------------------------------
    def get(self, request, category_uuid=None, product_uuid=None):
        unsynced_categories = Category.objects.filter(
            is_synced=False
        ).order_by("created_at")

        synced_categories = (
            Category.objects.filter(is_synced=True)
            .order_by("-last_synced_at")[:20]
        )

        unsynced_products = Product.objects.filter(
            is_synced=False
        ).order_by("created_at")

        synced_products = (
            Product.objects.filter(is_synced=True)
            .order_by("-last_synced_at")[:20]
        )

        return render(
            request,
            self.template_name,
            {
                # categories
                "unsynced_categories": unsynced_categories,
                "synced_categories": synced_categories,
                "unsynced_count": unsynced_categories.count(),

                # products
                "unsynced_products": unsynced_products,
                "synced_products": synced_products,
                "unsynced_product_count": unsynced_products.count(),
            },
        )

    # ------------------------------------------------------
    # POST
    # ------------------------------------------------------
    def post(self, request, category_uuid=None, product_uuid=None):

        # ---------- sync one category ----------
        if category_uuid:
            category = get_object_or_404(Category, uuid=category_uuid)
            success = publish_category(category)

            if success:
                messages.success(
                    request,
                    f"Category '{category.name}' synced successfully.",
                )
            else:
                messages.error(
                    request,
                    f"Failed to sync category '{category.name}'. "
                    f"Check server logs for details.",
                )
            return redirect(reverse("category-sync-page"))

        # ---------- sync one product ----------
        if product_uuid:
            product = get_object_or_404(Product, uuid=product_uuid)
            success = publish_product(product)

            if success:
                messages.success(
                    request,
                    f"Product '{product.name}' synced successfully.",
                )
            else:
                messages.error(
                    request,
                    f"Failed to sync product '{product.name}'. "
                    f"Check server logs for details.",
                )
            return redirect(reverse("category-sync-page"))

        # ---------- sync all ----------
        categories_published = publish_unsynced_categories()
        products_published = publish_unsynced_products()

        total = categories_published + products_published

        if total == 0:
            messages.info(
                request,
                "Nothing synced. Either there are no unsynced items, "
                "or all attempts failed — check logs.",
            )
        else:
            messages.success(
                request,
                f"Synced {categories_published} "
                f"categor{'y' if categories_published == 1 else 'ies'} "
                f"and {products_published} "
                f"product{'s' if products_published != 1 else ''}.",
            )

        return redirect(reverse("category-sync-page"))


# ==========================================================
# DEDICATED PRODUCT SYNC PAGE
# ==========================================================

class ProductSyncPageView(View):
    """
    GET  /menu/sync/products/            -> page with unsynced + recently synced products
    POST /menu/sync/products/            -> sync ALL unsynced, redirect back with flash
    POST /menu/sync/products/<uuid>/     -> sync ONE, redirect back with flash
    """

    template_name = "menu/sync_products.html"

    # ------------------------------------------------------
    # GET
    # ------------------------------------------------------
    def get(self, request, product_uuid=None):
        unsynced = Product.objects.filter(
            is_synced=False
        ).order_by("created_at")

        synced = (
            Product.objects.filter(is_synced=True)
            .order_by("-last_synced_at")[:20]
        )

        return render(
            request,
            self.template_name,
            {
                "unsynced_products": unsynced,
                "synced_products": synced,
                "unsynced_count": unsynced.count(),
            },
        )

    # ------------------------------------------------------
    # POST
    # ------------------------------------------------------
    def post(self, request, product_uuid=None):

        # ---------- sync one ----------
        if product_uuid:
            product = get_object_or_404(Product, uuid=product_uuid)
            success = publish_product(product)

            if success:
                messages.success(
                    request,
                    f"'{product.name}' synced successfully.",
                )
            else:
                messages.error(
                    request,
                    f"Failed to sync '{product.name}'. "
                    f"Check server logs for details.",
                )
            return redirect(reverse("product-sync-page"))

        # ---------- sync all ----------
        published = publish_unsynced_products()

        if published == 0:
            messages.info(
                request,
                "Nothing synced. Either no unsynced products, "
                "or all attempts failed — check logs.",
            )
        else:
            messages.success(
                request,
                f"Synced {published} product"
                f"{'s' if published != 1 else ''} successfully.",
            )

        return redirect(reverse("product-sync-page"))



from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View

from menu.category_sync import publish_all_categories
from menu.product_sync import publish_all_products



def sync_all(request):

    access_token = request.session.get("restaurant_access_token")
    

    
    restaurant_profile_id = request.session.get("restaurant_profile_id")
   


    



    
    

    if not access_token:
        messages.error(request, "Please log in to your cloud account.")
        return redirect("restaurant_login")

    """
    GET  /manager/online/sync/           -> combined dashboard (categories + products)
    POST /manager/online/sync/           -> Sync All Unsynced
    POST /manager/online/sync/  mode=full -> Full Refresh (force push everything)
    """

    # ------------------------------------------------------
    # POST — handle both sync modes
    # ------------------------------------------------------
    if request.method == "POST":
        mode = request.POST.get("mode", "unsynced")

        # ---------- FULL REFRESH ----------
        if mode == "full":
            c_pub, c_fail, c_total = publish_all_categories(
                token=access_token,
            )
            p_pub, p_fail, p_total = publish_all_products(
                token=access_token,
            )

            total_published = c_pub + p_pub
            total_failed = c_fail + p_fail
            total_items = c_total + p_total

            if total_items == 0:
                messages.info(
                    request,
                    "Nothing to refresh — there are no local items.",
                )
            elif total_failed == 0:
                messages.success(
                    request,
                    f"Full refresh complete: pushed {total_published} "
                    f"item{'s' if total_published != 1 else ''} "
                    f"({c_pub} categor"
                    f"{'y' if c_pub == 1 else 'ies'}, "
                    f"{p_pub} product"
                    f"{'s' if p_pub != 1 else ''}).",
                )
            else:
                messages.warning(
                    request,
                    f"Refresh pushed {total_published} of {total_items} "
                    f"items. {total_failed} failed — check server logs.",
                )

            return redirect(reverse("sync_all"))

        # ---------- SYNC ALL UNSYNCED ----------
        categories_published = publish_unsynced_categories(
            token=access_token,
        )
        products_published = publish_unsynced_products(
            token=access_token,
        )

        total = categories_published + products_published

        if total == 0:
            messages.info(
                request,
                "Nothing synced. Either there are no unsynced items, "
                "or all attempts failed — check logs.",
            )
        else:
            messages.success(
                request,
                f"Synced {categories_published} "
                f"categor{'y' if categories_published == 1 else 'ies'} "
                f"and {products_published} "
                f"product{'s' if products_published != 1 else ''}.",
            )

        return redirect(reverse("sync_all"))

    # ------------------------------------------------------
    # GET — render dashboard
    # ------------------------------------------------------
    unsynced_categories = Category.objects.filter(
        is_synced=False
    ).order_by("created_at")

    synced_categories = (
        Category.objects.filter(is_synced=True)
        .order_by("-last_synced_at")[:20]
    )

    unsynced_products = Product.objects.filter(
        is_synced=False
    ).order_by("created_at")

    synced_products = (
        Product.objects.filter(is_synced=True)
        .order_by("-last_synced_at")[:20]
    )

    return render(
        request,
        "menu/sync_all.html",
        {
            # categories
            "unsynced_categories": unsynced_categories,
            "synced_categories": synced_categories,
            "unsynced_count": unsynced_categories.count(),

            # products
            "unsynced_products": unsynced_products,
            "synced_products": synced_products,
            "unsynced_product_count": unsynced_products.count(),
        },
    )
import requests

from django.conf import settings
from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CLOUD_API_BASE_URL = getattr(
    settings,
    "CLOUD_API_BASE_URL",
    "https://admin.sysbr.net/api",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_cloud_headers(request):
    """Build the auth headers for the cloud API from the current session."""
    token = request.session.get("restaurant_access_token")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _cloud_error(response):
    """Short, template-friendly string from a cloud API error response."""
    try:
        data = response.json()
        if isinstance(data, dict):
            if "detail" in data:
                return str(data["detail"])
            parts = []
            for field, msgs in data.items():
                if isinstance(msgs, list):
                    parts.append(f"{field}: {', '.join(map(str, msgs))}")
                else:
                    parts.append(f"{field}: {msgs}")
            if parts:
                return "; ".join(parts)
    except ValueError:
        pass

    text = response.text.strip()
    if text.lower().startswith("<!doctype") or text.lower().startswith("<html"):
        return f"HTTP {response.status_code} from cloud API (see server logs)."
    return text[:300]


def _extract_list(data):
    """Accept either a bare list or a DRF paginated dict."""
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    if isinstance(data, list):
        return data
    return []


def _get_restaurant_uuid(request, error_message="No restaurant selected for this session."):
    uuid = request.session.get("restaurant_profile_id")
    if not uuid:
        django_messages.error(request, error_message)
    return uuid


def _collect_messages(request):
    """
    Pull every pending Django message into a plain list of dicts so the
    template can render them explicitly. Each item has:
        { 'tags': 'success' | 'error' | 'info' | 'warning', 'text': '...' }
    Reading the iterator drains the storage, which is what we want here —
    it prevents the base template from rendering them a second time.
    """
    collected = []
    for m in django_messages.get_messages(request):
        collected.append({
            "tags": m.tags or "info",
            "text": str(m),
        })
    return collected


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(["GET", "POST"])
def restaurant_languages_page(request):
    uuid = _get_restaurant_uuid(request)
    if not uuid:
        return redirect("restaurant_dashboard")

    api_url = f"{CLOUD_API_BASE_URL}/restaurants/{uuid}/languages/"
    headers = get_cloud_headers(request)
    error = None

    if request.method == "POST":
        action = request.POST.get("action", "create").strip()
        language_code = request.POST.get("language_code", "").strip()
        is_default = request.POST.get("is_default") == "true"
        is_active = request.POST.get("is_active") == "true"
        lang_id = request.POST.get("id", "").strip()

        payload = {
            "language_code": language_code,
            "is_default": is_default,
            "is_active": is_active,
        }

        try:
            if action == "create":
                response = requests.post(
                    api_url, json=payload, headers=headers, timeout=15,
                )
                success_msg = "Language added to the cloud."

            elif action == "update":
                if not lang_id:
                    error, response = "Missing language id for update.", None
                else:
                    response = requests.patch(
                        f"{api_url}{lang_id}/",
                        json=payload, headers=headers, timeout=15,
                    )
                    success_msg = "Language updated on the cloud."

            elif action == "toggle":
                if not lang_id:
                    error, response = "Missing language id for toggle.", None
                else:
                    response = requests.patch(
                        f"{api_url}{lang_id}/",
                        json={"is_active": is_active},
                        headers=headers, timeout=15,
                    )
                    success_msg = (
                        "Language activated." if is_active
                        else "Language deactivated."
                    )

            else:
                error, response = f"Unknown action: {action}", None

            if response is not None:
                if response.status_code in (200, 201):
                    django_messages.success(request, success_msg)
                elif response.status_code == 404:
                    error = "Language not found on the cloud."
                else:
                    error = (
                        f"Cloud API error ({response.status_code}): "
                        f"{_cloud_error(response)}"
                    )

        except requests.RequestException as exc:
            error = f"Could not connect to the cloud API: {exc}"

        if error is None:
            return redirect("restaurant_languages_page")

    languages = []
    try:
        response = requests.get(api_url, headers=headers, timeout=15)
        if response.ok:
            languages = _extract_list(response.json())
        else:
            error = (
                f"Could not load languages "
                f"({response.status_code}): {_cloud_error(response)}"
            )
    except requests.RequestException as exc:
        error = f"Could not connect to the cloud API: {exc}"
    except ValueError:
        error = "Cloud API returned an invalid response."

    return render(
        request,
        "online/translation/restaurant_languages.html",
        {
            "languages": languages,
            "error": error,
        },
    )


# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(["GET", "POST"])
def restaurant_translations_page(request):
    uuid = _get_restaurant_uuid(request)
    if not uuid:
        return redirect("restaurant_dashboard")

    translations_url = f"{CLOUD_API_BASE_URL}/restaurants/{uuid}/translations/"
    languages_url = f"{CLOUD_API_BASE_URL}/restaurants/{uuid}/languages/"

    headers = get_cloud_headers(request)
    error = None
    flash_messages = []

    # --------------------------- POST ---------------------------
    if request.method == "POST":
        payload = {
            "language_code": request.POST.get("language_code", "").strip(),
            "name": request.POST.get("name", "").strip(),
            "description": request.POST.get("description", "").strip(),
            "slogan": request.POST.get("slogan", "").strip(),
        }

        try:
            response = requests.post(
                translations_url, json=payload, headers=headers, timeout=15,
            )
            if response.status_code in (200, 201):
                django_messages.success(request, "Translation saved to the cloud.")
                return redirect("restaurant_translations_page")
            error = (
                f"Cloud API error ({response.status_code}): "
                f"{_cloud_error(response)}"
            )
        except requests.RequestException as exc:
            error = f"Could not connect to the cloud API: {exc}"

    # --------------------------- GET ---------------------------
    translations = []
    configured_languages = []

    try:
        response = requests.get(translations_url, headers=headers, timeout=15)
        if response.ok:
            translations = _extract_list(response.json())
        else:
            error = (
                f"Could not load translations "
                f"({response.status_code}): {_cloud_error(response)}"
            )
    except requests.RequestException as exc:
        error = f"Could not connect to the cloud API: {exc}"
    except ValueError:
        error = "Cloud API returned an invalid response."

    try:
        response = requests.get(languages_url, headers=headers, timeout=15)
        if response.ok:
            configured_languages = _extract_list(response.json())
    except (requests.RequestException, ValueError):
        pass

    translated_codes = {
        t.get("language_code")
        for t in translations
        if t.get("language_code")
    }

    available_languages = [
        lang for lang in configured_languages
        if lang.get("is_active") and lang.get("language_code") not in translated_codes
    ]

    # Drain pending Django messages into a template-friendly list, then
    # pass it explicitly. Because we've already consumed the iterator,
    # the base template's {% if messages %} block will render nothing —
    # so the flash shows up exactly once, in the spot this template chooses.
    flash_messages = _collect_messages(request)

    return render(
        request,
        "online/translation/restaurant_translations.html",
        {
            "translations": translations,
            "available_languages": available_languages,
            "configured_count": len(configured_languages),
            "error": error,
            "flash_messages": flash_messages,
        },
    )


    # ===========================================================================
# Categories
# ===========================================================================
@login_required
@require_http_methods(["GET", "POST"])
def categories_page(request):
    """List + create categories for the current restaurant."""
    uuid = _get_restaurant_uuid(request)
    if not uuid:
        return redirect("restaurant_dashboard")

    categories_url = f"{CLOUD_API_BASE_URL}/restaurants/{uuid}/categories/"
    headers = get_cloud_headers(request)
    error = None

    # --------------------------- POST: create ---------------------------
    if request.method == "POST":
        payload = {
            "name": request.POST.get("name", "").strip(),
            "slug": request.POST.get("slug", "").strip(),
            "description": request.POST.get("description", "").strip(),
            "sort_order": int(request.POST.get("sort_order") or 0),
            "is_active": request.POST.get("is_active") == "true",
            "is_published": request.POST.get("is_published") == "true",
        }

        try:
            response = requests.post(
                categories_url, json=payload, headers=headers, timeout=15,
            )
            if response.status_code in (200, 201):
                django_messages.success(request, "Category created on the cloud.")
                return redirect("categories_page")
            error = (
                f"Cloud API error ({response.status_code}): "
                f"{_cloud_error(response)}"
            )
        except requests.RequestException as exc:
            error = f"Could not connect to the cloud API: {exc}"

    # --------------------------- GET: list ---------------------------
    categories = []
    try:
        response = requests.get(categories_url, headers=headers, timeout=15)
        if response.ok:
            categories = _extract_list(response.json())
        else:
            error = (
                f"Could not load categories "
                f"({response.status_code}): {_cloud_error(response)}"
            )
    except requests.RequestException as exc:
        error = f"Could not connect to the cloud API: {exc}"
    except ValueError:
        error = "Cloud API returned an invalid response."

    flash_messages = _collect_messages(request)

    return render(
        request,
        "online/categories/categories.html",
        {
            "categories": categories,
            "error": error,
            "flash_messages": flash_messages,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def category_edit_page(request, category_id):
    """Edit or delete a single category."""
    uuid = _get_restaurant_uuid(request)
    if not uuid:
        return redirect("restaurant_dashboard")

    category_url = (
        f"{CLOUD_API_BASE_URL}/restaurants/{uuid}/categories/{category_id}/"
    )
    headers = get_cloud_headers(request)
    error = None

    # --------------------------- POST: update / delete ---------------------------
    if request.method == "POST":
        action = request.POST.get("action", "update").strip()

        try:
            if action == "delete":
                response = requests.delete(
                    category_url, headers=headers, timeout=15,
                )
                if response.status_code in (200, 204):
                    django_messages.success(request, "Category deleted.")
                    return redirect("categories_page")
                error = (
                    f"Cloud API error ({response.status_code}): "
                    f"{_cloud_error(response)}"
                )

            elif action == "update":
                payload = {
                    "name": request.POST.get("name", "").strip(),
                    "slug": request.POST.get("slug", "").strip(),
                    "description": request.POST.get("description", "").strip(),
                    "sort_order": int(request.POST.get("sort_order") or 0),
                    "is_active": request.POST.get("is_active") == "true",
                    "is_published": request.POST.get("is_published") == "true",
                }
                response = requests.patch(
                    category_url, json=payload, headers=headers, timeout=15,
                )
                if response.status_code in (200, 201):
                    django_messages.success(request, "Category updated.")
                    return redirect("category_edit_page", category_id=category_id)
                error = (
                    f"Cloud API error ({response.status_code}): "
                    f"{_cloud_error(response)}"
                )
            else:
                error = f"Unknown action: {action}"

        except requests.RequestException as exc:
            error = f"Could not connect to the cloud API: {exc}"

    # --------------------------- GET: fetch ---------------------------
    category = None
    try:
        response = requests.get(category_url, headers=headers, timeout=15)
        if response.ok:
            category = response.json()
        elif response.status_code == 404:
            error = "Category not found."
        else:
            error = (
                f"Could not load category "
                f"({response.status_code}): {_cloud_error(response)}"
            )
    except requests.RequestException as exc:
        error = f"Could not connect to the cloud API: {exc}"
    except ValueError:
        error = "Cloud API returned an invalid response."

    flash_messages = _collect_messages(request)

    return render(
        request,
        "online/categories/category_edit.html",
        {
            "category": category,
            "error": error,
            "flash_messages": flash_messages,
        },
    )


# ===========================================================================
# Category images
# ===========================================================================
@login_required
@require_http_methods(["GET", "POST"])
def category_images_page(request, category_id):
    """List + create images for a category."""
    uuid = _get_restaurant_uuid(request)
    if not uuid:
        return redirect("restaurant_dashboard")

    images_url = (
        f"{CLOUD_API_BASE_URL}"
        f"/restaurants/{uuid}/categories/{category_id}/images/"
    )
    category_url = (
        f"{CLOUD_API_BASE_URL}/restaurants/{uuid}/categories/{category_id}/"
    )
    headers = get_cloud_headers(request)
    error = None

    # --------------------------- POST: create ---------------------------
    if request.method == "POST":
        payload = {
            "image_url": request.POST.get("image_url", "").strip(),
            "alt_text": request.POST.get("alt_text", "").strip(),
            "sort_order": int(request.POST.get("sort_order") or 0),
            "is_primary": request.POST.get("is_primary") == "true",
        }

        try:
            response = requests.post(
                images_url, json=payload, headers=headers, timeout=15,
            )
            if response.status_code in (200, 201):
                django_messages.success(request, "Image added.")
                return redirect("category_images_page", category_id=category_id)
            error = (
                f"Cloud API error ({response.status_code}): "
                f"{_cloud_error(response)}"
            )
        except requests.RequestException as exc:
            error = f"Could not connect to the cloud API: {exc}"

    # --------------------------- GET: list + category header ---------------------------
    images = []
    category = None

    try:
        response = requests.get(images_url, headers=headers, timeout=15)
        if response.ok:
            images = _extract_list(response.json())
        else:
            error = (
                f"Could not load images "
                f"({response.status_code}): {_cloud_error(response)}"
            )
    except requests.RequestException as exc:
        error = f"Could not connect to the cloud API: {exc}"
    except ValueError:
        error = "Cloud API returned an invalid response."

    try:
        response = requests.get(category_url, headers=headers, timeout=15)
        if response.ok:
            category = response.json()
    except (requests.RequestException, ValueError):
        pass

    flash_messages = _collect_messages(request)

    return render(
        request,
        "online/categories/category_images.html",
        {
            "category": category,
            "category_id": category_id,
            "images": images,
            "error": error,
            "flash_messages": flash_messages,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def category_image_edit_page(request, category_id, image_id):
    """Edit / delete / set-primary on a single category image."""
    uuid = _get_restaurant_uuid(request)
    if not uuid:
        return redirect("restaurant_dashboard")

    image_url = (
        f"{CLOUD_API_BASE_URL}"
        f"/restaurants/{uuid}/categories/{category_id}/images/{image_id}/"
    )
    headers = get_cloud_headers(request)
    error = None

    # --------------------------- POST ---------------------------
    if request.method == "POST":
        action = request.POST.get("action", "update").strip()

        try:
            if action == "delete":
                response = requests.delete(
                    image_url, headers=headers, timeout=15,
                )
                if response.status_code in (200, 204):
                    django_messages.success(request, "Image deleted.")
                    return redirect(
                        "category_images_page", category_id=category_id
                    )
                error = (
                    f"Cloud API error ({response.status_code}): "
                    f"{_cloud_error(response)}"
                )

            elif action in ("update", "set_primary"):
                if action == "set_primary":
                    payload = {"is_primary": True}
                else:
                    payload = {
                        "image_url": request.POST.get("image_url", "").strip(),
                        "alt_text": request.POST.get("alt_text", "").strip(),
                        "sort_order": int(request.POST.get("sort_order") or 0),
                        "is_primary": request.POST.get("is_primary") == "true",
                    }

                response = requests.patch(
                    image_url, json=payload, headers=headers, timeout=15,
                )
                if response.status_code in (200, 201):
                    django_messages.success(
                        request,
                        "Primary image set." if action == "set_primary"
                        else "Image updated.",
                    )
                    return redirect(
                        "category_image_edit_page",
                        category_id=category_id,
                        image_id=image_id,
                    )
                error = (
                    f"Cloud API error ({response.status_code}): "
                    f"{_cloud_error(response)}"
                )
            else:
                error = f"Unknown action: {action}"

        except requests.RequestException as exc:
            error = f"Could not connect to the cloud API: {exc}"

    # --------------------------- GET ---------------------------
    image = None
    try:
        response = requests.get(image_url, headers=headers, timeout=15)
        if response.ok:
            image = response.json()
        elif response.status_code == 404:
            error = "Image not found."
        else:
            error = (
                f"Could not load image "
                f"({response.status_code}): {_cloud_error(response)}"
            )
    except requests.RequestException as exc:
        error = f"Could not connect to the cloud API: {exc}"
    except ValueError:
        error = "Cloud API returned an invalid response."

    flash_messages = _collect_messages(request)

    return render(
        request,
        "online/translation/category_image_edit.html",
        {
            "image": image,
            "category_id": category_id,
            "image_id": image_id,
            "error": error,
            "flash_messages": flash_messages,
        },
    )