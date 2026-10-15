from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from .models import Order, OrderStatus
from tables.models import RestaurantTable, TableStatus
from users.models import User
# orders/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from .models import Order, OrderStatus, RestaurantTable, TableStatus


@login_required
def order_dashboard(request):
    """Display the restaurant order dashboard."""
    today = timezone.localdate()

    # ------------------------------------------------------------------
    # FILTERS
    # ------------------------------------------------------------------
    dashboard_date = _parse_date(request.GET.get("date"), fallback=today)
    selected_waiter_id = _parse_int(request.GET.get("waiter"))

    # ------------------------------------------------------------------
    # BASE QUERY
    # ------------------------------------------------------------------
    date_orders = (
        Order.objects
        .filter(created_at__date=dashboard_date)
        .select_related("table", "waiter")
    )
    if selected_waiter_id:
        date_orders = date_orders.filter(waiter_id=selected_waiter_id)

    # ------------------------------------------------------------------
    # ORDER STATISTICS
    # ------------------------------------------------------------------
    paid_orders = date_orders.filter(status=OrderStatus.PAID)
    cancelled_orders = date_orders.filter(status=OrderStatus.CANCELLED)

    active_statuses = [
        OrderStatus.OPEN,
        OrderStatus.CONFIRMED,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.SERVED,
    ]
    active_orders_count = date_orders.filter(status__in=active_statuses).count()

    total_orders = date_orders.count()
    total_paid_orders = paid_orders.count()
    total_cancelled_orders = cancelled_orders.count()

    total_revenue = (
        paid_orders.aggregate(total=Sum("total"))["total"]
        or Decimal("0.00")
    )
    average_order_value = (
        total_revenue / total_paid_orders
        if total_paid_orders
        else Decimal("0.00")
    )

    # ------------------------------------------------------------------
    # TABLE STATISTICS
    # ------------------------------------------------------------------
    table_counts = _table_status_counts()
    active_tables = (
        table_counts["occupied"]
        + table_counts["reserved"]
        + table_counts["on_payment"]
    )

    # ------------------------------------------------------------------
    # WAITER PERFORMANCE
    # ------------------------------------------------------------------
    waiter_stats = _waiter_stats_for(dashboard_date)

    # ------------------------------------------------------------------
    # GRAPH DATA (last 7 days)
    # ------------------------------------------------------------------
    graph_data = _build_graph_data(dashboard_date, selected_waiter_id)

    # ------------------------------------------------------------------
    # ORDER LIST
    # ------------------------------------------------------------------
    orders = date_orders.order_by("-created_at")

    # ------------------------------------------------------------------
    # CONTEXT
    # ------------------------------------------------------------------
    context = {
        # Filters
        "today": today,
        "dashboard_date": dashboard_date,
        "selected_date": request.GET.get("date", "").strip(),
        "selected_waiter": selected_waiter_id,

        # Orders
        "orders": orders,
        "total_orders": total_orders,
        "total_paid_orders": total_paid_orders,
        "total_cancelled_orders": total_cancelled_orders,
        "active_order_count": active_orders_count,

        # Money
        "total_revenue": total_revenue,
        "average_order_value": average_order_value,

        # Tables
        "total_tables": table_counts["total"],
        "available_tables": table_counts["available"],
        "occupied_tables": table_counts["occupied"],
        "reserved_tables": table_counts["reserved"],
        "on_payment_tables": table_counts["on_payment"],
        "closed_tables": table_counts["closed"],
        "active_tables": active_tables,

        # Waiters
        "waiters": _waiters_with_orders(),
        "waiter_stats": waiter_stats,

        # Graph
        "graph_labels": graph_data["labels"],
        "graph_order_values": graph_data["orders"],
        "graph_revenue_values": graph_data["revenue"],
    }

    return render(request, "orders/dashboard.html", context)


# ======================================================================
# HELPERS
# ======================================================================

def _parse_date(value, fallback):
    """Parse a YYYY-MM-DD string, or return the fallback date."""
    if not value:
        return fallback
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return fallback


def _parse_int(value):
    """Parse an int safely, returning None on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _table_status_counts():
    """Return a dict with counts per table status."""
    rows = (
        RestaurantTable.objects
        .values("status")
        .annotate(count=Count("id"))
    )
    by_status = {row["status"]: row["count"] for row in rows}

    return {
        "total": sum(by_status.values()),
        "available": by_status.get(TableStatus.AVAILABLE, 0),
        "occupied": by_status.get(TableStatus.OCCUPIED, 0),
        "reserved": by_status.get(TableStatus.RESERVED, 0),
        "on_payment": by_status.get(TableStatus.ON_PAYMENT, 0),
        "closed": by_status.get(TableStatus.CLOSED, 0),
    }


def _waiter_stats_for(dashboard_date):
    """Aggregated performance per waiter for the given date."""
    from django.contrib.auth import get_user_model

    User = get_user_model()

    paid_filter = Q(
        orders__created_at__date=dashboard_date,
        orders__status=OrderStatus.PAID,
    )

    stats = (
        User.objects
        .filter(orders__created_at__date=dashboard_date)
        .annotate(
            order_count=Count("orders", filter=paid_filter, distinct=True),
            table_count=Count(
                "orders__table", filter=paid_filter, distinct=True
            ),
            revenue=Sum("orders__total", filter=paid_filter),
        )
        .order_by("-revenue", "full_name")
    )

    for waiter in stats:
        if waiter.revenue is None:
            waiter.revenue = Decimal("0.00")

    return stats


def _waiters_with_orders():
    """All waiters who have at least one order."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return (
        User.objects
        .filter(orders__isnull=False)
        .distinct()
        .order_by("full_name")
    )


def _build_graph_data(dashboard_date, waiter_id=None):
    """Return 7 days of order & revenue data ending on dashboard_date."""
    start = dashboard_date - timedelta(days=6)

    base = Order.objects.filter(
        created_at__date__gte=start,
        created_at__date__lte=dashboard_date,
    )
    if waiter_id:
        base = base.filter(waiter_id=waiter_id)

    orders_by_date = {
        row["created_at__date"]: row["count"]
        for row in (
            base
            .values("created_at__date")
            .annotate(count=Count("id"))
        )
    }

    revenue_by_date = {
        row["created_at__date"]: row["total"] or Decimal("0.00")
        for row in (
            base
            .filter(status=OrderStatus.PAID)
            .values("created_at__date")
            .annotate(total=Sum("total"))
        )
    }

    labels, orders, revenue = [], [], []
    current = start
    while current <= dashboard_date:
        labels.append(current.strftime("%d %b"))
        orders.append(orders_by_date.get(current, 0))
        revenue.append(float(revenue_by_date.get(current, Decimal("0.00"))))
        current += timedelta(days=1)

    return {"labels": labels, "orders": orders, "revenue": revenue}


@login_required
def analytics_dashboard(request):
    """Renders the shell — data is fetched via JS."""
    return render(request, "orders/analytics_dashboard.html")