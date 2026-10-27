
from django.contrib.auth import authenticate
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.authtoken.models import Token
from rest_framework import status
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.urls import reverse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied, ValidationError
from Financial.utils import format_currency
from menu.models import *
from tables.models import *
from users.models import *
from orders.models import *
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
import logging
import calendar
from datetime import date, datetime, time, timedelta
from rest_framework.authentication import TokenAuthentication
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.views import View
from django.utils.dateparse import parse_date









class WaiterMobileLoginAPIView(APIView):
    """Mobile login API for WAITER and MANAGER accounts."""

    print("started")

    permission_classes = [AllowAny]
    authentication_classes = []

    ALLOWED_ROLES = {"WAITER", "MANAGER"}

    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")

        if not isinstance(username, str) or not isinstance(password, str):
            return Response(
                {
                    "success": False,
                    "message": "Invalid username or password format.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        username = username.strip()

        if not username or not password:
            return Response(
                {
                    "success": False,
                    "message": "Username and password are required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(
            request=request,
            username=username,
            password=password,
        )

        if user is None:
            return Response(
                {
                    "success": False,
                    "message": "Invalid username or password.",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {
                    "success": False,
                    "message": "Your account is inactive.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.role not in self.ALLOWED_ROLES:
            return Response(
                {
                    "success": False,
                    "message": "You are not allowed to access the waiter app.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        token, _ = Token.objects.get_or_create(user=user)

        return Response(
            {
                "success": True,
                "message": "Login successful.",
                "token": token.key,
                "user": {
                    "id": user.pk,
                    "username": user.username,
                    "role": user.role,
                    "state":user.state
                },
                "redirect": "/waiter/",
            },
            status=status.HTTP_200_OK,
        )


#----------------------------------
#               tables 
#----------------------------------




# ==========================================================
# CONFIGURATION
# ==========================================================

STATUS_BACKGROUND = {
    TableStatus.AVAILABLE: "#FFFFFF",
    TableStatus.OCCUPIED: "#D5C688",
    TableStatus.RESERVED: "#D17CAB",
    TableStatus.CLOSED: "#A23F3F",
    TableStatus.ON_PAYMENT: "#5A85BD",
}

ACTIVE_ORDER_STATUSES = [
    OrderStatus.OPEN,
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.SERVED,
    OrderStatus.PAID,
]


# ==========================================================
# TABLES DASHBOARD API
# ==========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tables_dashboard_api(request):
    now = timezone.now()

    # ------------------------------------------------------
    # Tables
    # ------------------------------------------------------

    tables = list(
        RestaurantTable.objects
        .filter(is_active=True)
        .select_related("section_block")
        .order_by("table_number")
    )

    # ------------------------------------------------------
    # Section Blocks
    # ------------------------------------------------------

    section_blocks = list(
        SectionBlock.objects
        .filter(is_active=True)
        .order_by("display_order", "name")
    )

    # ------------------------------------------------------
    # Latest Active Order Per Table
    # ------------------------------------------------------

    table_ids = [table.pk for table in tables]

    orders = (
        Order.objects
        .filter(
            table_id__in=table_ids,
            status__in=ACTIVE_ORDER_STATUSES,
        )
        .select_related("waiter", "table")
        .order_by("table_id", "-created_at", "-pk")
    )

    latest_order_by_table = {}

    for order in orders:
        if order.table_id not in latest_order_by_table:
            latest_order_by_table[order.table_id] = order

    # ------------------------------------------------------
    # Build Dashboard Tables
    # ------------------------------------------------------

    dashboard_tables = []

    for table in tables:
        order = (
            latest_order_by_table.get(table.pk)
            if table.status != TableStatus.AVAILABLE
            else None
        )

        waiter = order.waiter if order else None

        waiter_name = ""
        waiter_id = None
        order_total = None
        order_created_at = None
        elapsed_seconds = 0
        elapsed_display = ""

        if order:
            if waiter:
                waiter_name = waiter.full_name or waiter.username
                waiter_id = waiter.pk

            order_total = order.total
            order_created_at = order.created_at

            if order_created_at:
                elapsed_seconds = max(
                    0,
                    int((now - order_created_at).total_seconds()),
                )

                hours, remainder = divmod(elapsed_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)

                if hours:
                    elapsed_display = f"{hours}h {minutes}m"
                elif minutes:
                    elapsed_display = f"{minutes}m {seconds}s"
                else:
                    elapsed_display = f"{seconds}s"

        dashboard_tables.append({
            "tableId": table.pk,
            "name": table.name,
            "tableNumber": table.table_number,
            "status": table.status,
            "statusLabel": table.get_status_display(),

            "backgroundColor": STATUS_BACKGROUND.get(
                table.status,
                "#FFFFFF",
            ),

            "waiterId": waiter_id,
            "waiterName": waiter_name,

            "orderTotalDisplay": (
                format_currency(order_total)
                if order_total is not None
                else "N/A"
            ),

            "orderCreatedAt": order_created_at,
            "elapsedDisplay": elapsed_display,
            "elapsedSeconds": elapsed_seconds,

            "sectionBlockId": table.section_block_id,
            "sectionBlockName": (
                table.section_block.name
                if table.section_block
                else "Unassigned"
            ),

            "detailUrl": f"/manager/tables/{table.pk}/",
        })

    # ------------------------------------------------------
    # Filters
    # Supports:
    # ?filter=all
    # ?filter=occupied
    # ?section=1
    # ?filter=occupied&section=1
    # ------------------------------------------------------

    filter_type = request.query_params.get("filter", "all")
    section_id = request.query_params.get("section")

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
            if str(table["sectionBlockId"]) == str(section_id)
        ]

    # ------------------------------------------------------
    # Table Summary
    # Calculated from all active tables, before filtering
    # ------------------------------------------------------

    summary = {
        "totalTables": len(tables),

        "occupiedTables": sum(
            table.status == TableStatus.OCCUPIED
            for table in tables
        ),

        "availableTables": sum(
            table.status == TableStatus.AVAILABLE
            for table in tables
        ),
    }

    # ------------------------------------------------------
    # Product Summary
    # ------------------------------------------------------

    product_summary = {
        "totalProducts": Product.objects.filter(
            is_active=True
        ).count(),

        "totalCategories": Category.objects.filter(
            is_active=True
        ).count(),

        "totalSections": SectionBlock.objects.filter(
            is_active=True
        ).count(),
    }

    # ------------------------------------------------------
    # Order Summary
    # ------------------------------------------------------

    order_summary = {
        "activeOrders": Order.objects.filter(
            status__in=ACTIVE_ORDER_STATUSES
        ).count(),

        "completedOrders": Order.objects.filter(
            status__in=[
                OrderStatus.PAID,
                OrderStatus.CANCELLED,
            ]
        ).count(),

        "openTabs": Order.objects.filter(
            status__in=ACTIVE_ORDER_STATUSES
        ).values("table_id").distinct().count(),
    }

    # ------------------------------------------------------
    # JSON Response
    # ------------------------------------------------------

    return Response({
        "tables": dashboard_tables,

        "sectionBlocks": [
            {
                "id": section.pk,
                "name": section.name,
            }
            for section in section_blocks
        ],

        "summary": summary,
        "productSummary": product_summary,
        "orderSummary": order_summary,
    })
#-------------------------------
# deitles of table 
# -------------------------------

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

ACTIVE_ORDER_STATUSES = [
    OrderStatus.OPEN,
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.SERVED,
    OrderStatus.PAID,
]

# Waiter is allowed to work only on these — a paid/cancelled order
# must not receive new items.
EDITABLE_ORDER_STATUSES = {
    OrderStatus.OPEN,
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.SERVED,
}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def get_current_order(table):
    """Latest active order on a table."""
    return (
        Order.objects
        .filter(table=table, status__in=ACTIVE_ORDER_STATUSES)
        .exclude(table__status=TableStatus.AVAILABLE)
        .select_related("waiter")
        .prefetch_related("items__product")
        .order_by("-created_at")
        .first()
    )


def recalculate_order_totals(order: Order) -> None:
    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")

    for item in order.items.select_related("product"):
        qty = Decimal(str(item.quantity))
        line_subtotal = item.unit_price * qty
        line_tax = line_subtotal * item.product.tax_rate / Decimal("100")
        subtotal += line_subtotal
        tax_total += line_tax

    total = subtotal + tax_total - order.discount
    if total < Decimal("0.00"):
        total = Decimal("0.00")

    order.subtotal = subtotal
    order.tax = tax_total
    order.total = total
    order.save(update_fields=["subtotal", "tax", "total"])


def parse_quantity(raw) -> Decimal | None:
    if raw is None:
        return None
    try:
        qty = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if qty < Decimal("0.50"):
        return None
    return qty.quantize(Decimal("0.01"))


def format_quantity(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.to_integral())
    return f"{value:.2f}".rstrip("0").rstrip(".")


def resolve_waiter(request) -> User | None:
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return user
    return (
        User.objects.filter(is_active=True, role=UserRole.WAITER)
        .order_by("id")
        .first()
        or User.objects.filter(is_active=True).order_by("id").first()
    )


# ------------------------------------------------------------------
# Serializers (hand-rolled — swap for DRF serializers if you prefer)
# ------------------------------------------------------------------

def serialize_item(item: OrderItem) -> dict:
    qty = Decimal(str(item.quantity))
    line_total = item.unit_price * qty
    return {
        "id": item.id,
        "product_id": item.product_id,
        "name": item.product.name,
        "quantity": float(qty),
        "quantity_display": format_quantity(qty),
        "quantity_input": f"{qty:.2f}",
        "unit_price": float(item.unit_price),
        "unit_price_display": format_currency(item.unit_price),
        "line_total": float(line_total),
        "line_total_display": format_currency(line_total),
        "notes": item.notes or "",
        "has_print_job": item.has_print_job,
        "summary_display": (
            f"Qty: {format_quantity(qty)} · "
            f"Price: {format_currency(item.unit_price)} · "
            f"Total: {format_currency(line_total)}"
        ),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def serialize_order(order: Order | None) -> dict | None:
    if order is None:
        return None

    items = list(order.items.select_related("product").order_by("-created_at"))
    rows = [serialize_item(i) for i in items]

    return {
        "id": order.id,
        "status": order.status,
        "status_label": order.get_status_display() if hasattr(order, "get_status_display") else order.status,
        "waiter": (
            {
                "id": order.waiter_id,
                "name": order.waiter.full_name or order.waiter.username,
            }
            if order.waiter_id else None
        ),
        "subtotal": float(order.subtotal),
        "tax": float(order.tax),
        "discount": float(order.discount),
        "total": float(order.total),
        "total_display": format_currency(order.total),
        "items_count": len(rows),
        "items": rows,
        "items_with_notes": [r for r in rows if r["notes"]],
        "items_without_notes": [r for r in rows if not r["notes"]],
        "has_unprinted_items": any(not r["has_print_job"] for r in rows),
        "is_editable": order.status in EDITABLE_ORDER_STATUSES,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


def serialize_table(table: RestaurantTable) -> dict:
    status_background = {
        TableStatus.AVAILABLE: "#dcfce7",
        TableStatus.OCCUPIED: "#fee2e2",
        TableStatus.RESERVED: "#fef3c7",
        TableStatus.ON_PAYMENT: "#fde68a",
        TableStatus.CLOSED: "#e5e7eb",
    }
    return {
        "id": table.id,
        "table_number": table.table_number,
        "name": table.name or f"Table {table.table_number}",
        "capacity": table.capacity,
        "status": table.status,
        "status_label": table.get_status_display(),
        "background_color": status_background.get(table.status, "#ffffff"),
        "section": (
            {
                "id": table.section_block_id,
                "name": table.section_block.name,
            }
            if table.section_block_id else None
        ),
    }


def build_menu_payload() -> list[dict]:
    categories = (
        Category.objects
        .filter(is_active=True)
        .order_by("display_order", "name")
        .prefetch_related("products")
    )

    menu = []
    for category in categories:
        products = sorted(
            [p for p in category.products.all() if p.is_active],
            key=lambda p: p.name.lower(),
        )
        if not products:
            continue

        menu.append({
            "id": category.id,
            "name": category.name,
            "products": [
                {
                    "id": p.id,
                    "name": p.name,
                    "price": float(p.get_current_price()),
                    "price_display": format_currency(p.get_current_price()),
                    "description": p.description or "",
                    "tax_rate": float(p.tax_rate),
                }
                for p in products
            ],
        })
    return menu


# ------------------------------------------------------------------
# Views
# ------------------------------------------------------------------

class WaiterTableDetailView(APIView):
    """GET table detail: table + menu + current order."""
    permission_classes = [IsAuthenticated]

    def get(self, request, table_id: int):
        table = get_object_or_404(
            RestaurantTable.objects.select_related("section_block"),
            id=table_id,
        )
        order = get_current_order(table)

        return Response({
            "table": serialize_table(table),
            "current_order": serialize_order(order),
            "menu": build_menu_payload(),
            "currency": settings.CURRENCY,
        })


class WaiterCreateOrderView(APIView):
    """
    POST — create a new order OR append items to the existing one.

    Body:
    {
      "items": [
        {"product_id": 12, "quantity": "2",   "notes": "no onions"},
        {"product_id": 34, "quantity": "0.5", "notes": ""}
      ]
    }

    Rules preserved from the original:
      * Every line is a NEW OrderItem (never merged/incremented).
      * has_print_job stays False — printing is a separate action.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, table_id: int):
        table = get_object_or_404(RestaurantTable, id=table_id)

        raw_items = request.data.get("items") or []
        if not isinstance(raw_items, list) or not raw_items:
            return Response(
                {"error": "Please provide at least one product."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- parse input -----------------------------------------
        parsed = []
        product_ids = []

        for entry in raw_items:
            try:
                product_id = int(entry.get("product_id"))
            except (TypeError, ValueError):
                return Response(
                    {"error": "Invalid product_id in items."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            qty = parse_quantity(entry.get("quantity"))
            if qty is None:
                return Response(
                    {"error": f"Quantity must be at least 0.5 (product {product_id})."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            note = (entry.get("notes") or "").strip()
            parsed.append({"product_id": product_id, "quantity": qty, "notes": note})
            product_ids.append(product_id)

        # --- validate products ----------------------------------
        product_map = {
            p.id: p
            for p in Product.objects.filter(id__in=product_ids, is_active=True)
        }
        missing = [pid for pid in product_ids if pid not in product_map]
        if missing:
            return Response(
                {"error": "Some products are no longer available.", "missing_ids": missing},
                status=status.HTTP_400_BAD_REQUEST,
            )

        line_items = [
            (
                product_map[e["product_id"]],
                e["quantity"],
                product_map[e["product_id"]].get_current_price(),
                e["notes"],
            )
            for e in parsed
        ]

        # --- waiter ---------------------------------------------
        waiter = resolve_waiter(request)
        if waiter is None:
            return Response(
                {"error": "No active waiter user found. Please create/activate a waiter first."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # --- create / append ------------------------------------
        with transaction.atomic():
            order = get_current_order(table)

            if order is not None and order.status not in EDITABLE_ORDER_STATUSES:
                return Response(
                    {"error": "This order can no longer be modified."},
                    status=status.HTTP_409_CONFLICT,
                )

            if order is None:
                order = Order.objects.create(
                    table=table,
                    waiter=waiter,
                    status=OrderStatus.OPEN,
                    subtotal=Decimal("0.00"),
                    tax=Decimal("0.00"),
                    discount=Decimal("0.00"),
                    total=Decimal("0.00"),
                )

            # Every selected product → brand-new OrderItem.
            for product, qty, price, note in line_items:
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    unit_price=price,
                    discount=Decimal("0.00"),
                    notes=note,
                    has_print_job=False,
                )

            recalculate_order_totals(order)
            Order._sync_table_status(order.table_id)

            # Refresh items for serialization.
            order.refresh_from_db()

        return Response(
            {"ok": True, "order": serialize_order(order)},
            status=status.HTTP_201_CREATED,
        )


class WaiterUpdateItemView(APIView):
    """PATCH — update quantity and/or notes on an existing item."""
    permission_classes = [IsAuthenticated]

    def patch(self, request, table_id: int, item_id: int):
        table = get_object_or_404(RestaurantTable, id=table_id)
        order = get_current_order(table)

        if order is None:
            return Response(
                {"error": "No active order on this table."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status not in EDITABLE_ORDER_STATUSES:
            return Response(
                {"error": "This order can no longer be modified."},
                status=status.HTTP_409_CONFLICT,
            )

        item = order.items.filter(id=item_id).first()
        if item is None:
            return Response(
                {"error": "Order item not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        qty = parse_quantity(request.data.get("quantity"))
        if qty is None:
            return Response(
                {"error": "Quantity must be at least 0.5."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        notes = (request.data.get("notes") or "").strip()

        with transaction.atomic():
            item.quantity = qty
            item.notes = notes
            item.save(update_fields=["quantity", "notes"])
            recalculate_order_totals(order)
            order.refresh_from_db()

        return Response({"ok": True, "order": serialize_order(order)})


class WaiterPrintPendingView(APIView):
    """POST — send all unprinted items on this order to the kitchen."""
    permission_classes = [IsAuthenticated]

    def post(self, request, table_id: int):
        table = get_object_or_404(RestaurantTable, id=table_id)
        order = get_current_order(table)

        if order is None:
            return Response(
                {"error": "No active order on this table."},
                status=status.HTTP_404_NOT_FOUND,
            )

        pending = (
            OrderItem.objects
            .filter(order=order, has_print_job=False)
            .select_related("product", "product__section")
        )

        if not pending.exists():
            return Response(
                {"error": "There are no unprinted items in this order."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        jobs = OrderItem.print_pending_items(order, request.user)

        if not jobs:
            return Response(
                {"error": "Unprinted items found, but no active printer is configured for their section."},
                status=status.HTTP_409_CONFLICT,
            )

        failed = [j for j in jobs if j.status == PrintJobStatus.FAILED]
        if failed:
            return Response(
                {
                    "error": f"{len(failed)} print job(s) failed.",
                    "order": serialize_order(get_current_order(table)),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({
            "ok": True,
            "job_count": len(jobs),
            "order": serialize_order(get_current_order(table)),
        })

class WaiterInvoiceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, table_id: int):
        table = get_object_or_404(RestaurantTable, id=table_id)

        current_order = get_current_order(table)

        # ---- Same check as the original -------------------------
        if current_order is None:
            return Response(
                {"error": "No active order found to print an invoice for."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # =========================================================
        # OWNERSHIP CHECK
        #
        # - Manager / Admin → always allowed
        # - Waiter          → only if they own this order
        # - Otherwise       → rejected
        # =========================================================
        user = request.user
        user_role = getattr(user, "role", None)

        is_manager = user_role in {"ADMIN", "MANAGER"}

        if not is_manager:
            order_waiter_id = current_order.waiter_id

            # If the order has no waiter yet (shouldn't happen for
            # an active order, but be defensive) or the requesting
            # user is not that waiter → reject.
            if order_waiter_id is None or order_waiter_id != user.id:
                return Response(
                    {
                        "error": (
                            "This is not your table. "
                            "You can only print invoices for "
                            "orders assigned to you."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # ---- Same call as the original --------------------------
        try:
            current_order.set_order_as_printed()
        except Exception as exc:
            return Response(
                {"error": f"Unable to print the invoice: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "ok": True,
                "invoice_printed": True,
                "order_id": current_order.id,
            },
            status=status.HTTP_200_OK,
        )



def is_manager(user) -> bool:
    """
    True for ADMIN or MANAGER.

    Handles both plain string roles and TextChoices values.
    """
    role = getattr(user, "role", None)
    role_value = getattr(role, "value", role)
    return role_value in {"ADMIN", "CASHIER"}


def can_manage_order(user, order) -> bool:
    """
    True if the user is allowed to operate on this order.

    - Managers / admins → always allowed.
    - Waiters           → only when they own the order.
    - Everyone else     → denied.
    """
    if not user or not user.is_authenticated:
        return False

    if is_manager(user):
        return True

    return order is not None and order.waiter_id == user.id


class WaiterChangeTableView(APIView):
    """
    POST — move an order to a different table.

    Body:
      { "new_table_id": 12 }

    Guards (mirrors the original view):
      - must have an active order on this table
      - order must not be PAID / CANCELLED
      - new_table_id must be a positive integer
      - (extra) waiter must own the order, unless manager/admin
      - (model-level) target table must exist and be free
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, table_id: int):
        table = get_object_or_404(RestaurantTable, id=table_id)
        current_order = get_current_order(table)

        if current_order is None:
            return Response(
                {"error": "No active order found to change the table for."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if current_order.status in (
            OrderStatus.PAID,
            OrderStatus.CANCELLED,
        ):
            return Response(
                {"error": "Cannot change the table of a paid or cancelled order."},
                status=status.HTTP_409_CONFLICT,
            )

        # ---- Ownership guard (extra vs original) ----------------
        if not can_manage_order(request.user, current_order):
            return Response(
                {"error": "This is not your table. You can only change "
                          "tables for orders assigned to you."},
                status=status.HTTP_403_FORBIDDEN,
            )
        # ---------------------------------------------------------

        raw_table_id = request.data.get("new_table_id")

        try:
            new_table_id = int(raw_table_id)
        except (TypeError, ValueError):
            new_table_id = 0

        if new_table_id <= 0:
            return Response(
                {"error": "Please provide a valid new_table_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            current_order.change_table(new_table_id=new_table_id)

        except ValidationError as exc:
            message = (
                " ".join(exc.messages)
                if hasattr(exc, "messages")
                else str(exc)
            )
            return Response(
                {"error": message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as exc:
            return Response(
                {"error": f"Unable to change the table: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # ---------------------------------------------------------
        # Reload so the returned payload reflects the new table
        # (the FK was swapped; stale cached relations would lie).
        # ---------------------------------------------------------
        current_order.refresh_from_db()

        return Response(
            {
                "ok": True,
                "message": "Table changed successfully.",
                "new_table_id": new_table_id,
                "order": serialize_order(current_order),
            },
            status=status.HTTP_200_OK,
        )



class RequestWaiterChangeView(APIView):
    """
    POST — Request to transfer an order to a new waiter.
    Body: { "new_waiter_id": 5 }
    """
    permission_classes = [IsAuthenticated]

    print("started transfare ")

    def post(self, request, table_id: int):
        # 1. Get the table and current order
        table = get_object_or_404(RestaurantTable, id=table_id)
        
        # Note: Replace get_current_order(table) with your actual logic if it's different
        current_order = Order.objects.filter(
            table=table, 
            status__in=["OPEN", "CONFIRMED", "PREPARING", "READY", "SERVED"]
        ).first()

        if current_order is None:
            return Response(
                {"error": "No active order found to transfer."},
                status=status.HTTP_404_NOT_FOUND
            )

        if current_order.status in ("PAID", "CANCELLED"):
            return Response(
                {"error": "Cannot change the waiter of a paid or cancelled order."},
                status=status.HTTP_409_CONFLICT
            )

        # 2. Validate the new waiter
        raw_waiter_id = request.data.get("new_waiter_id")
        try:
            new_waiter_id = int(raw_waiter_id)
        except (TypeError, ValueError):
            return Response(
                {"error": "Please provide a valid new_waiter_id."},
                status=status.HTTP_400_BAD_REQUEST
            )

        seted_waiter = User.objects.filter(
            id=new_waiter_id, 
            role=UserRole.WAITER, 
            is_active=True
        ).first()

        if not seted_waiter:
            return Response(
                {"error": "Selected waiter is not available."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 3. Create the request (Model handles Manager auto-approval)
        try:
            transfer = ChangeOrderWaiter.create_transfer_request(
                order=current_order,
                created_by_user=request.user,
                seted_waiter=seted_waiter
            )

            if transfer.is_approved:
                return Response(
                    {
                        "message": "Waiter changed successfully (Auto-approved by Manager).", 
                        "approved": True,
                        "order": serialize_order(current_order) # Optional
                    },
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {
                        "message": "Waiter transfer requested. Waiting for approval.",
                        "approved": False,
                        "transfer_id": transfer.id
                    },
                    status=status.HTTP_201_CREATED
                )

        except Exception as exc:
            return Response(
                {"error": f"Unable to request waiter change: {exc}"},
                status=status.HTTP_400_BAD_REQUEST
            )


class ApproveWaiterChangeView(APIView):
    """
    POST — Approve or Deny a pending waiter transfer.
    Body: { "action": "approve" } OR { "action": "deny" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, change_id: int):
        change_req = get_object_or_404(ChangeOrderWaiter, id=change_id)
        
        if change_req.is_approved:
            return Response(
                {"error": "This transfer request has already been processed."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if the frontend wants to approve or deny
        resolve_action = request.data.get("action", "approve").strip().lower()
        approve_bool = (resolve_action == "approve")

        try:
            # The model handles the permission check (Manager or Seted Waiter)
            change_req.approve_or_deny_transfer(
                actioning_user=request.user,
                approve=approve_bool
            )
            
            if approve_bool:
                return Response(
                    {"message": "Waiter successfully changed."}, 
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {"message": "Transfer request denied. Order kept with original waiter."}, 
                    status=status.HTTP_200_OK
                )
            
        except PermissionDenied as e:
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            return Response(
                {"error": f"Unable to process request: {str(e)}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )






logger = logging.getLogger(__name__)


ACTIVE_ORDER_STATUSES = [
    "OPEN",
    "CONFIRMED",
    "PREPARING",
    "READY",
    "SERVED",
]


class RequestWaiterChangeView(APIView):
    """
    POST /api/tables/<table_id>/change-waiter/

    Request body:
    {
        "new_waiter_id": 5
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, table_id: int):
        raw_waiter_id = request.data.get("new_waiter_id")

        try:
            new_waiter_id = int(raw_waiter_id)
            if new_waiter_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "Please provide a valid new_waiter_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        table = get_object_or_404(RestaurantTable, pk=table_id)

        new_waiter = User.objects.filter(
            pk=new_waiter_id,
            role=UserRole.WAITER,
            is_active=True,
        ).first()

        if new_waiter is None:
            return Response(
                {"error": "Selected waiter is not available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            with transaction.atomic():
                # Lock the table's active order while selecting it.
                current_order = (
                    Order.objects
                    .select_for_update()
                    .filter(
                        table=table,
                        status__in=ACTIVE_ORDER_STATUSES,
                    )
                    .order_by("-id")
                    .first()
                )

                if current_order is None:
                    return Response(
                        {"error": "No active order found to transfer."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                transfer = ChangeOrderWaiter.create_transfer_request(
                    order=current_order,
                    created_by_user=request.user,
                    seted_waiter=new_waiter,
                )

                current_order.refresh_from_db()

                if transfer.status == TransferStatus.APPROVED:
                    return Response(
                        {
                            "message": "Waiter changed successfully.",
                            "approved": True,
                            "status": transfer.status,
                            "transfer_id": transfer.pk,
                            "order": serialize_order(current_order),
                        },
                        status=status.HTTP_200_OK,
                    )

                return Response(
                    {
                        "message": (
                            "Waiter transfer requested. "
                            "Waiting for approval."
                        ),
                        "approved": False,
                        "status": transfer.status,
                        "transfer_id": transfer.pk,
                    },
                    status=status.HTTP_201_CREATED,
                )

        except PermissionDenied as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_403_FORBIDDEN,
            )

        except ValidationError as exc:
            return Response(
                {"error": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Order.DoesNotExist:
            return Response(
                {"error": "The order no longer exists."},
                status=status.HTTP_404_NOT_FOUND,
            )

        except Exception:
            logger.exception(
                "Failed to request waiter transfer for table %s",
                table_id,
            )
            return Response(
                {"error": "Unable to request waiter change."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ApproveWaiterChangeView(APIView):
    """
    POST /api/waiter-changes/<change_id>/resolve/

    Request body:
    {
        "action": "approve"
    }

    Or:
    {
        "action": "deny",
        "reason": "Transfer not accepted"
    }
    """

  #  permission_classes = [IsAuthenticated]

    def post(self, request, change_id: int):
        action = request.data.get("action", "approve")

        if not isinstance(action, str):
            return Response(
                {"error": "Action must be 'approve' or 'deny'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action = action.strip().lower()

        if action not in ("approve", "deny"):
            return Response(
                {"error": "Action must be 'approve' or 'deny'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = request.data.get("reason", "")

        if not isinstance(reason, str):
            return Response(
                {"error": "Reason must be a string."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        change_req = get_object_or_404(
            ChangeOrderWaiter,
            pk=change_id,
        )

        try:
            change_req.approve_or_deny_transfer(
                actioning_user=request.user,
                approve=(action == "approve"),
                denial_reason=reason.strip() if action == "deny" else "",
            )

            change_req.refresh_from_db()

            if change_req.status == TransferStatus.APPROVED:
                return Response(
                    {
                        "message": "Waiter successfully changed.",
                        "approved": True,
                        "status": change_req.status,
                        "transfer_id": change_req.pk,
                        "order_id": change_req.order_id,
                        "new_waiter_id": change_req.seted_waiter_id,
                    },
                    status=status.HTTP_200_OK,
                )

            return Response(
                {
                    "message": "Transfer request denied.",
                    "approved": False,
                    "status": change_req.status,
                    "transfer_id": change_req.pk,
                    "order_id": change_req.order_id,
                },
                status=status.HTTP_200_OK,
            )

        except PermissionDenied as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_403_FORBIDDEN,
            )

        except ValidationError as exc:
            return Response(
                {"error": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except ChangeOrderWaiter.DoesNotExist:
            return Response(
                {"error": "Transfer request no longer exists."},
                status=status.HTTP_404_NOT_FOUND,
            )

        except Exception:
            logger.exception(
                "Failed to resolve waiter transfer %s",
                change_id,
            )
            return Response(
                {"error": "Unable to process waiter transfer."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PendingWaiterChangesView(APIView):
    """
    GET /api/waiter-changes/pending/

    Waiters see requests assigned to them.
    Managers see all pending requests.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        is_manager = (
            user.is_staff
            or user.is_superuser
            or getattr(user, "role", "") == "MANAGER"
        )

        if is_manager:
            requests = ChangeOrderWaiter.objects.filter(
                status=TransferStatus.PENDING
            )
        elif getattr(user, "role", "") == "WAITER":
            requests = ChangeOrderWaiter.objects.filter(
                status=TransferStatus.PENDING,
                seted_waiter=user,
            )
        else:
            return Response(
                {"error": "You are not authorized to view these requests."},
                status=status.HTTP_403_FORBIDDEN,
            )

        requests = requests.select_related(
            "order",
            "order__table",
            "current_waiter",
            "seted_waiter",
        ).order_by("-id")

        data = []

        for item in requests:
            data.append({
                "id": item.id,
                "status": item.status,
                "order_id": item.order_id,
                "table_id": item.order.table_id,
                "current_waiter_id": item.current_waiter_id,
                "current_waiter_name": (
                    getattr(item.current_waiter, "full_name", "")
                    if item.current_waiter else None
                ),
                "new_waiter_id": item.seted_waiter_id,
                "new_waiter_name": (
                    getattr(item.seted_waiter, "full_name", "")
                    if item.seted_waiter else None
                ),
                "created_at": item.created_at.isoformat()
                if getattr(item, "created_at", None)
                else None,
            })

        return Response({
            "count": len(data),
            "has_pending_requests": bool(data),
            "requests": data,
        }, status=status.HTTP_200_OK)





class ManagerAttendanceAPI(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        # Only managers and admins can access this API.
        if request.user.role not in (
            UserRole.MANAGER,
            UserRole.ADMIN,
        ):
            raise PermissionDenied

        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)

        day_start = timezone.make_aware(
            datetime.combine(today, time.min)
        )
        day_end = timezone.make_aware(
            datetime.combine(tomorrow, time.min)
        )

        now = timezone.now()

        users = User.objects.filter(
                is_active=True,
            ).exclude(
                state="STOPPED"
            ).order_by(
                "full_name", "username"
            )

        attendance_records = Attendance.objects.filter(
            check_in__lt=day_end,
        ).filter(
            Q(check_out__isnull=True)
            | Q(check_out__gt=day_start)
        ).select_related(
            "user"
        ).order_by("check_in")

        records_by_user = {}

        for record in attendance_records:
            records_by_user.setdefault(
                record.user_id, []
            ).append(record)

        employee_rows = []

        for user in users:
            records = records_by_user.get(user.id, [])

            today_seconds = 0
            active_record = None
            sessions = []

            for record in records:
                session_start = max(
                    record.check_in,
                    day_start,
                )

                session_end = min(
                    record.check_out or now,
                    day_end,
                    now,
                )

                if session_end > session_start:
                    today_seconds += int(
                        (
                            session_end - session_start
                        ).total_seconds()
                    )

                if record.check_out is None:
                    active_record = record

                duration_seconds = max(
                    0,
                    int(
                        (
                            (record.check_out or now)
                            - record.check_in
                        ).total_seconds()
                    ),
                )

                sessions.append({
                    "id": record.id,
                    "check_in": timezone.localtime(
                        record.check_in
                    ).isoformat(),
                    "check_out": (
                        timezone.localtime(
                            record.check_out
                        ).isoformat()
                        if record.check_out else None
                    ),
                    "is_working": record.check_out is None,
                    "duration_seconds": duration_seconds,
                    "duration_hours": round(
                        duration_seconds / 3600, 2
                    ),
                })

            today_hours, today_remainder = divmod(
                today_seconds, 3600
            )
            today_minutes = today_remainder // 60

            target_hours = float(user.daily_working_hours)
            target_seconds = int(target_hours * 3600)

            progress = min(
                100,
                round(today_seconds / target_seconds * 100)
                if target_seconds > 0 else 0,
            )

            shift_seconds = 0

            if active_record:
                shift_seconds = max(
                    0,
                    int(
                        (
                            now - active_record.check_in
                        ).total_seconds()
                    ),
                )

            shift_hours, shift_remainder = divmod(
                shift_seconds, 3600
            )
            shift_minutes = shift_remainder // 60

            employee_rows.append({
                "user_id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "role": user.role,
                "role_display": user.get_role_display(),
                "state": user.state,
                "is_working": active_record is not None,

                "current_check_in": (
                    timezone.localtime(
                        active_record.check_in
                    ).isoformat()
                    if active_record else None 
                ),

                "today": {
                    "date": today.isoformat(),
                    "total_seconds": today_seconds,
                    "hours": today_hours,
                    "minutes": today_minutes,
                },

                "daily_target": {
                    "hours": target_hours,
                    "seconds": target_seconds,
                },

                "progress": {
                    "percentage": progress,
                    "completed": (
                        target_seconds > 0
                        and today_seconds >= target_seconds
                    ),
                    "remaining_seconds": max(
                        0,
                        target_seconds - today_seconds,
                    ),
                },

                "current_shift": {
                    "seconds": shift_seconds,
                    "hours": shift_hours,
                    "minutes": shift_minutes,
                },

                "sessions": sessions,
            })

        working_count = sum(
            1 for employee in employee_rows
            if employee["is_working"]
        )

        total_today_seconds = sum(
            employee["today"]["total_seconds"]
            for employee in employee_rows
        )

        completed_count = sum(
            1 for employee in employee_rows
            if employee["progress"]["completed"]
        )

        return JsonResponse({
            "success": True,
            "date": today.isoformat(),
            "timezone": timezone.get_current_timezone_name(),
            "generated_at": timezone.localtime(now).isoformat(),

            "summary": {
                "employee_count": len(employee_rows),
                "working_count": working_count,
                "not_working_count": (
                    len(employee_rows) - working_count
                ),
                "completed_count": completed_count,
                "total_today_seconds": total_today_seconds,
                "total_today_hours": round(
                    total_today_seconds / 3600, 2
                ),
            },

            "employees": employee_rows,
        })


from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404



@login_required
@require_POST
def attendance_check_in(request, user_id):
    # Get the selected user by ID
    user = get_object_or_404(User, id=user_id)

    # Managers and admins do not need attendance.
    if user.role in ["MANAGER", "ADMIN"]:
        return JsonResponse({
            "success": False,
            "message": "Attendance is not required for managers or admins.",
        }, status=400)

    # Prevent multiple active attendance sessions.
    active_attendance = Attendance.objects.filter(
        user=user,
        check_out__isnull=True,
    ).first()

    if active_attendance:
        return JsonResponse({
            "success": False,
            "message": "This user is already checked in.",
            "user_id": user.id,
            "check_in": timezone.localtime(
                active_attendance.check_in
            ).isoformat(),
        }, status=400)

    attendance = Attendance.objects.create(
        user=user,
        check_in=timezone.now(),
    )

    return JsonResponse({
        "success": True,
        "message": "Check-in successful.",
        "user_id": user.id,
        "check_in": timezone.localtime(
            attendance.check_in
        ).isoformat(),
    })



from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from orders.models import Order, OrderStatus


ACTIVE_ORDER_STATUSES = (
    OrderStatus.OPEN,
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.SERVED,
)


@login_required
@require_POST
def attendance_check_out(request, user_id):
    user = get_object_or_404(User, id=user_id)

    # Managers and admins do not require attendance.
    if user.role in ("MANAGER", "ADMIN"):
        return JsonResponse({
            "success": False,
            "message": "Attendance is not required for managers or admins.",
        }, status=400)

    # Find the user's active attendance session.
    attendance = Attendance.objects.filter(
        user=user,
        check_out__isnull=True,
    ).order_by("-check_in").first()

    if not attendance:
        return JsonResponse({
            "success": False,
            "message": "This user is not currently checked in.",
            "user_id": user.id,
        }, status=400)

    # Block waiter checkout if they still have active orders.
    if user.role == "WAITER":
        active_orders = Order.objects.filter(
            waiter=user,
            status__in=ACTIVE_ORDER_STATUSES,
        ).select_related("table")

        if active_orders.exists():
            orders_data = [
                {
                    "order_id": order.id,
                    "table_id": order.table_id,
                    "table": str(order.table),
                    "status": order.status,
                    "total": str(order.total),
                }
                for order in active_orders
            ]

            return JsonResponse({
                "success": False,
                "message": (
                    "Checkout blocked. Please complete payment or "
                    "transfer all active orders before checking out."
                ),
                "user_id": user.id,
                "active_orders_count": len(orders_data),
                "active_orders": orders_data,
            }, status=400)

    # Allow checkout when no active orders remain.
    attendance.check_out = timezone.now()
    attendance.save(update_fields=["check_out"])

    return JsonResponse({
        "success": True,
        "message": "Check-out successful.",
        "user_id": user.id,
        "check_out": timezone.localtime(
            attendance.check_out
        ).isoformat(),
        "working_hours": attendance.working_hours,
        "working_time": attendance.working_time_display,
    })







import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET




User = get_user_model()


# ---------------------------------------------------------
# Permissions
# ---------------------------------------------------------

def _can_manage_attendance(user):
    return (
        user.is_superuser
        or getattr(user, "role", "") in ("MANAGER", "ADMIN")
    )


def _employee_target_hours(employee):
    """
    Get the employee's daily working-hour target.
    Falls back to 8 hours if the field is empty or invalid.
    """
    value = getattr(employee, "daily_working_hours", None)

    try:
        value = Decimal(str(value))
        if not value.is_finite() or value <= 0:
            return Decimal("8")
        return value
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("8")


# ---------------------------------------------------------
# Duration helpers
# ---------------------------------------------------------

def _duration_seconds(check_in, check_out=None):
    if not check_in:
        return 0

    end = check_out or timezone.now()

    # Avoid subtracting naive and aware datetimes.
    if timezone.is_aware(check_in) and timezone.is_naive(end):
        end = timezone.make_aware(end, timezone.get_current_timezone())
    elif timezone.is_naive(check_in) and timezone.is_aware(end):
        check_in = timezone.make_aware(
            check_in,
            timezone.get_current_timezone(),
        )

    return max(0, int((end - check_in).total_seconds()))


def _format_duration(total_seconds):
    total_seconds = max(0, int(total_seconds))

    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60

    return f"{hours:02d}:{minutes:02d}"


def _local_datetime(value):
    if not value:
        return None

    if timezone.is_aware(value):
        value = timezone.localtime(value)

    return value.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------
# Attendance queries
# ---------------------------------------------------------

def _attendance_for_user(employee, start, end):
    """
    Get sessions that start inside the requested date range.
    """
    return list(
        Attendance.objects.filter(
            user=employee,
            check_in__gte=start,
            check_in__lt=end,
        ).order_by("check_in")
    )


def _daily_sessions(sessions, day):
    """
    Group attendance sessions by the local date of check-in.
    """
    result = []

    for session in sessions:
        if not session.check_in:
            continue

        check_in = session.check_in

        if timezone.is_aware(check_in):
            check_in = timezone.localtime(check_in)

        if check_in.date() == day:
            result.append(session)

    return result


# ---------------------------------------------------------
# Daily summary
# ---------------------------------------------------------

def _day_summary(day_sessions, target_hours, today, day):
    target_hours = Decimal(str(target_hours or 8))
    target_seconds = int(target_hours * 3600)

    worked_seconds = sum(
        _duration_seconds(session.check_in, session.check_out)
        for session in day_sessions
    )

    has_active_session = any(
        session.check_out is None
        for session in day_sessions
    )

    if worked_seconds >= target_seconds and day_sessions:
        status = "completed"

    elif day_sessions:
        if has_active_session and day == today:
            status = "in_progress"
        else:
            status = "short"

    elif day > today:
        status = "future"

    elif day == today:
        status = "today"

    else:
        status = "missing"

    remaining_seconds = max(0, target_seconds - worked_seconds)

    return {
        "date": day.isoformat(),
        "status": status,
        "worked_seconds": worked_seconds,
        "worked_time": _format_duration(worked_seconds),
        "target_seconds": target_seconds,
        "target_hours": float(target_hours),
        "remaining_seconds": remaining_seconds,
        "remaining_time": _format_duration(remaining_seconds),
        "sessions_count": len(day_sessions),
        "has_active_session": has_active_session,
    }


# ---------------------------------------------------------
# Employee attendance page
# URL: manager/employees/<int:user_id>/attendance/
# ---------------------------------------------------------

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render


@login_required
def employee_attendance_page(request, user_id):
    if not _can_manage_attendance(request.user):
        return JsonResponse(
            {"error": "You do not have permission to view attendance."},
            status=403,
        )

    employee = get_object_or_404(User, pk=user_id)
    target_hours = _employee_target_hours(employee)

    # Accepted day-off requests for this employee
    accepted_day_offs = DayOffRequest.objects.filter(
        user=employee,
        status="ACCEPTED",
    ).order_by("-created_at")

    return render(
        request,
        "attendance/employee_attendance.html",
        {
            "employee": employee,
            "daily_target_hours": float(target_hours),
            "accepted_day_offs": accepted_day_offs,
        },
    )
# ---------------------------------------------------------
# Monthly attendance calendar API
# URL: api/v1/attendance/<int:user_id>/calendar/
# Query parameters: ?year=2026&month=10
# ---------------------------------------------------------

@login_required
@require_GET
def employee_attendance_calendar_api(request, user_id):
    if not _can_manage_attendance(request.user):
        return JsonResponse(
            {"error": "You do not have permission to view attendance."},
            status=403,
        )

    employee = get_object_or_404(User, pk=user_id)

    today = timezone.localdate()
    target_hours = _employee_target_hours(employee)

    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))

        if not 1 <= month <= 12:
            raise ValueError

        date(year, month, 1)

    except (TypeError, ValueError):
        return JsonResponse(
            {"error": "Invalid year or month."},
            status=400,
        )

    first_day = date(year, month, 1)
    last_day_number = calendar.monthrange(year, month)[1]

    next_month = (
        date(year + 1, 1, 1)
        if month == 12
        else date(year, month + 1, 1)
    )

    start_datetime = timezone.make_aware(
        datetime.combine(first_day, time.min),
        timezone.get_current_timezone(),
    )

    end_datetime = timezone.make_aware(
        datetime.combine(next_month, time.min),
        timezone.get_current_timezone(),
    )

    # ---------------------------------------------------------
    # Attendance sessions for the selected month
    # ---------------------------------------------------------
    sessions = _attendance_for_user(
        employee,
        start_datetime,
        end_datetime,
    )

    # ---------------------------------------------------------
    # Accepted day-off requests for the selected month
    # Model fields: user, date, status
    # ---------------------------------------------------------
    accepted_day_off_dates = set(
        DayOffRequest.objects.filter(
            user=employee,
            date__gte=first_day,
            date__lt=next_month,
        ).exclude(status="REJECTED").values_list("date", flat=True))

    days = []

    completed_days = 0
    short_days = 0
    missing_days = 0
    day_off_days = 0
    total_worked_seconds = 0

    # ---------------------------------------------------------
    # Build each calendar day
    # ---------------------------------------------------------
    for day_number in range(1, last_day_number + 1):
        current_day = date(year, month, day_number)

        day_sessions = _daily_sessions(
            sessions,
            current_day,
        )

        summary = _day_summary(
            day_sessions=day_sessions,
            target_hours=target_hours,
            today=today,
            day=current_day,
        )

        # Keep actual worked time even when the date is a day off.
        total_worked_seconds += summary.get(
            "worked_seconds", 0
        )

        if current_day in accepted_day_off_dates:
            # An accepted day off must not be counted as missing.
            summary["status"] = "day_off"
            day_off_days += 1

        elif summary["status"] == "completed":
            completed_days += 1

        elif summary["status"] == "short":
            short_days += 1

        elif summary["status"] == "missing":
            missing_days += 1

        days.append(summary)

    # ---------------------------------------------------------
    # Response
    # ---------------------------------------------------------
    return JsonResponse({
        "employee": {
            "id": employee.pk,
            "name": (
                getattr(employee, "full_name", None)
                or employee.get_username()
            ),
        },
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "daily_target_hours": float(target_hours),
        "days_in_month": last_day_number,
        "summary": {
            "completed_days": completed_days,
            "short_days": short_days,
            "missing_days": missing_days,
            "day_off_days": day_off_days,
            "total_worked_seconds": total_worked_seconds,
            "total_worked_time": _format_duration(
                total_worked_seconds
            ),
        },
        "days": days,
    })

# ---------------------------------------------------------
# Attendance details for one day
# URL: api/v1/attendance/<int:user_id>/day/
# Query parameter: ?date=2026-10-27
# ---------------------------------------------------------

@login_required
@require_GET
def employee_attendance_day_api(request, user_id):
    if not _can_manage_attendance(request.user):
        return JsonResponse(
            {"error": "You do not have permission to view attendance."},
            status=403,
        )

    employee = get_object_or_404(User, pk=user_id)

    target_hours = _employee_target_hours(employee)
    today = timezone.localdate()

    # ---------------------------------------------------------
    # Read selected date
    # ---------------------------------------------------------
    date_value = request.GET.get("date")

    if not date_value:
        selected_day = today
    else:
        try:
            selected_day = date.fromisoformat(date_value)
        except (TypeError, ValueError):
            return JsonResponse(
                {"error": "Invalid date. Use YYYY-MM-DD."},
                status=400,
            )

    # ---------------------------------------------------------
    # Find accepted day-off request for this date
    # ---------------------------------------------------------
    day_off_request = (
        DayOffRequest.objects.filter(
            user=employee,date=selected_day
        ).exclude(status="REJECTED").order_by("-created_at")
        .first()
    )

    # ---------------------------------------------------------
    # Get attendance sessions
    # ---------------------------------------------------------
    start_datetime = timezone.make_aware(
        datetime.combine(selected_day, time.min),
        timezone.get_current_timezone(),
    )

    end_datetime = start_datetime + timedelta(days=1)

    sessions = _attendance_for_user(
        employee,
        start_datetime,
        end_datetime,
    )

    # ---------------------------------------------------------
    # Calculate the normal attendance summary
    # ---------------------------------------------------------
    summary = _day_summary(
        day_sessions=sessions,
        target_hours=target_hours,
        today=today,
        day=selected_day,
    )

    # ---------------------------------------------------------
    # Override the status when the day off was accepted
    # ---------------------------------------------------------
    if day_off_request:
        summary["status"] = "day_off"

    # ---------------------------------------------------------
    # Serialize attendance sessions
    # ---------------------------------------------------------
    session_data = []

    for session in sessions:
        duration = _duration_seconds(
            session.check_in,
            session.check_out,
        )

        session_data.append({
            "id": session.pk,
            "check_in": _local_datetime(session.check_in),
            "check_out": _local_datetime(session.check_out),
            "worked_seconds": duration,
            "worked_time": _format_duration(duration),
            "is_active": session.check_out is None,
        })

    # ---------------------------------------------------------
    # Serialize accepted day-off request
    # ---------------------------------------------------------
    day_off_data = None

    if day_off_request:
        day_off_data = {
            "id": day_off_request.pk,
            "date": day_off_request.date.isoformat(),
            "status": day_off_request.status,
            "reason": day_off_request.reason,
            "review_note": day_off_request.review_note,
        }

        if day_off_request.reviewed_at:
            day_off_data["reviewed_at"] = (
                _local_datetime(day_off_request.reviewed_at)
            )

        if day_off_request.reviewed_by:
            day_off_data["reviewed_by"] = (
                getattr(
                    day_off_request.reviewed_by,
                    "full_name",
                    None,
                )
                or day_off_request.reviewed_by.get_username()
            )

    # ---------------------------------------------------------
    # Response
    # ---------------------------------------------------------
    return JsonResponse({
        "employee": {
            "id": employee.pk,
            "name": (
                getattr(employee, "full_name", None)
                or employee.get_username()
            ),
        },
        "date": selected_day.isoformat(),
        "daily_target_hours": float(target_hours),
        "summary": summary,
        "day_off": day_off_data,
        "sessions": session_data,
    })
#phone 
import calendar
from datetime import date, datetime, time, timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView



class AttendanceBaseAPIView(APIView):
    """
    Base class for attendance APIs.
    Authentication: Authorization: Token <token>
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_employee(self, user_id):
        employee = User.objects.filter(pk=user_id).first()

        if employee is None:
            return None

        return employee

    def can_manage(self, request):
        return _can_manage_attendance(request.user)

    def can_view_user_attendance(self, request, target_user_id):
        """
        Allow an employee to view their own attendance, or allow managers/admins to view any employee.
        """
        return (request.user.pk == target_user_id) or self.can_manage(request)

    def employee_data(self, employee):
        return {
            "id": employee.pk,
            "name": (
                getattr(employee, "full_name", None)
                or employee.get_username()
            ),
        }


class EmployeeAttendanceCalendarAPI(AttendanceBaseAPIView):
    """
    GET /api/v1/attendance/<user_id>/calendar/?year=2026&month=10
    """

    def get(self, request, user_id):
        if not self.can_view_user_attendance(request, user_id):
            return Response(
                {"error": "You do not have permission to view attendance."},
                status=status.HTTP_403_FORBIDDEN,
            )

        employee = self.get_employee(user_id)

        if employee is None:
            return Response(
                {"error": "Employee not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        today = timezone.localdate()
        target_hours = _employee_target_hours(employee)

        try:
            year = int(request.query_params.get("year", today.year))
            month = int(request.query_params.get("month", today.month))

            if not 1 <= month <= 12:
                raise ValueError

            date(year, month, 1)

        except (TypeError, ValueError):
            return Response(
                {"error": "Invalid year or month."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        first_day = date(year, month, 1)
        last_day_number = calendar.monthrange(year, month)[1]

        next_month = (
            date(year + 1, 1, 1)
            if month == 12
            else date(year, month + 1, 1)
        )

        current_tz = timezone.get_current_timezone()

        start_datetime = timezone.make_aware(
            datetime.combine(first_day, time.min),
            current_tz,
        )

        end_datetime = timezone.make_aware(
            datetime.combine(next_month, time.min),
            current_tz,
        )

        sessions = _attendance_for_user(
            employee,
            start_datetime,
            end_datetime,
        )

        days = []
        completed_days = 0
        short_days = 0
        missing_days = 0
        total_worked_seconds = 0

        for day_number in range(1, last_day_number + 1):
            current_day = date(year, month, day_number)

            day_sessions = _daily_sessions(
                sessions,
                current_day,
            )

            summary = _day_summary(
                day_sessions=day_sessions,
                target_hours=target_hours,
                today=today,
                day=current_day,
            )

            total_worked_seconds += summary["worked_seconds"]

            if summary["status"] == "completed":
                completed_days += 1
            elif summary["status"] == "short":
                short_days += 1
            elif summary["status"] == "missing":
                missing_days += 1

            days.append(summary)

        return Response({
            "employee": self.employee_data(employee),
            "year": year,
            "month": month,
            "month_name": calendar.month_name[month],
            "daily_target_hours": float(target_hours),
            "days_in_month": last_day_number,
            "summary": {
                "completed_days": completed_days,
                "short_days": short_days,
                "missing_days": missing_days,
                "total_worked_seconds": total_worked_seconds,
                "total_worked_time": _format_duration(
                    total_worked_seconds
                ),
            },
            "days": days,
        })


class EmployeeAttendanceDayAPI(AttendanceBaseAPIView):
    """
    GET /api/v1/attendance/<user_id>/day/?date=2026-10-27
    """

    def get(self, request, user_id):
        if not self.can_view_user_attendance(request, user_id):
            return Response(
                {"error": "You do not have permission to view attendance."},
                status=status.HTTP_403_FORBIDDEN,
            )

        employee = self.get_employee(user_id)

        if employee is None:
            return Response(
                {"error": "Employee not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        target_hours = _employee_target_hours(employee)
        today = timezone.localdate()

        date_value = request.query_params.get("date")

        if not date_value:
            selected_day = today
        else:
            try:
                selected_day = date.fromisoformat(date_value)
            except (TypeError, ValueError):
                return Response(
                    {"error": "Invalid date. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        current_tz = timezone.get_current_timezone()

        start_datetime = timezone.make_aware(
            datetime.combine(selected_day, time.min),
            current_tz,
        )

        end_datetime = start_datetime + timedelta(days=1)

        sessions = _attendance_for_user(
            employee,
            start_datetime,
            end_datetime,
        )

        summary = _day_summary(
            day_sessions=sessions,
            target_hours=target_hours,
            today=today,
            day=selected_day,
        )

        session_data = []

        for session in sessions:
            duration = _duration_seconds(
                session.check_in,
                session.check_out,
            )

            session_data.append({
                "id": session.pk,
                "check_in": _local_datetime(session.check_in),
                "check_out": _local_datetime(session.check_out),
                "worked_seconds": duration,
                "worked_time": _format_duration(duration),
                "is_active": session.check_out is None,
            })

        return Response({
            "employee": self.employee_data(employee),
            "date": selected_day.isoformat(),
            "daily_target_hours": float(target_hours),
            "summary": summary,
            "sessions": session_data,
        })




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user_profile(request):
     """ GET /api/v1/auth/me/ Returns the latest user profile and working state. """ 
     user = request.user
     return Response({ "id": user.pk, "username": user.username, "email": user.email, "role": user.role, "state": user.state, })



class EmployeeDayOffRequestsAPI(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def serialize_request(self, item):
        reviewer = item.reviewed_by

        return {
            "id": item.id,
            "user_id": item.user_id,
            "employee_name": (
                item.user.get_full_name()
                or item.user.get_username()
            ),
            "date": item.date.isoformat(),
            "reason": item.reason,
            "status": item.status,
            "reviewed_by": (
                reviewer.get_full_name()
                or reviewer.get_username()
                if reviewer else None
            ),
            "reviewed_at": (
                item.reviewed_at.isoformat()
                if item.reviewed_at else None
            ),
            "review_note": item.review_note,
            "created_at": item.created_at.isoformat(),
        }

    # GET: List the authenticated employee's requests
    def get(self, request):
        requests_qs = (
            DayOffRequest.objects
            .filter(user=request.user)
            .select_related("user", "reviewed_by")
            .order_by("-date", "-created_at")
        )

        return Response({
            "success": True,
            "count": requests_qs.count(),
            "results": [
                self.serialize_request(item)
                for item in requests_qs
            ],
            "today": timezone.localdate().isoformat(),
        })

    # POST: Create a day-off request
    def post(self, request):
        requested_date_value = request.data.get("date")
        reason = request.data.get("reason", "")

        if not requested_date_value:
            return Response(
                {
                    "success": False,
                    "message": "The date field is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(requested_date_value, str):
            return Response(
                {
                    "success": False,
                    "message": "The date must use YYYY-MM-DD format.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        requested_date = parse_date(requested_date_value)

        if requested_date is None:
            return Response(
                {
                    "success": False,
                    "message": "Invalid date. Use YYYY-MM-DD format.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.localdate()

        # Prevent requests for dates in the past.
        if requested_date < today:
            return Response(
                {
                    "success": False,
                    "message": "You cannot request a day off in the past.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if reason is None:
            reason = ""

        if not isinstance(reason, str):
            return Response(
                {
                    "success": False,
                    "message": "The reason must be text.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = reason.strip()

        if len(reason) > 500:
            return Response(
                {
                    "success": False,
                    "message": "The reason cannot exceed 500 characters.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prevent duplicate pending or approved requests.
        duplicate_exists = DayOffRequest.objects.filter(
            user=request.user,
            date=requested_date,
            status__in=[
                DayOffStatus.PENDING,
                DayOffStatus.APPROVED,
            ],
        ).exists()

        if duplicate_exists:
            return Response(
                {
                    "success": False,
                    "message": (
                        "You already have a pending or approved "
                        "request for this date."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        day_off_request = DayOffRequest.objects.create(
            user=request.user,
            date=requested_date,
            reason=reason,
            status=DayOffStatus.PENDING,
        )

        return Response(
            {
                "success": True,
                "message": "Day-off request submitted successfully.",
                "request": self.serialize_request(day_off_request),
            },
            status=status.HTTP_201_CREATED,
        )
