# orders/api_views.py
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Order, OrderStatus


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _parse_int(value, default, min_value=1, max_value=365):
    try:
        n = int(value)
        return max(min_value, min(max_value, n))
    except (TypeError, ValueError):
        return default


# -------------------------------------------------------------------
# GET /orders/api/analytics/dashboard/
# -------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_dashboard(request):
    """
    High-level KPIs for the orders analytics dashboard.
    """
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    # All paid orders — revenue is only counted for PAID orders
    paid = Order.objects.filter(status=OrderStatus.PAID)

    today_orders = paid.filter(created_at__gte=today_start)
    week_orders = paid.filter(created_at__gte=week_start)
    month_orders = paid.filter(created_at__gte=month_start)

    def agg(qs):
        return qs.aggregate(
            revenue=Sum("total"),
            count=Count("id"),
            avg=Sum("total") / Count("id") if qs.exists() else Decimal("0"),
        )

    today = agg(today_orders)
    week = agg(week_orders)
    month = agg(month_orders)
    all_time = agg(paid)

    # Live status counts (all orders, not just paid)
    status_counts = (
        Order.objects.values("status")
        .annotate(count=Count("id"))
        .order_by()
    )
    status_map = {row["status"]: row["count"] for row in status_counts}

    # Active = not PAID and not CANCELLED
    active_statuses = [
        OrderStatus.OPEN,
        OrderStatus.CONFIRMED,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.SERVED,
    ]
    active_count = Order.objects.filter(status__in=active_statuses).count()

    return Response(
        {
            "currency": getattr(__import__("django.conf", fromlist=["settings"]).settings, "CURRENCY", "₺"),
            "today": {
                "revenue": str(today["revenue"] or 0),
                "orders": today["count"] or 0,
                "avg": str(today["avg"] or 0),
            },
            "week": {
                "revenue": str(week["revenue"] or 0),
                "orders": week["count"] or 0,
                "avg": str(week["avg"] or 0),
            },
            "month": {
                "revenue": str(month["revenue"] or 0),
                "orders": month["count"] or 0,
                "avg": str(month["avg"] or 0),
            },
            "all_time": {
                "revenue": str(all_time["revenue"] or 0),
                "orders": all_time["count"] or 0,
            },
            "active_orders": active_count,
            "status_breakdown": [
                {"status": s.value, "label": s.label, "count": status_map.get(s.value, 0)}
                for s in OrderStatus
            ],
        }
    )


# -------------------------------------------------------------------
# GET /orders/api/analytics/daily-revenue/?days=30
# -------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def daily_revenue(request):
    """
    Revenue per day for the last N days (default 30).

    Only counts PAID orders. Fills gaps with zero so the chart is
    continuous.
    """
    days = _parse_int(request.query_params.get("days"), default=30, max_value=365)

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = (today_start - timedelta(days=days - 1)).date()

    rows = (
        Order.objects
        .filter(
            status=OrderStatus.PAID,
            created_at__date__gte=start_date,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            revenue=Sum("total"),
            orders=Count("id"),
        )
        .order_by("day")
    )

    # Build a continuous date range
    data_map = {row["day"]: row for row in rows}
    result = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        row = data_map.get(d)
        result.append(
            {
                "date": d.isoformat(),
                "label": d.strftime("%b %d"),
                "revenue": str(row["revenue"] if row else Decimal("0.00")),
                "orders": row["orders"] if row else 0,
            }
        )

    total = sum(Decimal(r["revenue"]) for r in result)
    return Response(
        {
            "days": days,
            "start": start_date.isoformat(),
            "end": today_start.date().isoformat(),
            "total": str(total),
            "data": result,
        }
    )


# -------------------------------------------------------------------
# GET /orders/api/analytics/hourly-today/
# -------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hourly_today(request):
    """
    Revenue + orders per hour for today. Useful for a small bar chart.
    """
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    rows = (
        Order.objects
        .filter(status=OrderStatus.PAID, created_at__gte=today_start)
        .annotate(hour=TruncDate("created_at"))  # placeholder — we'll bucket in Python
        .values("created_at", "total")
    )

    buckets = {h: {"revenue": Decimal("0"), "orders": 0} for h in range(24)}
    for row in rows:
        h = row["created_at"].hour
        buckets[h]["revenue"] += row["total"]
        buckets[h]["orders"] += 1

    return Response(
        {
            "data": [
                {
                    "hour": h,
                    "label": f"{h:02d}:00",
                    "revenue": str(buckets[h]["revenue"]),
                    "orders": buckets[h]["orders"],
                }
                for h in range(24)
            ]
        }
    )


# -------------------------------------------------------------------
# GET /orders/api/analytics/status-breakdown/
# -------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def status_breakdown(request):
    """
    Count of orders per status (all-time).
    """
    rows = Order.objects.values("status").annotate(count=Count("id"))
    status_map = {row["status"]: row["count"] for row in rows}
    return Response(
        {
            "data": [
                {
                    "status": s.value,
                    "label": s.label,
                    "count": status_map.get(s.value, 0),
                }
                for s in OrderStatus
            ]
        }
    )


# -------------------------------------------------------------------
# GET /orders/api/analytics/top-items/?days=30&limit=10
# -------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def top_items(request):
    """
    Best-selling items by quantity or revenue, for the last N days.
    """
    days = _parse_int(request.query_params.get("days"), default=30, max_value=365)
    limit = _parse_int(request.query_params.get("limit"), default=10, max_value=50)

    now = timezone.now()
    start_date = (now - timedelta(days=days)).date()

    # Adjust these paths to match your OrderItem model.
    # Assuming OrderItem has: order, menu_item (or product), quantity, price/total
    from .models import OrderItem  # adjust import

    rows = (
        OrderItem.objects
        .filter(
            order__status=OrderStatus.PAID,
            order__created_at__date__gte=start_date,
        )
        .values("menu_item__name")
        .annotate(
            qty=Sum("quantity"),
            revenue=Sum("total"),  # or F("quantity") * F("price")
        )
        .order_by("-revenue")[:limit]
    )

    return Response(
        {
            "data": [
                {
                    "name": r["menu_item__name"],
                    "quantity": r["qty"] or 0,
                    "revenue": str(r["revenue"] or 0),
                }
                for r in rows
            ]
        }
    )