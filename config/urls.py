
"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from users.views import index_view


urlpatterns = [
    path("admin/", admin.site.urls),
    # path("manu/", include("menu.urls")),
    path("users/", include("users.urls")),
    path("", index_view, name="index_view"),
     path("orders/", include("orders.urls")),
    # path("printers/", include("printers.urls")),
    # path("tables/", include("tables.urls")),
    path("manager/", include("ui.urls")),
    # path("licensing/", include("licensing.urls")),
    # path("api/", include("api.urls")),
    path("financial/", include("Financial.urls")),
]

# Serve uploaded files during local development.
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )