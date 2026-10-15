from django.shortcuts import render

from tables.models import TableStatus
from decimal import Decimal

from django.shortcuts import render
from django.db import transaction
# Create your views here.
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from orders.models import *
from Financial.models import *
from django.utils import timezone
from users.models import User, UserRole
#add format_currency
from Financial.utils import format_currency
from tables.models import *
from django.conf import settings
from menu.models import Category
from tables.models import (
    RestaurantTable,
    SectionBlock,
    TableStatus,
)


def admin_tables(request):
    # ---------------------------------------------------------
    # Tables
    # ---------------------------------------------------------
    tables = list(
        RestaurantTable.objects
        .filter(is_active=True)
        .select_related("section_block")
        .order_by("table_number")
    )

    # ---------------------------------------------------------
    # Section Blocks
    # ---------------------------------------------------------
    section_blocks = list(
        SectionBlock.objects
        .filter(is_active=True)
        .order_by("display_order", "name")
    )

    # ---------------------------------------------------------
    # Filters
    # ---------------------------------------------------------
    filter_type = request.GET.get("filter", "all")
    section_id = request.GET.get("section")

    # ---------------------------------------------------------
    # Active Order Statuses
    # ---------------------------------------------------------
    active_statuses = [
        OrderStatus.OPEN,
        OrderStatus.CONFIRMED,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.SERVED,
        OrderStatus.PAID,
    ]

    # ---------------------------------------------------------
    # Get Latest Active Order For Each Table
    # ---------------------------------------------------------
    active_orders = (
        Order.objects
        .filter(
            table__in=tables,
            status__in=active_statuses,
        )
        .select_related("waiter", "table")
        .order_by("table_id", "-created_at")
    )

    latest_order_by_table = {}

    for order in active_orders:
        if order.table_id not in latest_order_by_table:
            latest_order_by_table[order.table_id] = order

    # ---------------------------------------------------------
    # Table Status Colors
    # ---------------------------------------------------------
    status_background = {
        TableStatus.AVAILABLE:   "#FFFFFF",  # soft emerald tint  — free & ready
        TableStatus.OCCUPIED:    "#D5C688",  # soft amber tint    — in service
        TableStatus.RESERVED:    "#D17CAB",  # soft pink tint     — booked
        TableStatus.CLOSED:      "#A23F3F",  # soft red tint      — out of service
        TableStatus.ON_PAYMENT:  "#5A85BD",  # soft blue tint     — settling up
    }

    # ---------------------------------------------------------
    # Build Dashboard Tables
    # ---------------------------------------------------------
    dashboard_tables = []

    now = timezone.now()

    for table in tables:
        waiter_name = ""
        order_total = None
        order_created_at = None
        elapsed_display = ""
        elapsed_seconds = 0

        # Only look for an order when the table is not available
        if table.status != TableStatus.AVAILABLE:
            order = latest_order_by_table.get(table.id)

            if order:
                waiter_name = (
                    order.waiter.full_name
                    or order.waiter.username
                )

                order_total = order.total
                order_created_at = order.created_at

                # ---------------------------------------------
                # Elapsed time since order was created
                # ---------------------------------------------
                if order_created_at:
                    delta = now - order_created_at
                    elapsed_seconds = int(delta.total_seconds())

                    hours, remainder = divmod(elapsed_seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)

                    if hours > 0:
                        elapsed_display = f"{hours}h {minutes}m"
                    elif minutes > 0:
                        elapsed_display = f"{minutes}m {seconds}s"
                    else:
                        elapsed_display = f"{seconds}s"

        order_total_display = (
            format_currency(order_total)
            if order_total is not None
            else "N/A"
        )

        dashboard_tables.append(
            {
                "table_id": table.id,
                "name": table.name,
                "table_number": table.table_number,
                "status": table.status,
                "status_label": table.get_status_display(),
                "background_color": status_background.get(
                    table.status,
                    "#ffffff",
                ),
                "waiter_name": waiter_name,
                "order_total_display": order_total_display,
                "order_created_at": order_created_at,
                "elapsed_display": elapsed_display,
                "elapsed_seconds": elapsed_seconds,
                "section_block_id": table.section_block_id,
                "section_block_name": (
                    table.section_block.name
                    if table.section_block
                    else "Unassigned"
                ),
                "detail_url": f"/manager/tables/{table.id}/",
            }
        )

    # ---------------------------------------------------------
    # Apply Filters
    # ---------------------------------------------------------
    if filter_type == "occupied":
        dashboard_tables = [
            table
            for table in dashboard_tables
            if table["status"] == TableStatus.OCCUPIED
        ]

    if section_id:
        dashboard_tables = [
            table
            for table in dashboard_tables
            if str(table["section_block_id"]) == str(section_id)
        ]

    # ---------------------------------------------------------
    # Dashboard Summary
    # ---------------------------------------------------------
    summary = {
        "total_tables": len(tables),

        "occupied_tables": sum(
            1
            for table in tables
            if table.status == TableStatus.OCCUPIED
        ),

        "available_tables": sum(
            1
            for table in tables
            if table.status == TableStatus.AVAILABLE
        ),
    }

    # ---------------------------------------------------------
    # Product Summary
    # ---------------------------------------------------------
    product_summary = {
        "total_products": Product.objects.filter(
            is_active=True
        ).count(),

        "total_categories": Category.objects.filter(
            is_active=True
        ).count(),

        "total_sections": SectionBlock.objects.filter(
            is_active=True
        ).count(),
    }

    # ---------------------------------------------------------
    # Order Summary
    # ---------------------------------------------------------
    order_summary = {
        "active_orders": Order.objects.filter(
            status__in=active_statuses
        ).count(),

        "completed_orders": Order.objects.filter(
            status__in=[
                OrderStatus.PAID,
                OrderStatus.CANCELLED,
            ]
        ).count(),

        "open_tabs": Order.objects.filter(
            status__in=active_statuses
        ).values(
            "table_id"
        ).distinct().count(),
    }

    # ---------------------------------------------------------
    # Render
    # ---------------------------------------------------------
    return render(
        request,
        "ui/tables.html",
        {
            "tables": dashboard_tables,
            "section_blocks": section_blocks,

            "occupied_status": TableStatus.OCCUPIED,

            "active_filter": filter_type,
            "active_section_id": section_id,

            "admin_page": "tables",

            "summary": summary,
            "product_summary": product_summary,
            "order_summary": order_summary,
        },
    )