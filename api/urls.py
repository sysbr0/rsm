


 
"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import *

from users.views import *



urlpatterns = [
    path("v1/auth/admin-login/",
        WaiterMobileLoginAPIView.as_view(),
        name="WaiterMobileLoginAPIView",
    ),
    path("v1/auth/me/", current_user_profile, name="current_user_profile"),

    path("v1/manager/tables/",tables_dashboard_api, name="tables-dashboard-api", ),
    path("v1/tables/<int:table_id>/", WaiterTableDetailView.as_view(),name="api-waiter-table-detail", ),
    path( "v1/tables/<int:table_id>/orders/", WaiterCreateOrderView.as_view(),  name="api-waiter-order-create", ),
    path("v1/tables/<int:table_id>/orders/items/<int:item_id>/",
            WaiterUpdateItemView.as_view(),name="api-waiter-item-update",  ),
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
    path(
        "v1/working-waiters/",
        WorkingWaitersAPIView.as_view(),
        name="working-waiters",
    ),

       path(
        "v1/attendance/",
        ManagerAttendanceAPI.as_view(),
        name="manager_attendance_api",
    ),

    path(
        "v1/attendance/<int:user_id>/check-in/",
        attendance_check_in,
        name="attendance_check_in",
    ),
    path(
        "v1/attendance/<int:user_id>/check-out/",
        attendance_check_out,
        name="attendance_check_out",
    ),

    path(
        "v2/attendance/<int:user_id>/calendar/",
        employee_attendance_calendar_api,
        name="employee_attendance_calendar_api",
    ),
    path(
        "v2/attendance/<int:user_id>/day/",
        employee_attendance_day_api,
        name="employee_attendance_day_api",
    ),

     path(
        "v1/attendance/<int:user_id>/calendar/",
        EmployeeAttendanceCalendarAPI.as_view(),
        name="employee_attendance_calendar_api",
    ),
    path(
        "v1/attendance/<int:user_id>/day/",
        EmployeeAttendanceDayAPI.as_view(),
        name="employee_attendance_day_api",
    ),
    #employe 
    
    # API: list and filter requests
    path(
        "v1/manager/day-off-requests/",
        manager_day_off_requests_api,
        name="manager_day_off_requests_api",
    ),

    # API: approve or reject a request
    path(
        "v1/manager/day-off-requests/<int:request_id>/review/",
        review_day_off_request_api,
        name="review_day_off_request_api",
    ),
    path(
    "v1/manager/day-off-requests/<int:request_id>/review/",
    review_day_off_request,
),

        path(
        "v1/employee/day-off-requests/",
        EmployeeDayOffRequestsAPI.as_view(),
        name="employee-day-off-requests",
    ),

#frm the user
    path("v2/manager/attendance/",manager_attendance_api, name="manager_attendance_api", ),
   
    ]

