from django.core.serializers import python
# Create your views here.
from django.contrib.auth import authenticate, login
from django.contrib import messages
from rest_framework.generics import ListAPIView
from .models import User, UserRole, UserState
from .serializers import WorkingWaiterSerializer
from django.contrib.auth.decorators import login_required
from .models import *
import json
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render ,redirect
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST



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


from datetime import date


from datetime import date

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET



# =========================================================
# API: LIST MANAGER DAY-OFF REQUESTS
# GET /api/v1/manager/day-off-requests/
# =========================================================
from datetime import date

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import JsonResponse
from django.utils.dateparse import parse_date

from .models import DayOffRequest, DayOffStatus

# Pagination defaults (must match the frontend PAGE_SIZE = 20)
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def day_off_request_to_dict(item):
    """Converts a DayOffRequest instance into a dictionary."""
    return {
        "id": item.id,
        "user_id": item.user_id,
        "username": item.user.get_username(),
        "date": item.date.isoformat(),
        "reason": item.reason,
        "status": item.status,
        "reviewed_by_id": item.reviewed_by_id,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "review_note": item.review_note,
        "created_at": item.created_at.isoformat(),
    }


def _get_positive_int(value, default, maximum=None):
    """Safely parse a positive int from query params."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 1:
        return default
    if maximum is not None and parsed > maximum:
        return maximum
    return parsed


def manager_day_off_requests_api(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "error": "Authentication required."},
            status=401,
        )

    today = date.today()

    # --- Base queryset by permissions ---
    # Staff/managers see all requests; regular users see only their own.
    if request.user.is_staff:
        base_qs = DayOffRequest.objects.all().select_related(
            "user", "reviewed_by"
        )
    else:
        base_qs = DayOffRequest.objects.filter(user=request.user).select_related(
            "user", "reviewed_by"
        )
    requests_qs = base_qs
    # --- 1. Status filter ---
    filter_status = request.GET.get("status", "").strip().upper()
    valid_statuses = [choice[0] for choice in DayOffStatus.choices]

    if filter_status in valid_statuses:
        requests_qs = requests_qs.filter(status=filter_status)
    else:
        filter_status = None  # Reset if empty or invalid

    # --- 2. Date range filter ---
    date_from_str = request.GET.get("date_from", "").strip()
    date_to_str = request.GET.get("date_to", "").strip()

    date_from = parse_date(date_from_str) if date_from_str else None
    date_to = parse_date(date_to_str) if date_to_str else None

    # Invalid strings silently become None; keep them out of the filter.
    if date_from:
        requests_qs = requests_qs.filter(date__gte=date_from)
    if date_to:
        requests_qs = requests_qs.filter(date__lte=date_to)

    # Stable ordering so pages don't shuffle between requests.
    # Newest first — matches the "review queue" UX in the modal.
    requests_qs = requests_qs.order_by("date", "created_at", "id")
    # --- 3. Pagination ---
    page_size = _get_positive_int(
        request.GET.get("page_size"), DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
    )
    page_number = _get_positive_int(request.GET.get("page"), 1)

    paginator = Paginator(requests_qs, page_size)
    total_count = paginator.count
    total_pages = paginator.num_pages if total_count else 1

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        # If the requested page is out of range, return the last page.
        page_obj = paginator.page(total_pages)

    # --- 4. Summary metrics (scope = base queryset, ignoring active filters) ---
    pending_count = base_qs.filter(status=DayOffStatus.PENDING).count()
    approved_count = base_qs.filter(status=DayOffStatus.APPROVED).count()
    rejected_count = base_qs.filter(status=DayOffStatus.REJECTED).count()
    today_off_count = base_qs.filter(
        status=DayOffStatus.APPROVED, date=today
    ).count()

    # --- 5. Final JSON response ---
    return JsonResponse(
        {
            "success": True,
            "results": [
                day_off_request_to_dict(item) for item in page_obj.object_list
            ],
            "count": total_count,
            "page": page_obj.number,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
            "next_page": (
                page_obj.next_page_number() if page_obj.has_next() else None
            ),
            "previous_page": (
                page_obj.previous_page_number()
                if page_obj.has_previous()
                else None
            ),
            "filters": {
                "status": filter_status,
                "date_from": date_from_str or None,
                "date_to": date_to_str or None,
            },
            "summary": {
                "pending_count": pending_count,
                "approved_count": approved_count,
                "rejected_count": rejected_count,
                "today_off_count": today_off_count,
            },
            "today": today.isoformat(),
        }
    )
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

from django.utils.dateparse import parse_date

ACTION_TO_STATUS = {
    "approve": DayOffStatus.APPROVED,
    "reject":  DayOffStatus.REJECTED,
    "pending": DayOffStatus.PENDING,
}


@require_POST
def review_day_off_request(request, request_id):
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required."}, status=401)
    if not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Permission denied."}, status=403)

    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"success": False, "error": "Invalid JSON."}, status=400)

    action = str(payload.get("action", "")).strip().lower()
    if action not in ACTION_TO_STATUS:
        return JsonResponse(
            {"success": False, "error": "Action must be approve, reject, or pending."},
            status=400,
        )

    # Optional date override
    new_date = None
    raw_date = payload.get("date")
    if raw_date:
        new_date = parse_date(str(raw_date).strip())
        if new_date is None:
            return JsonResponse({"success": False, "error": "Invalid date format. Use YYYY-MM-DD."}, status=400)

    try:
        item = DayOffRequest.objects.get(pk=request_id)
    except DayOffRequest.DoesNotExist:
        return JsonResponse({"success": False, "error": "Request not found."}, status=404)

    item.status = ACTION_TO_STATUS[action]
    item.review_note = str(payload.get("review_note", "")).strip()[:500]

    if new_date is not None:
        item.date = new_date

    if action == "pending":
        item.reviewed_by = None
        item.reviewed_at = None
    else:
        item.reviewed_by = request.user
        item.reviewed_at = timezone.now()

    item.save()

    return JsonResponse({
        "success": True,
        "message": f"Request {action}d successfully.",
        "status": item.status,
        "date": item.date.isoformat(),
    })


# views.py

from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Attendance, DayOffRequest, EmployeeSchedule
from .models import DayOffStatus, UserRole, UserState


User = get_user_model()


def is_manager(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.role in [UserRole.ADMIN, UserRole.MANAGER]
    )


def get_selected_date(request):
    """
    Read ?date=YYYY-MM-DD.
    Defaults to today's date in Django's configured timezone.
    """
    value = request.GET.get("date")

    if not value:
        return timezone.localdate()

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def duration_details(total_seconds):
    """Return a non-negative duration as hours/minutes."""
    total_seconds = max(int(total_seconds), 0)
    total_minutes = total_seconds // 60
    hours, minutes = divmod(total_minutes, 60)

    return {
        "hours": hours,
        "minutes": minutes,
        "display": f"{hours}h {minutes}m",
    }


def manager_employee_queryset():
    """
    Include active employees, excluding administrators and managers.
    Change this filter if managers should also appear in the list.
    """
    return User.objects.filter(
        is_active=True,
        state=UserState.WORKING,
    ).exclude(
        role__in=[UserRole.ADMIN, UserRole.MANAGER]
    ).order_by("full_name", "username")


def build_attendance_dashboard(selected_date):
    today = timezone.localdate()
    now = timezone.now()

    employees = list(manager_employee_queryset())

    weekday = selected_date.strftime("%A").upper()

    schedules = {
        item.user_id: item
        for item in EmployeeSchedule.objects.filter(
            user_id__in=[employee.pk for employee in employees],
            day_of_week=weekday,
            is_active=True,
        )
    }

    # Only attendance sessions that started on the selected local date.
    start_of_day = timezone.make_aware(
        datetime.combine(selected_date, time.min)
    )
    start_of_next_day = timezone.make_aware(
        datetime.combine(selected_date + timedelta(days=1), time.min)
    )

    attendance_records = (
        Attendance.objects.filter(
            user_id__in=[employee.pk for employee in employees],
            check_in__gte=start_of_day,
            check_in__lt=start_of_next_day,
        )
        .select_related("user")
        .order_by("-check_in")
    )

    attendance_by_user = {}

    for record in attendance_records:
        # Prefer an active attendance if one exists.
        if record.user_id not in attendance_by_user:
            attendance_by_user[record.user_id] = record

        if record.check_out is None:
            attendance_by_user[record.user_id] = record

    day_off_requests = DayOffRequest.objects.filter(
        user_id__in=[employee.pk for employee in employees],
        date=selected_date,
    ).select_related("reviewed_by")

    approved_by_user = {}
    pending_by_user = {}

    for request in day_off_requests:
        if request.status == DayOffStatus.APPROVED:
            approved_by_user[request.user_id] = request
        elif request.status == DayOffStatus.PENDING:
            pending_by_user[request.user_id] = request

    rows = []

    for employee in employees:
        schedule = schedules.get(employee.pk)
        attendance = attendance_by_user.get(employee.pk)
        approved_leave = approved_by_user.get(employee.pk)
        pending_leave = pending_by_user.get(employee.pk)

        target_hours = max(
            float(employee.daily_working_hours or 0),
            0,
        )

        target_seconds = int(target_hours * 3600)

        elapsed_seconds = 0
        remaining_seconds = target_seconds
        progress = 0
        overtime_seconds = 0

        if attendance:
            end_time = attendance.check_out or now

            elapsed_seconds = max(
                int((end_time - attendance.check_in).total_seconds()),
                0,
            )

            remaining_seconds = max(
                target_seconds - elapsed_seconds,
                0,
            )

            overtime_seconds = max(
                elapsed_seconds - target_seconds,
                0,
            )

            progress = (
                min(elapsed_seconds / target_seconds * 100, 100)
                if target_seconds > 0
                else 100
            )

        is_working = bool(attendance and attendance.check_out is None)
        has_checked_in = attendance is not None
        is_scheduled_day_off = bool(schedule and schedule.is_day_off)

        if approved_leave:
            status = "approved_day_off"

        elif is_scheduled_day_off:
            status = "scheduled_day_off"

        elif is_working and overtime_seconds > 0:
            status = "overtime"

        elif is_working:
            status = "working"

        elif has_checked_in:
            status = "checked_out"

        elif pending_leave:
            status = "pending_day_off"

        elif schedule is None:
            status = "no_schedule"

        elif selected_date > today:
            status = "upcoming"

        elif selected_date < today:
            status = "absent"

        else:
            # Don't mark an employee absent before their scheduled start.
            shift_start = schedule.start_time

            if shift_start:
                scheduled_start = timezone.make_aware(
                    datetime.combine(selected_date, shift_start)
                )
                is_past_start = now >= scheduled_start
            else:
                is_past_start = True

            status = "absent" if is_past_start else "not_arrived_yet"

        rows.append({
            "id": employee.pk,
            "name": employee.full_name or employee.username,
            "username": employee.username,
            "role": employee.get_role_display(),
            "target_hours": target_hours,
            "target_display": duration_details(target_seconds)["display"],
            "check_in": (
                timezone.localtime(attendance.check_in).strftime("%H:%M")
                if attendance else None
            ),
            "check_out": (
                timezone.localtime(attendance.check_out).strftime("%H:%M")
                if attendance and attendance.check_out else None
            ),
            "elapsed": duration_details(elapsed_seconds),
            "remaining": duration_details(remaining_seconds),
            "overtime": duration_details(overtime_seconds),
            "progress": round(progress, 1),
            "status": status,
            "schedule_start": (
                schedule.start_time.strftime("%H:%M")
                if schedule and schedule.start_time else None
            ),
            "schedule_end": (
                schedule.end_time.strftime("%H:%M")
                if schedule and schedule.end_time else None
            ),
            "day_off_reason": (
                approved_leave.reason if approved_leave else ""
            ),
            "pending_reason": (
                pending_leave.reason if pending_leave else ""
            ),
        })

    # Summary cards
    summary = {
        "working": sum(row["status"] == "working" for row in rows),
        "overtime": sum(row["status"] == "overtime" for row in rows),
        "approved_day_off": sum(
            row["status"] == "approved_day_off" for row in rows
        ),
        "scheduled_day_off": sum(
            row["status"] == "scheduled_day_off" for row in rows
        ),
        "absent": sum(row["status"] == "absent" for row in rows),
        "pending_day_off": sum(
            row["status"] == "pending_day_off" for row in rows
        ),
        "checked_out": sum(
            row["status"] == "checked_out" for row in rows
        ),
    }

    return {
        "date": selected_date.isoformat(),
        "today": today.isoformat(),
        "summary": summary,
        "employees": rows,
    }


@login_required
@user_passes_test(is_manager)
@require_GET
def manager_attendance_api(request):
    selected_date = get_selected_date(request)

    if selected_date is None:
        return JsonResponse(
            {"error": "Invalid date. Use YYYY-MM-DD."},
            status=400,
        )

    data = build_attendance_dashboard(selected_date)
    return JsonResponse(data)


@login_required
@user_passes_test(is_manager)
def manager_attendance_dashboard(request):
    selected_date = get_selected_date(request) or timezone.localdate()

    return render(
        request,
        "users/attendance_dashboard.html",
        {
            "selected_date": selected_date.isoformat(),
            "api_url": "/api/manager/attendance/",
        },
    )