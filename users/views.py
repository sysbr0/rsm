from django.core.serializers import python
from django.shortcuts import render

# Create your views here.
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.shortcuts import redirect, render
from django.template.backends import django

from rest_framework.generics import ListAPIView
from .models import User, UserRole, UserState
from .serializers import WorkingWaiterSerializer

from django.contrib.auth.decorators import login_required

from .models import *



def _login_user(request, allowed_roles, redirect_url, template_name):
    if request.user.is_authenticated:
        return redirect(redirect_url)

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is None:
            messages.error(request, "Invalid username or password.")
            return render(request, template_name)

        if user.role not in allowed_roles:
            messages.error(
                request,
                "You are not allowed to login from this page.",
            )
            return render(request, template_name)

        if not user.is_active:
            messages.error(request, "Your account is inactive.")
            return render(request, template_name)

        login(request, user)
        return redirect(redirect_url)

    return render(request, template_name)


def admin_manager_login(request):
    return _login_user(
        request=request,
        allowed_roles=["ADMIN", "MANAGER"],
        redirect_url="/manager/",
        template_name="users/login_admin.html",
    )


def waiter_login(request):
    return _login_user(
        request=request,
        allowed_roles=["WAITER"],
        redirect_url="/waiter/",
        template_name="users/login_waiter.html",
    )


def employee_login(request):
    return _login_user(
        request=request,
        allowed_roles=["CASHIER", "KITCHEN"],
        redirect_url="/employee/",
        template_name="users/login_employee.html",
    )



from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny


# ============================================================
# NORMAL WEB LOGIN
# ============================================================

def admin_login(request):

    if request.method == "POST":

        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is None:
            return render(
                request,
                "users/login_admin.html",
                {
                    "error": "Invalid username or password."
                },
            )

        # Allow ADMIN and MANAGER
        if user.role not in ["ADMIN", "MANAGER"]:
            return render(
                request,
                "users/login_admin.html",
                {
                    "error": (
                        "You do not have permission "
                        "to access this panel."
                    )
                },
            )

        # Create Django session
        login(request, user)

        # Successful login
        return redirect("/manager/tables/")

    return render(
        request,
        "users/login_admin.html"
    )


# ============================================================
# ADMIN LOGIN API
# ============================================================

