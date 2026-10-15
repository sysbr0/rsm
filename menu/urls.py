from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import *
from .api_views import (
    CategoryStatsAPIView,
    CategoryViewSet,
    ProductStatsAPIView,
    ProductViewSet,
)


router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="api-category")
router.register("products", ProductViewSet, basename="api-product")


urlpatterns = [
    # ============================================================
    # JSON API — stats routes MUST come BEFORE the router
    # (otherwise the router matches them as <pk> and returns 404)
    # ============================================================
    path(
        "api/categories/stats/",
        CategoryStatsAPIView.as_view(),
        name="api-category-stats",
    ),
    path(
        "api/products/stats/",
        ProductStatsAPIView.as_view(),
        name="api-product-stats",
    ),

    # Router-managed CRUD endpoints
    path("api/", include(router.urls)),

    # ============================================================
    # Category HTML pages
    # ============================================================
    path(
        "categories/",
        category_list_page,
        name="category_list",
    ),
    path(
        "categories/create/",
        category_create_page,
        name="category_create",
    ),
    path(
        "categories/<str:pk>/edit/",
        category_edit_page,
        name="category_edit",
    ),
    path(
        "categories/<str:pk>/delete/",
        category_delete_page,
        name="category_delete",
    ),

    # ============================================================
    # Product HTML pages
    # ============================================================
    path(
        "products/",
        product_list_page,
        name="product_list",
    ),
    path(
        "products/create/",
        product_create_page,
        name="product_create",
    ),
    path(
        "products/<str:pk>/edit/",
        product_edit_page,
        name="product_edit",
    ),
    path(
        "products/<str:pk>/delete/",
        product_delete_page,
        name="product_delete",
    ),
]