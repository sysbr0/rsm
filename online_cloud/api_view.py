import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated  # adjust as needed

from menu.models import Category, Product
from menu.category_sync import (
    publish_category,
    publish_unsynced_categories,
)
from menu.product_sync import (
    publish_product,
    publish_unsynced_products,
)

logger = logging.getLogger(__name__)


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





