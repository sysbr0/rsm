from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from .models import Order, OrderStatus
from apps.tables.models import RestaurantTable, TableStatus
from apps.users.models import User


@login_required
def order_dashboard(request):
    today = timezone.localdate()

    # ---------------------------------------------------------
    # FILTERS
    # ---------------------------------------------------------

    selected_waiter = request.GET.get("waiter", "").strip()
    selected_date = request.GET.get("date", "").strip()

    # If a date is selected, use it.
    # Otherwise use today.
    dashboard_date = today

    if selected_date:
        try:
            from datetime import datetime

            dashboard_date = datetime.strptime(
                selected_date,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            dashboard_date = today

    # ---------------------------------------------------------
    # BASE ORDER QUERY
    # ---------------------------------------------------------

    date_orders = Order.objects.filter(
        created_at__date=dashboard_date
    ).select_related(
        "table",
        "waiter",
    )

    # Waiter filter
    if selected_waiter:
        try:
            selected_waiter_id = int(selected_waiter)
            date_orders = date_orders.filter(
                waiter_id=selected_waiter_id
            )
        except (ValueError, TypeError):
            selected_waiter_id = None
    else:
        selected_waiter_id = None

    # ---------------------------------------------------------
    # TODAY / SELECTED DATE STATISTICS
    # ---------------------------------------------------------

    paid_orders = date_orders.filter(
        status=OrderStatus.PAID
    )

    cancelled_orders = date_orders.filter(
        status=OrderStatus.CANCELLED
    )

    active_orders = date_orders.filter(
        status__in=[
            OrderStatus.OPEN,
            OrderStatus.CONFIRMED,
            OrderStatus.PREPARING,
            OrderStatus.READY,
            OrderStatus.SERVED,
        ]
    )

    total_orders = date_orders.count()

    total_paid_orders = paid_orders.count()

    total_cancelled_orders = cancelled_orders.count()

    total_revenue = (
        paid_orders.aggregate(
            total=Sum("total")
        )["total"]
        or Decimal("0.00")
    )

    average_order_value = (
        total_revenue / total_paid_orders
        if total_paid_orders
        else Decimal("0.00")
    )

    # ---------------------------------------------------------
    # TABLE STATISTICS
    # ---------------------------------------------------------

    total_tables = RestaurantTable.objects.count()

    available_tables = RestaurantTable.objects.filter(
        status=TableStatus.AVAILABLE
    ).count()

    occupied_tables = RestaurantTable.objects.filter(
        status=TableStatus.OCCUPIED
    ).count()

    reserved_tables = RestaurantTable.objects.filter(
        status=TableStatus.RESERVED
    ).count()

    on_payment_tables = RestaurantTable.objects.filter(
        status=TableStatus.ON_PayMENT
    ).count()

    closed_tables = RestaurantTable.objects.filter(
        status=TableStatus.CLOSED
    ).count()

    active_tables = (
        occupied_tables
        + reserved_tables
        + on_payment_tables
    )

    # ---------------------------------------------------------
    # WAITERS
    # ---------------------------------------------------------

    waiters = User.objects.filter(
        orders__isnull=False
    ).distinct().order_by(
        "full_name"
    )

    # ---------------------------------------------------------
    # WAITER PERFORMANCE
    # ---------------------------------------------------------

    waiter_stats = (
        User.objects
        .filter(
            orders__created_at__date=dashboard_date
        )
        .annotate(
            order_count=Count(
                "orders",
                filter=Q(
                    orders__created_at__date=dashboard_date,
                    orders__status=OrderStatus.PAID,
                ),
                distinct=True,
            ),

            table_count=Count(
                "orders__table",
                filter=Q(
                    orders__created_at__date=dashboard_date,
                    orders__status=OrderStatus.PAID,
                ),
                distinct=True,
            ),

            revenue=Sum(
                "orders__total",
                filter=Q(
                    orders__created_at__date=dashboard_date,
                    orders__status=OrderStatus.PAID,
                ),
            ),
        )
        .order_by("-revenue", "full_name")
    )

    # Replace None revenue with zero
    for waiter in waiter_stats:
        if waiter.revenue is None:
            waiter.revenue = Decimal("0.00")

    # ---------------------------------------------------------
    # LAST 7 DAYS GRAPH
    # ---------------------------------------------------------

    graph_start = dashboard_date - timedelta(days=6)

    graph_orders = (
        Order.objects
        .filter(
            created_at__date__gte=graph_start,
            created_at__date__lte=dashboard_date,
        )
    )

    if selected_waiter_id:
        graph_orders = graph_orders.filter(
            waiter_id=selected_waiter_id
        )

    # Orders per day
    daily_orders = (
        graph_orders
        .values("created_at__date")
        .annotate(
            order_count=Count("id")
        )
        .order_by("created_at__date")
    )

    # Revenue per day
    daily_revenue = (
        graph_orders
        .filter(status=OrderStatus.PAID)
        .values("created_at__date")
        .annotate(
            revenue=Sum("total")
        )
        .order_by("created_at__date")
    )

    orders_by_date = {
        item["created_at__date"]: item["order_count"]
        for item in daily_orders
    }

    revenue_by_date = {
        item["created_at__date"]: item["revenue"] or Decimal("0.00")
        for item in daily_revenue
    }

    graph_labels = []
    graph_order_values = []
    graph_revenue_values = []

    current_date = graph_start

    while current_date <= dashboard_date:

        graph_labels.append(
            current_date.strftime("%d %b")
        )

        graph_order_values.append(
            orders_by_date.get(
                current_date,
                0,
            )
        )

        graph_revenue_values.append(
            float(
                revenue_by_date.get(
                    current_date,
                    Decimal("0.00"),
                )
            )
        )

        current_date += timedelta(days=1)

    # ---------------------------------------------------------
    # ORDER LIST
    # ---------------------------------------------------------

    orders = (
        date_orders
        .order_by("-created_at")
    )

    # ---------------------------------------------------------
    # CONTEXT
    # ---------------------------------------------------------

    context = {
        # Date / filter
        "today": today,
        "dashboard_date": dashboard_date,
        "selected_date": selected_date,
        "selected_waiter": selected_waiter_id,

        # Orders
        "orders": orders,
        "total_orders": total_orders,
        "total_paid_orders": total_paid_orders,
        "total_cancelled_orders": total_cancelled_orders,
        "active_order_count": active_orders.count(),

        # Money
        "total_revenue": total_revenue,
        "average_order_value": average_order_value,

        # Tables
        "total_tables": total_tables,
        "available_tables": available_tables,
        "occupied_tables": occupied_tables,
        "reserved_tables": reserved_tables,
        "on_payment_tables": on_payment_tables,
        "closed_tables": closed_tables,
        "active_tables": active_tables,

        # Waiters
        "waiters": waiters,
        "waiter_stats": waiter_stats,

        # Graph
        "graph_labels": graph_labels,
        "graph_order_values": graph_order_values,
        "graph_revenue_values": graph_revenue_values,
    }

    return render(
        request,
        "manager/orders/dashboard.html",
        context,
    )