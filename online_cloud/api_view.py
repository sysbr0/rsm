import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated  # adjust as needed
from django.contrib import messages as django_messages
from django.conf import settings
from django.http import JsonResponse
from menu.models import Category, Product

import json
from collections import Counter

import requests

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.shortcuts import render, redirect
from django.contrib import messages as django_messages



from menu.category_sync import (
    publish_category,
    publish_unsynced_categories,
)
from menu.product_sync import (
    publish_product,
    publish_unsynced_products,
)

logger = logging.getLogger(__name__)




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





# ==========================================================
# CATEGORY SYNC API
# ==========================================================

class CategorySyncAPIView(APIView):
    """
    POST /api/sync/categories/            -> sync all unsynced categories
    POST /api/sync/categories/<uuid>/     -> sync one category
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, category_uuid=None):

        # ---------- sync one ----------
        if category_uuid:
            try:
                category = Category.objects.get(uuid=category_uuid)
            except Category.DoesNotExist:
                return Response(
                    {"success": False, "error": "Category not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            success = publish_category(category)

            return Response(
                {
                    "success": success,
                    "entity_type": "CATEGORY",
                    "uuid": str(category.uuid),
                    "name": category.name,
                    "message": (
                        "Category synchronized successfully."
                        if success
                        else "Category synchronization failed. "
                             "Check server logs."
                    ),
                },
                status=(
                    status.HTTP_200_OK
                    if success
                    else status.HTTP_502_BAD_GATEWAY
                ),
            )

        # ---------- sync all ----------
        published = publish_unsynced_categories()

        return Response(
            {
                "success": True,
                "entity_type": "CATEGORY",
                "published": published,
                "message": (
                    f"Synced {published} categor"
                    f"{'y' if published == 1 else 'ies'}."
                ),
            },
            status=status.HTTP_200_OK,
        )


# ==========================================================
# PRODUCT SYNC API
# ==========================================================

class ProductSyncAPIView(APIView):
    """
    POST /api/sync/products/            -> sync all unsynced products
    POST /api/sync/products/<uuid>/     -> sync one product
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, product_uuid=None):

        # ---------- sync one ----------
        if product_uuid:
            try:
                product = Product.objects.get(uuid=product_uuid)
            except Product.DoesNotExist:
                return Response(
                    {"success": False, "error": "Product not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            success = publish_product(product)

            return Response(
                {
                    "success": success,
                    "entity_type": "PRODUCT",
                    "uuid": str(product.uuid),
                    "name": product.name,
                    "sku": product.sku,
                    "message": (
                        "Product synchronized successfully."
                        if success
                        else "Product synchronization failed. "
                             "Check server logs."
                    ),
                },
                status=(
                    status.HTTP_200_OK
                    if success
                    else status.HTTP_502_BAD_GATEWAY
                ),
            )

        # ---------- sync all ----------
        published = publish_unsynced_products()

        return Response(
            {
                "success": True,
                "entity_type": "PRODUCT",
                "published": published,
                "message": (
                    f"Synced {published} product"
                    f"{'s' if published != 1 else ''}."
                ),
            },
            status=status.HTTP_200_OK,
        )


# ==========================================================
# COMBINED SYNC API (categories + products)
# ==========================================================

class CombinedSyncAPIView(APIView):
    """
    POST /api/sync/all/            -> sync all unsynced (categories + products)
    POST /api/sync/all/<uuid>/     -> ambiguous: requires ?type=category|product
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, entity_uuid=None):

        # ---------- sync one ----------
        if entity_uuid:
            entity_type = (
                request.query_params.get("type")
                or request.data.get("type")
                or ""
            ).strip().lower()

            if entity_type == "category":
                try:
                    category = Category.objects.get(uuid=entity_uuid)
                except Category.DoesNotExist:
                    return Response(
                        {"success": False, "error": "Category not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                success = publish_category(category)

                return Response(
                    {
                        "success": success,
                        "entity_type": "CATEGORY",
                        "uuid": str(category.uuid),
                        "name": category.name,
                        "message": (
                            "Category synchronized successfully."
                            if success
                            else "Category synchronization failed."
                        ),
                    },
                    status=(
                        status.HTTP_200_OK
                        if success
                        else status.HTTP_502_BAD_GATEWAY
                    ),
                )

            if entity_type == "product":
                try:
                    product = Product.objects.get(uuid=entity_uuid)
                except Product.DoesNotExist:
                    return Response(
                        {"success": False, "error": "Product not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                success = publish_product(product)

                return Response(
                    {
                        "success": success,
                        "entity_type": "PRODUCT",
                        "uuid": str(product.uuid),
                        "name": product.name,
                        "message": (
                            "Product synchronized successfully."
                            if success
                            else "Product synchronization failed."
                        ),
                    },
                    status=(
                        status.HTTP_200_OK
                        if success
                        else status.HTTP_502_BAD_GATEWAY
                    ),
                )

            return Response(
                {
                    "success": False,
                    "error": (
                        "Missing or invalid ?type= parameter. "
                        "Use type=category or type=product."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------- sync all ----------
        categories_published = publish_unsynced_categories()
        products_published = publish_unsynced_products()

        return Response(
            {
                "success": True,
                "categories": {
                    "published": categories_published,
                },
                "products": {
                    "published": products_published,
                },
                "total_published": (
                    categories_published + products_published
                ),
                "message": (
                    f"Synced {categories_published} "
                    f"categor{'y' if categories_published == 1 else 'ies'} "
                    f"and {products_published} "
                    f"product{'s' if products_published != 1 else ''}."
                ),
            },
            status=status.HTTP_200_OK,
        )








# menu/views.py (or wherever ProductSyncAPIView lives)
import logging

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status


logger = logging.getLogger(__name__)


class ProductPriceRefreshAPIView(APIView):
    """
    POST /api/sync/products/refresh-prices/
    Force-republishes every product to the cloud so prices are refreshed.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            token = get_cloud_token()
            if not token:
                return Response(
                    {"success": False, "error": "Cloud token is not configured."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            published, failed, total = publish_all_products(token=token)

        except ValueError as exc:
            # Missing CLOUD_API_URL / RESTAURANT_UUID
            logger.error("Price refresh aborted: %s", exc)
            return Response(
                {"success": False, "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception:
            logger.exception("Unexpected error during price refresh.")
            return Response(
                {"success": False, "error": "Unexpected error. Check server logs."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        success = failed == 0
        return Response(
            {
                "success": success,
                "entity_type": "PRODUCT",
                "total": total,
                "published": published,
                "failed": failed,
                "message": (
                    f"Refreshed {published} product"
                    f"{'s' if published != 1 else ''} online."
                    if success
                    else f"Refreshed {published} of {total}; {failed} failed."
                ),
            },
            status=status.HTTP_200_OK if success else status.HTTP_207_MULTI_STATUS,
        )