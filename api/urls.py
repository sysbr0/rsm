


 
"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import *


urlpatterns = [
    path(
        "v1/auth/admin-login/",
        WaiterMobileLoginAPIView.as_view(),
        name="WaiterMobileLoginAPIView",
    ),
        path(
        "v1/manager/tables/",
        tables_dashboard_api,
        name="tables-dashboard-api",
    ),
    path(
            "v1/tables/<int:table_id>/",
            WaiterTableDetailView.as_view(),
            name="api-waiter-table-detail",
        ),
    path(
        "v1/tables/<int:table_id>/orders/",
        WaiterCreateOrderView.as_view(),
        name="api-waiter-order-create",
    ),
      path(
            "v1/tables/<int:table_id>/orders/items/<int:item_id>/",
            WaiterUpdateItemView.as_view(),
            name="api-waiter-item-update",
        ),
        path(
            "v1/tables/<int:table_id>/orders/print/",
            WaiterPrintPendingView.as_view(),
            name="api-waiter-order-print",
        ),
        path("v1/tables/<int:table_id>/invoice/",
              WaiterInvoiceView.as_view(),
              name="api-waiter-invoice",
),

    path(
        "v1/tables/<int:table_id>/orders/change-table/",
        WaiterChangeTableView.as_view(),
        name="api-waiter-change-table",
    ),



    # POST: Approve a waiter transfer request
    # Example: /api/waiter-changes/5/approve/
     path(
        "v1/tables/<int:table_id>/request-waiter/",
        RequestWaiterChangeView.as_view(),
        name="api_request_waiter_change",
    ),

    # 2. Approve/Deny the request (Waiter B or Manager does this)
    path(
        "v1/waiter-changes/<int:change_id>/resolve/",
        ApproveWaiterChangeView.as_view(),
        name="api_resolve_waiter_change",
    ),
    path(
    "v1/waiter-changes/pending/",
    PendingWaiterChangesView.as_view(),
    name="pending-waiter-changes",
),
    ]

