from django.urls import path

from . import views
from .views import (
    CategorySyncPageView,
    ProductSyncPageView,
 

)
from .api_view import (
    CategorySyncAPIView,
    ProductSyncAPIView,
    CombinedSyncAPIView,
)

urlpatterns = [
    # ======================================================
    # AUTH / DASHBOARD
    # ======================================================
    path(
        "login/",
        views.restaurant_login,
        name="restaurant_login",
    ),
    path(
        "dashboard/",
        views.restaurant_dashboard,
        name="restaurant_dashboard",
    ),
    path(
        "logout/",
        views.restaurant_logout,
        name="restaurant_logout",
    ),
    path(
        "online/profile/save/",
        views.restaurant_profile_update,
        name="restaurant_profile_update",
    ),

    # ======================================================
    # HTML — COMBINED SYNC PAGE (categories + products)
    # ======================================================

    path("sync/",views.sync_all,name="sync_all"),
    path(
        "sync/categories/",
        CategorySyncPageView.as_view(),
        name="category-sync-page",
    ),
    path(
        "sync/category/<uuid:category_uuid>/",
        CategorySyncPageView.as_view(),
        name="category-sync-one",
    ),
    path(
        "sync/product/<uuid:product_uuid>/",
        CategorySyncPageView.as_view(),
        name="product-sync-one",
    ),

    # ======================================================
    # HTML — DEDICATED PRODUCT SYNC PAGE
    # ======================================================
    path(
        "sync/products/",
        ProductSyncPageView.as_view(),
        name="product-sync-page",
    ),
    path(
        "sync/products/<uuid:product_uuid>/",
        ProductSyncPageView.as_view(),
        name="product-sync-one-page",
    ),

    # ======================================================
    # API — CATEGORIES
    # ======================================================
    path(
        "api/sync/categories/",
        CategorySyncAPIView.as_view(),
        name="api-category-sync-all",
    ),
    path(
        "api/sync/categories/<uuid:category_uuid>/",
        CategorySyncAPIView.as_view(),
        name="api-category-sync-one",
    ),

    # ======================================================
    # API — PRODUCTS
    # ======================================================
    path(
        "api/sync/products/",
        ProductSyncAPIView.as_view(),
        name="api-product-sync-all",
    ),
    path(
        "api/sync/products/<uuid:product_uuid>/",
        ProductSyncAPIView.as_view(),
        name="api-product-sync-one",
    ),

    # ======================================================
    # API — COMBINED (categories + products)
    # ======================================================
    path("sync/", CombinedSyncAPIView.as_view(),name="api-sync-all",),
    path("api/sync/all/<uuid:entity_uuid>/",CombinedSyncAPIView.as_view(), name="api-sync-all-one",),

    path("language/",views.restaurant_languages_page,name="restaurant_languages_page"),
    path("translation/",views.restaurant_translations_page,name="restaurant_translations_page"),



     # Categories
    path("categories/",views.categories_page,name="categories_page",),
    path("categories/<uuid:category_id>/edit/",views.category_edit_page,name="category_edit_page",),

    # Category images
    path("categories/<uuid:category_id>/images/",views.category_images_page, name="category_images_page",),
    path("categories/<uuid:category_id>/images/<uuid:image_id>/edit/",views.category_image_edit_page,name="category_image_edit_page",),


]