class AdminLoginAPIView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        username = request.data.get(
            "username",
            ""
        ).strip()

        password = request.data.get(
            "password",
            ""
        )


        # ----------------------------------------
        # Validate input
        # ----------------------------------------

        if not username or not password:

            return Response(
                {
                    "success": False,
                    "message": "Username and password are required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


        # ----------------------------------------
        # Authenticate
        # ----------------------------------------

        user = authenticate(
            request,
            username=username,
            password=password,
        )


        # ----------------------------------------
        # Invalid credentials
        # ----------------------------------------

        if user is None:

            return Response(
                {
                    "success": False,
                    "message": "Invalid username or password.",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )


        # ----------------------------------------
        # Check role
        # ----------------------------------------

        if user.role not in [
            "ADMIN",
            "MANAGER",
        ]:

            return Response(
                {
                    "success": False,
                    "message": (
                        "You do not have permission "
                        "to access this panel."
                    ),
                },
                status=status.HTTP_403_FORBIDDEN,
            )


        # ----------------------------------------
        # Login / Django session
        # ----------------------------------------

        login(
            request,
            user
        )


        # ----------------------------------------
        # Success
        # ----------------------------------------

        return Response(
            {
                "success": True,
                "message": "Login successful.",

                "user": {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role,
                },

                "redirect": "/manager/tables/",
            },
            status=status.HTTP_200_OK,
        )



def index_view(request):
    #if request.user.is_authenticated:
        # Redirect authenticated users to their dashboard according to role
      #  if request.user.role == "ADMIN" or request.user.role == "MANAGER":
         #   return redirect('admin_tables')
        
    # Render main selection landing page for unauthenticated users
    return render(request, 'index.html')



class WorkingWaitersAPIView(ListAPIView):
    serializer_class = WorkingWaiterSerializer

    def get_queryset(self):
        return User.objects.filter(
            role=UserRole.WAITER,
            state=UserState.WORKING,
            is_active=True,
        )





@login_required
def manager_attendance_page(request):
    return render(request, "ui/attendance.html")





from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone

from .models import Attendance
from orders.models import Order, OrderStatus


User = get_user_model()


ACTIVE_WAITER_ORDER_STATUSES = (
    OrderStatus.OPEN,
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.SERVED,
)


@login_required
def waiter_dashboard(request):
    # Only managers and admins can view the team dashboard.
    if not (
        request.user.is_superuser
        or getattr(request.user, "role", "") in ("MANAGER", "ADMIN")
    ):
        return HttpResponseForbidden(
            "You do not have permission to view the waiter dashboard."
        )

    today = timezone.localdate()
    current_tz = timezone.get_current_timezone()

    start_datetime = timezone.make_aware(
        datetime.combine(today, time.min),
        current_tz,
    )
    end_datetime = timezone.make_aware(
        datetime.combine(today + timedelta(days=1), time.min),
        current_tz,
    )

    waiters = User.objects.filter(
        role="WAITER"
    ).exclude(
    state="STOPPED"
).order_by("full_name", "username")

    waiter_cards = []

    for waiter in waiters:
        # Today's attendance sessions.
        today_sessions = Attendance.objects.filter(
            user=waiter,
            check_in__gte=start_datetime,
            check_in__lt=end_datetime,
        ).order_by("-check_in")

        # Most recent active attendance session, if any.
        active_session = Attendance.objects.filter(
            user=waiter,
            check_out__isnull=True,
        ).order_by("-check_in").first()

        # Most recent session started today, for today's login time.
        today_session = today_sessions.first()

        # Orders created today and assigned to this waiter.
        today_orders = Order.objects.filter(
            waiter=waiter,
            created_at__gte=start_datetime,
            created_at__lt=end_datetime,
        )

        # Current tables the waiter is serving.
        active_orders = Order.objects.filter(
            waiter=waiter,
            status__in=ACTIVE_WAITER_ORDER_STATUSES,
        ).select_related("table").order_by("table_id")

        # A waiter can have multiple active orders on one table.
        current_tables = {}
        for order in active_orders:
            current_tables[order.table_id] = {
                "id": order.table_id,
                "name": str(order.table),
                "orders_count": current_tables.get(
                    order.table_id, {}
                ).get("orders_count", 0) + 1,
            }

        # Number of distinct tables served today.
        tables_served_today = (
            today_orders
            .values("table_id")
            .distinct()
            .count()
        )

        # Calculate worked time for today's attendance sessions.
        worked_seconds = 0

        for session in today_sessions:
            end_time = session.check_out or timezone.now()
            worked_seconds += max(
                0,
                int((end_time - session.check_in).total_seconds()),
            )

        worked_hours = worked_seconds // 3600
        worked_minutes = (worked_seconds % 3600) // 60

        is_working = active_session is not None

        waiter_cards.append({
            "id": waiter.pk,
            "name": (
                getattr(waiter, "full_name", None)
                or waiter.get_username()
            ),
            "username": waiter.get_username(),
            "is_working": is_working,
            "check_in": (
                active_session.check_in
                if active_session
                else (
                    today_session.check_in
                    if today_session
                    else None
                )
            ),
            "check_out": (
                today_session.check_out
                if today_session and not is_working
                else None
            ),
            "worked_time": f"{worked_hours:02d}:{worked_minutes:02d}",
            "current_tables": list(current_tables.values()),
            "current_tables_count": len(current_tables),
            "tables_served_today": tables_served_today,
            "total_orders_today": today_orders.count(),
            "active_orders_count": active_orders.count(),
        })

    context = {
        "waiters": waiter_cards,
        "today": today,
        "total_waiters": len(waiter_cards),
        "working_waiters": sum(
            1 for waiter in waiter_cards if waiter["is_working"]
        ),
        "idle_waiters": sum(
            1 for waiter in waiter_cards
            if waiter["is_working"] and not waiter["current_tables_count"]
        ),
        "total_tables_served": sum(
            waiter["tables_served_today"] for waiter in waiter_cards
        ),
        "total_orders_today": sum(
            waiter["total_orders_today"] for waiter in waiter_cards
        ),
    }

    return render(
        request,
        "users/waiter_dashboard.html",
        context,
    )

import json

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import DayOffRequest, DayOffStatus, UserRole


def is_manager(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.role in [UserRole.MANAGER, UserRole.ADMIN]
    )


def api_error(message, status=400):
    return JsonResponse(
        {
            "success": False,
            "message": message,
        },
        status=status,
    )


def get_employee_name(user):
    return (
        getattr(user, "full_name", None)
        or user.get_full_name()
        or user.username
    )


def day_off_request_to_dict(day_off):
    user = day_off.user
    reviewer = day_off.reviewed_by

    return {
        "id": day_off.pk,
        "user_id": user.pk,
        "employee_name": get_employee_name(user),
        "username": user.username,
        "date": day_off.date.isoformat() if day_off.date else None,
        "reason": getattr(day_off, "reason", ""),
        "status": day_off.status,
        "reviewed_by": (
            get_employee_name(reviewer) if reviewer else None
        ),
        "reviewed_at": (
            day_off.reviewed_at.isoformat()
            if day_off.reviewed_at
            else None
        ),
        "review_note": getattr(day_off, "review_note", ""),
    }


# ---------------------------------------------------------
# HTML PAGE
# Keep this as the only view that renders the HTML template.
# ---------------------------------------------------------

@login_required
@user_passes_test(is_manager)
def day_off_dashboard(request):
    return render(
        request,
        "attendance/day_off_dashboard.html",
    )


# ---------------------------------------------------------
# API: GET day-off requests and summary counts
# GET /api/v1/manager/day-off-requests/
# GET /api/v1/manager/day-off-requests/?status=PENDING
# ---------------------------------------------------------
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET


@require_GET
def manager_day_off_requests_api(request):
    if not request.user.is_authenticated:
        return api_error("Authentication required.", 401)

    if not is_manager(request.user):
        return api_error("Permission denied.", 403)

    # ---------------------------------------------------------
    # Filters
    # ---------------------------------------------------------
    filter_status = request.GET.get("status", "ALL").upper()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    valid_statuses = [
        DayOffStatus.PENDING,
        DayOffStatus.APPROVED,
        DayOffStatus.REJECTED,
    ]

    if filter_status != "ALL" and filter_status not in valid_statuses:
        return api_error("Invalid status filter.")

    # ---------------------------------------------------------
    # Validate date range
    # ---------------------------------------------------------
    from datetime import date

    parsed_date_from = None
    parsed_date_to = None

    if date_from:
        try:
            parsed_date_from = date.fromisoformat(date_from)
        except ValueError:
            return api_error(
                "Invalid date_from. Use YYYY-MM-DD."
            )

    if date_to:
        try:
            parsed_date_to = date.fromisoformat(date_to)
        except ValueError:
            return api_error(
                "Invalid date_to. Use YYYY-MM-DD."
            )

    if (
        parsed_date_from
        and parsed_date_to
        and parsed_date_from > parsed_date_to
    ):
        return api_error(
            "The start date cannot be after the end date."
        )

    # ---------------------------------------------------------
    # Requests queryset
    # ---------------------------------------------------------
    requests_qs = (
        DayOffRequest.objects
        .select_related("user", "reviewed_by")
        .order_by("-date", "-pk")
    )

    if filter_status != "ALL":
        requests_qs = requests_qs.filter(
            status=filter_status
        )

    if parsed_date_from:
        requests_qs = requests_qs.filter(
            date__gte=parsed_date_from
        )

    if parsed_date_to:
        requests_qs = requests_qs.filter(
            date__lte=parsed_date_to
        )

    # ---------------------------------------------------------
    # Summary counts (not affected by the filters)
    # ---------------------------------------------------------
    today = timezone.localdate()

    all_requests = DayOffRequest.objects.all()

    pending_count = all_requests.filter(
        status=DayOffStatus.PENDING
    ).count()

    approved_count = all_requests.filter(
        status=DayOffStatus.APPROVED
    ).count()

    rejected_count = all_requests.filter(
        status=DayOffStatus.REJECTED
    ).count()

    today_off_count = (
        all_requests.filter(
            date=today,
            status=DayOffStatus.APPROVED,
        )
        .values("user_id")
        .distinct()
        .count()
    )

    # ---------------------------------------------------------
    # Response
    # ---------------------------------------------------------
    return JsonResponse({
        "success": True,
        "results": [
            day_off_request_to_dict(item)
            for item in requests_qs
        ],
        "count": requests_qs.count(),
        "filters": {
            "status": filter_status,
            "date_from": date_from or None,
            "date_to": date_to or None,
        },
        "summary": {
            "pending_count": pending_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "today_off_count": today_off_count,
        },
        "today": today.isoformat(),
    })
# ---------------------------------------------------------
# API: APPROVE OR REJECT A REQUEST
# POST /api/v1/manager/day-off-requests/<id>/review/
#
# JSON:
# {
#     "status": "APPROVED",
#     "review_note": "Approved"
# }
# ---------------------------------------------------------

@require_POST
def review_day_off_request_api(request, request_id):
    if not request.user.is_authenticated:
        return api_error("Authentication required.", 401)

    if not is_manager(request.user):
        return api_error("Permission denied.", 403)

    # Accept JSON requests and regular form submissions.
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return api_error("Invalid JSON body.")
    else:
        data = request.POST

    new_status = str(
        data.get("status", data.get("action", ""))
    ).strip().upper()

    # Also accept the old form values: approve / reject.
    if new_status == "APPROVE":
        new_status = DayOffStatus.APPROVED
    elif new_status == "REJECT":
        new_status = DayOffStatus.REJECTED

    if new_status not in [
        DayOffStatus.APPROVED,
        DayOffStatus.REJECTED,
    ]:
        return api_error(
            "Status must be APPROVED or REJECTED."
        )

    review_note = str(
        data.get("review_note", "")
    ).strip()

    with transaction.atomic():
        day_off = get_object_or_404(
            DayOffRequest.objects.select_for_update(),
            pk=request_id,
        )

        if day_off.status != DayOffStatus.PENDING:
            return api_error(
                "This request has already been reviewed.",
                409,
            )

        day_off.status = new_status
        day_off.reviewed_by = request.user
        day_off.reviewed_at = timezone.now()
        day_off.review_note = review_note

        day_off.save(update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
        ])

    day_off.refresh_from_db()
    day_off = (
        DayOffRequest.objects
        .select_related("user", "reviewed_by")
        .get(pk=day_off.pk)
    )

    return JsonResponse({
        "success": True,
        "message": (
            "Day-off request approved."
            if new_status == DayOffStatus.APPROVED
            else "Day-off request rejected."
        ),
        "request": day_off_request_to_dict(day_off),
    })
