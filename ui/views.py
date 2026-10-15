from decimal import Decimal

from django.shortcuts import render
from django.db import transaction
# Create your views here.
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from requests import request
from orders.models import *
from Financial.models import *

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

from orders.models import (
    Order,
    OrderStatus,
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
        TableStatus.AVAILABLE: "#ffffff",
        TableStatus.OCCUPIED: "#70eb04",
        TableStatus.RESERVED: "#ff00bb",
        TableStatus.CLOSED: "#ff0000",
        TableStatus.ON_PAYMENT: "#1100ff",
    }

    # ---------------------------------------------------------
    # Build Dashboard Tables
    # ---------------------------------------------------------
    dashboard_tables = []

    for table in tables:
        waiter_name = ""
        order_total = None

        # Only look for an order when the table is not available
        if table.status != TableStatus.AVAILABLE:
            order = latest_order_by_table.get(table.id)

            if order:
                waiter_name = (
                    order.waiter.full_name
                    or order.waiter.username
                )

                order_total = order.total

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


@login_required
def table_list(request):
    """
    Main restaurant tables dashboard.

    Shows:
    - table sections
    - active tables
    - current table status
    - active order information
    - table summary counters
    """

    # ---------------------------------------------------------
    # Permission
    # ---------------------------------------------------------

    if request.user.role not in ["ADMIN", "MANAGER", "WAITER"]:
        return redirect("login")

    # ---------------------------------------------------------
    # Sections
    # ---------------------------------------------------------

    section_blocks = (
        SectionBlock.objects
        .filter(is_active=True)
        .prefetch_related(
            Prefetch(
                "tables",
                queryset=(
                    RestaurantTable.objects
                    .filter(is_active=True)
                    .order_by("table_number")
                ),
            )
        )
        .order_by("display_order", "name")
    )

    # ---------------------------------------------------------
    # Tables
    # ---------------------------------------------------------

    tables = (
        RestaurantTable.objects
        .filter(is_active=True)
        .select_related("section_block")
        .prefetch_related(
            Prefetch(
                "orders",
                queryset=(
                    Order.objects
                    .filter(
                        status__in=[
                            OrderStatus.OPEN,
                            OrderStatus.CONFIRMED,
                            OrderStatus.PREPARING,
                            OrderStatus.READY,
                            OrderStatus.SERVED,
                        ]
                    )
                    .prefetch_related("items__product")
                    .order_by("-created_at")
                ),
                to_attr="active_orders",
            )
        )
        .order_by(
            "section_block__display_order",
            "section_block__name",
            "table_number",
        )
    )

    # ---------------------------------------------------------
    # Attach current order to each table
    # ---------------------------------------------------------

    for table in tables:

        table.current_order = (
            table.active_orders[0]
            if table.active_orders
            else None
        )

    # ---------------------------------------------------------
    # Status counts
    # ---------------------------------------------------------

    available_count = tables.filter(
        status=TableStatus.AVAILABLE
    ).count()

    occupied_count = tables.filter(
        status=TableStatus.OCCUPIED
    ).count()

    reserved_count = tables.filter(
        status=TableStatus.RESERVED
    ).count()

    payment_count = tables.filter(
        status=TableStatus.ON_PAYMENT
    ).count()

    closed_count = tables.filter(
        status=TableStatus.CLOSED
    ).count()

    # ---------------------------------------------------------
    # Total
    # ---------------------------------------------------------

    total_count = tables.count()

    # ---------------------------------------------------------
    # Section data
    # ---------------------------------------------------------

    section_data = []

    for section in section_blocks:

        section_tables = [
            table
            for table in tables
            if table.section_block_id == section.id
        ]

        section_data.append({
            "section": section,
            "tables": section_tables,
            "count": len(section_tables),
        })

    # ---------------------------------------------------------
    # Context
    # ---------------------------------------------------------

    context = {
        "tables": tables,
        "section_blocks": section_blocks,
        "section_data": section_data,

        "total_count": total_count,

        "available_count": available_count,
        "occupied_count": occupied_count,
        "reserved_count": reserved_count,
        "payment_count": payment_count,
        "closed_count": closed_count,

        "table_statuses": TableStatus.choices,
    }

    return render(
        request,
        "ui/tables.html",
        context,
    )


def test(request):
    return render(
        request,
        "ui/test.html",
    )
def admin_table_detail(request, table_id: int):
    table = get_object_or_404(
        RestaurantTable,
        id=table_id,
    )

    section_blocks = list(
        SectionBlock.objects
        .filter(is_active=True)
        .order_by("display_order", "name")
    )

    active_statuses = [
        OrderStatus.OPEN,
        OrderStatus.CONFIRMED,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.SERVED,
        OrderStatus.PAID,
    ]

    # ============================================================
    # SECTIONS + AVAILABLE TABLES (for the change-table modal)
    #
    # Two-step picker:
    #   1. Choose a section
    #   2. Choose an available table in that section
    #
    # A table is "available" when:
    #   - it is active
    #   - it is NOT the current table
    #   - its status is not OCCUPIED / ON_PAYMENT / RESERVED / CLOSED
    # ============================================================

    available_tables_qs = (
        RestaurantTable.objects
        .filter(is_active=True)
        .exclude(pk=table.pk)
        .exclude(
            status__in=[
                TableStatus.OCCUPIED,
                TableStatus.ON_PAYMENT,
                TableStatus.RESERVED,
                TableStatus.CLOSED,
            ]
        )
        .select_related("section_block")
        .order_by(
            "section_block__display_order",
            "table_number",
        )
    )

    # Group available tables by section for the two-step picker.
    available_tables_by_section = {}

    for t in available_tables_qs:
        section = t.section_block
        if section is None:
            continue
        available_tables_by_section.setdefault(
            section.id, []
        ).append(t)

    # Build a JSON-friendly structure for the template.
    sections_payload = []
    for section in section_blocks:
        tables = available_tables_by_section.get(section.id, [])
        if not tables:
            continue  # skip sections with no available tables
        sections_payload.append({
            "id": section.id,
            "name": section.name,
            "tables": [
                {
                    "id": t.id,
                    "table_number": t.table_number,
                    "name": t.name or f"Table {t.table_number}",
                    "capacity": t.capacity,
                }
                for t in tables
            ],
        })

    # ============================================================
    # HELPERS
    # ============================================================

    def get_current_order() -> Order | None:
        return (
            Order.objects
            .filter(
                table=table,
                status__in=active_statuses,
            )
            .exclude(
                table__status=TableStatus.AVAILABLE,
            )
            .select_related("waiter")
            .prefetch_related(
                "items__product",
            )
            .order_by("-created_at")
            .first()
        )

    def recalculate_order_totals(order: Order) -> None:
        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")

        for item in order.items.select_related("product"):
            quantity_decimal = Decimal(str(item.quantity))

            line_subtotal = (
                item.unit_price * quantity_decimal
            )

            line_tax = (
                line_subtotal
                * item.product.tax_rate
                / Decimal("100")
            )

            subtotal += line_subtotal
            tax_total += line_tax

        total = (
            subtotal
            + tax_total
            - order.discount
        )

        if total < Decimal("0.00"):
            total = Decimal("0.00")

        order.subtotal = subtotal
        order.tax = tax_total
        order.total = total

        order.save(
            update_fields=[
                "subtotal",
                "tax",
                "total",
            ]
        )

    def parse_quantity(
        raw_value: str | None,
    ) -> Decimal | None:

        if raw_value is None:
            return None

        try:
            quantity = Decimal(
                str(raw_value)
            )
        except Exception:
            return None

        if quantity < Decimal("0.50"):
            return None

        return quantity.quantize(
            Decimal("0.01")
        )

    def format_quantity(
        value: Decimal,
    ) -> str:

        normalized = value.normalize()

        if normalized == normalized.to_integral():
            return str(
                normalized.to_integral()
            )

        return (
            f"{value:.2f}"
            .rstrip("0")
            .rstrip(".")
        )

    # ============================================================
    # CATEGORIES / PRODUCTS
    # ============================================================

    categories = list(
        Category.objects
        .filter(is_active=True)
        .order_by(
            "display_order",
            "name",
        )
        .prefetch_related(
            "products",
        )
    )

    products_by_category = []
    products_flat = []

    for category in categories:

        category_products = [
            product
            for product in category.products.all()
            if product.is_active
        ]

        if not category_products:
            continue

        sorted_products = sorted(
            category_products,
            key=lambda product: product.name.lower(),
        )

        products_by_category.append(
            {
                "category": category,
                "products": sorted_products,
            }
        )

        for product in sorted_products:

            current_price = (
                product.get_current_price()
            )

            meta_text = (
                f"{format_currency(current_price)}"
                f" · {category.name}"
            )

            if product.description:
                meta_text = (
                    f"{meta_text}"
                    f" · {product.description}"
                )

            products_flat.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "category_id": category.id,
                    "current_price": current_price,
                    "meta_text": meta_text,
                }
            )

    # ============================================================
    # INITIAL STATE
    # ============================================================

    form_error = ""

    form_success = (
        request.GET.get("created") == "1"
    )

    delete_item_success = (
        request.GET.get("item_deleted") == "1"
    )

    update_item_success = (
        request.GET.get("item_updated") == "1"
    )

    delete_order_success = (
        request.GET.get("order_deleted") == "1"
    )

    invoice_printed = (
        request.GET.get("invoice_printed") == "1"
    )

    order_paid = (
        request.GET.get("order_paid") == "1"
    )

    order_items_printed = (
        request.GET.get("order_items_printed") == "1"
    )

    table_changed = (
        request.GET.get("table_changed") == "1"
    )

    selected_quantities: dict[
        int,
        Decimal,
    ] = {}

    selected_notes: dict[
        int,
        str,
    ] = {}

    money_sources = list(
        MoneySource.objects
        .filter(is_active=True)
        .order_by("name")
    )

    # ============================================================
    # POST ACTIONS
    # ============================================================

    if request.method == "POST":

        action = request.POST.get(
            "action",
            "create_order",
        )

        # ========================================================
        # PRINT CUSTOMER INVOICE
        # ========================================================

        if action == "print_invoice":

            current_order = get_current_order()

            if current_order is None:

                form_error = (
                    "No active order found "
                    "to print an invoice for."
                )

            else:

                current_order.set_order_as_printed()

                return redirect(
                    f"{request.path}?invoice_printed=1"
                )

        # ========================================================
        # MARK ORDER AS PAID
        # ========================================================

        elif action == "mark_paid":

            current_order = get_current_order()

            raw_money_source_id = (
                request.POST
                .get("money_source_id", "")
                .strip()
            )

            # ----------------------------------------------------
            # CHECK ACTIVE ORDER
            # ----------------------------------------------------

            if current_order is None:

                form_error = (
                    "No active order found "
                    "to set as paid."
                )

            # ----------------------------------------------------
            # CHECK ORDER STATUS
            # ----------------------------------------------------

            elif current_order.status == OrderStatus.PAID:

                form_error = (
                    "This order has already been paid."
                )

            # ----------------------------------------------------
            # VALIDATE MONEY SOURCE
            # ----------------------------------------------------

            else:

                try:

                    money_source_id = int(
                        raw_money_source_id
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    money_source_id = 0

                if money_source_id <= 0:

                    form_error = (
                        "Please select a money source "
                        "before marking the order as paid."
                    )

                else:

                    money_source = (
                        MoneySource.objects
                        .filter(
                            id=money_source_id,
                            is_active=True,
                        )
                        .first()
                    )

                    if money_source is None:

                        form_error = (
                            "Selected money source "
                            "is not available."
                        )

                    else:

                        try:

                            current_order.set_order_as_paid(
                                income_source_id=money_source.id,
                                received_by_who=request.user,
                            )

                            return redirect(
                                "admin_tables"
                            )

                        except Exception as exc:

                            form_error = (
                                "Unable to mark "
                                "the order as paid: "
                                f"{exc}"
                            )

        # ========================================================
        # CHANGE TABLE
        #
        # Two-step picker in the UI:
        #   1. Choose a section
        #   2. Choose an available table in that section
        #
        # Only available tables are shown (excluding the current
        # table and any table that is OCCUPIED / ON_PAYMENT /
        # RESERVED / CLOSED).
        # ========================================================

        elif action == "change_table":

            current_order = get_current_order()

            if current_order is None:

                form_error = (
                    "No active order found "
                    "to change the table for."
                )

            elif current_order.status in (
                OrderStatus.PAID,
                OrderStatus.CANCELLED,
            ):

                form_error = (
                    "Cannot change the table of a paid "
                    "or cancelled order."
                )

            else:

                raw_table_id = (
                    request.POST
                    .get("new_table_id", "")
                    .strip()
                )

                try:
                    new_table_id = int(raw_table_id)
                except (TypeError, ValueError):
                    new_table_id = 0

                if new_table_id <= 0:

                    form_error = (
                        "Please select a section and a "
                        "table before confirming."
                    )

                else:

                    try:

                        current_order.change_table(
                            new_table_id=new_table_id,
                        )

                        # ------------------------------------------
                        # Redirect to the *new* table's admin page
                        # so the user lands on the correct screen.
                        # ------------------------------------------
                        return redirect(
                            "admin_table_detail",
                            table_id=new_table_id,
                        )

                    except ValidationError as exc:

                        if hasattr(exc, "messages"):
                            form_error = " ".join(exc.messages)
                        else:
                            form_error = str(exc)

                    except Exception as exc:

                        form_error = (
                            "Unable to change the table: "
                            f"{exc}"
                        )

        # ========================================================
        # PRINT PENDING KITCHEN / SECTION ITEMS
        #
        # IMPORTANT:
        # This is the ONLY place where pending OrderItems
        # are sent to the printer.
        #
        # Creating or adding an order item does NOT print it.
        # ========================================================

        elif action == "print_pending_items":

            current_order = get_current_order()

            if current_order is None:

                form_error = (
                    "No active order found to print."
                )

            else:

                pending_items = (
                    OrderItem.objects
                    .filter(
                        order=current_order,
                        has_print_job=False,
                    )
                    .select_related(
                        "product",
                        "product__section",
                    )
                )

                if not pending_items.exists():

                    form_error = (
                        "There are no unprinted "
                        "items in this order."
                    )

                else:

                    jobs = (
                        OrderItem.print_pending_items(
                            current_order, request.user
                        )
                    )

                    if not jobs:

                        form_error = (
                            "Unprinted items were found, "
                            "but no active printer is "
                            "configured for their section."
                        )

                    else:

                        failed_jobs = [
                            job
                            for job in jobs
                            if job.status
                            == PrintJobStatus.FAILED
                        ]

                        if failed_jobs:

                            form_error = (
                                f"{len(failed_jobs)} "
                                "print job(s) failed."
                            )

                        else:

                            return redirect(
                                f"{request.path}"
                                "?order_items_printed=1"
                            )

        # ========================================================
        # PRINT ORDER ITEMS
        #
        # Keep this action as an alias if your template currently
        # submits action="print_order_items".
        # ========================================================

        elif action == "print_order_items":

            current_order = get_current_order()

            if current_order is None:

                form_error = (
                    "No active order found to print."
                )

            else:

                pending_items = (
                    OrderItem.objects
                    .filter(
                        order=current_order,
                        has_print_job=False,
                    )
                    .select_related(
                        "product",
                        "product__section",
                    )
                )

                if not pending_items.exists():

                    form_error = (
                        "There are no new order "
                        "items to print."
                    )

                else:

                    jobs = (
                        OrderItem.print_pending_items(
                            current_order, request.user
                        )
                    )

                    if not jobs:

                        form_error = (
                            "There are pending items, "
                            "but no active printer is "
                            "configured for their section."
                        )

                    else:

                        failed_jobs = [
                            job
                            for job in jobs
                            if job.status
                            == PrintJobStatus.FAILED
                        ]

                        if failed_jobs:

                            form_error = (
                                f"{len(failed_jobs)} "
                                "print job(s) failed."
                            )

                        else:

                            return redirect(
                                f"{request.path}"
                                "?order_items_printed=1"
                            )

        # ========================================================
        # UPDATE ORDER ITEM
        # ========================================================

        elif action == "update_item":

            current_order = get_current_order()

            raw_item_id = request.POST.get(
                "order_item_id"
            )

            try:

                item_id = int(
                    raw_item_id
                )

            except (
                TypeError,
                ValueError,
            ):

                item_id = 0

            new_quantity = parse_quantity(
                request.POST.get("quantity")
            )

            new_notes = (
                request.POST.get("notes")
                or ""
            ).strip()

            if (
                current_order is None
                or item_id <= 0
            ):

                form_error = (
                    "No active order item "
                    "found to update."
                )

            elif new_quantity is None:

                form_error = (
                    "Quantity must be "
                    "at least 0.5."
                )

            else:

                order_item = (
                    current_order.items
                    .filter(id=item_id)
                    .first()
                )

                if order_item is None:

                    form_error = (
                        "Selected order item "
                        "was not found."
                    )

                else:

                    order_item.quantity = (
                        new_quantity
                    )

                    order_item.notes = (
                        new_notes
                    )

                    order_item.save(
                        update_fields=[
                            "quantity",
                            "notes",
                        ]
                    )

                    recalculate_order_totals(
                        current_order
                    )

                    return redirect(
                        f"{request.path}"
                        "?item_updated=1"
                    )

        # ========================================================
        # DELETE ORDER ITEM
        # ========================================================

        elif action == "delete_item":

            current_order = get_current_order()

            raw_item_id = request.POST.get(
                "order_item_id"
            )

            try:

                item_id = int(
                    raw_item_id
                )

            except (
                TypeError,
                ValueError,
            ):

                item_id = 0

            if (
                current_order is None
                or item_id <= 0
            ):

                form_error = (
                    "No active order item "
                    "found to delete."
                )

            else:

                order_item = (
                    current_order.items
                    .filter(id=item_id)
                    .select_related(
                        "product",
                        "product__section",
                        "order",
                        "order__table",
                        "order__waiter",
                    )
                    .first()
                )

                if order_item is None:

                    form_error = (
                        "Selected order item "
                        "was not found."
                    )

                else:

                    with transaction.atomic():

                        # -------------------------------------------------
                        # This handles:
                        #
                        # 1. Not printed → delete only
                        #
                        # 2. Already printed → create cancellation
                        #    PrintJob + delete item
                        # -------------------------------------------------

                        OrderItem.cancel_and_print(
                            order_item
                        )

                        # -------------------------------------------------
                        # If no items remain, delete order
                        # -------------------------------------------------

                        if not current_order.items.exists():

                            current_order.delete()

                        else:

                            # -------------------------------------------------
                            # Recalculate remaining order totals
                            # -------------------------------------------------

                            recalculate_order_totals(
                                current_order
                            )

                    return redirect(
                        f"{request.path}"
                        "?item_deleted=1"
                    )

        # ========================================================
        # DELETE ENTIRE ORDER
        # ========================================================

        elif action == "delete_order":

            current_order = get_current_order()

            if current_order is None:

                form_error = (
                    "No active order found "
                    "to delete."
                )

            else:

                current_order.delete()

                return redirect(
                    f"{request.path}"
                    "?order_deleted=1"
                )

        # ========================================================
        # CREATE / ADD ORDER ITEMS
        # ========================================================

        elif action in {
            "save_and_create_order",
            "create_order",
        }:

            product_ids = []

            # ----------------------------------------------------
            # READ SELECTED PRODUCTS
            # ----------------------------------------------------

            for category_block in products_by_category:

                for product in category_block[
                    "products"
                ]:

                    raw_qty = request.POST.get(
                        f"qty_{product.id}",
                        "0",
                    )

                    is_selected = (
                        request.POST.get(
                            f"send_{product.id}"
                        )
                        in {
                            "1",
                            "on",
                            "true",
                        }
                    )

                    quantity = Decimal("0.00")

                    try:

                        candidate = Decimal(
                            str(raw_qty)
                        )

                        if (
                            is_selected
                            and candidate
                            > Decimal("0.00")
                        ):

                            quantity = candidate

                    except Exception:

                        quantity = Decimal(
                            "0.00"
                        )

                    note_value = (
                        request.POST.get(
                            f"note_{product.id}"
                        )
                        or ""
                    ).strip()

                    selected_quantities[
                        product.id
                    ] = quantity

                    selected_notes[
                        product.id
                    ] = note_value

                    if quantity > 0:

                        product_ids.append(
                            product.id
                        )

            # ----------------------------------------------------
            # NO PRODUCTS
            # ----------------------------------------------------

            if not product_ids:

                form_error = (
                    "Please choose at least "
                    "one product before "
                    "saving the order."
                )

            else:

                # ------------------------------------------------
                # FIND WAITER
                # ------------------------------------------------

                waiter = None

                if (
                    getattr(
                        request,
                        "user",
                        None,
                    )
                    and request.user.is_authenticated
                ):

                    waiter = request.user

                if waiter is None:

                    waiter = (
                        User.objects
                        .filter(
                            is_active=True,
                            role=UserRole.WAITER,
                        )
                        .order_by("id")
                        .first()
                    )

                if waiter is None:

                    waiter = (
                        User.objects
                        .filter(
                            is_active=True
                        )
                        .order_by("id")
                        .first()
                    )

                # ------------------------------------------------
                # NO WAITER
                # ------------------------------------------------

                if waiter is None:

                    form_error = (
                        "No active waiter "
                        "user found. Please "
                        "create/activate a "
                        "waiter first."
                    )

                else:

                    # --------------------------------------------
                    # GET SELECTED PRODUCTS
                    # --------------------------------------------

                    product_map = {
                        product.id: product
                        for product in (
                            Product.objects
                            .filter(
                                id__in=product_ids,
                                is_active=True,
                            )
                        )
                    }

                    line_items = []

                    # --------------------------------------------
                    # BUILD LINE ITEMS
                    # --------------------------------------------

                    for product_id in product_ids:

                        product = product_map.get(
                            product_id
                        )

                        quantity = (
                            selected_quantities.get(
                                product_id,
                                Decimal("0.00"),
                            )
                        )

                        if (
                            product is None
                            or quantity <= 0
                        ):

                            continue

                        current_price = (
                            product.get_current_price()
                        )

                        item_note = (
                            selected_notes.get(
                                product_id,
                                "",
                            )
                        )

                        line_items.append(
                            (
                                product,
                                quantity,
                                current_price,
                                item_note,
                            )
                        )

                    # --------------------------------------------
                    # NO VALID ITEMS
                    # --------------------------------------------

                    if not line_items:

                        form_error = (
                            "Selected products "
                            "are not available "
                            "anymore. Please "
                            "choose again."
                        )

                    else:

                        created_order = None

                        # ----------------------------------------
                        # CREATE / UPDATE ORDER
                        # ----------------------------------------

                        with transaction.atomic():

                            current_order = (
                                get_current_order()
                            )

                            # ====================================
                            # CREATE NEW ORDER
                            # ====================================

                            if current_order is None:

                                order = (
                                    Order.objects.create(
                                        table=table,
                                        waiter=waiter,
                                        status=OrderStatus.OPEN,
                                        subtotal=Decimal(
                                            "0.00"
                                        ),
                                        tax=Decimal(
                                            "0.00"
                                        ),
                                        discount=Decimal(
                                            "0.00"
                                        ),
                                        total=Decimal(
                                            "0.00"
                                        ),
                                    )
                                )

                                # --------------------------------
                                # IMPORTANT:
                                #
                                # Every selected product gets a
                                # NEW OrderItem.
                                #
                                # has_print_job MUST remain FALSE
                                # until the user explicitly presses
                                # the Print button.
                                # --------------------------------

                                for (
                                    product,
                                    quantity,
                                    current_price,
                                    item_note,
                                ) in line_items:

                                    OrderItem.objects.create(
                                        order=order,
                                        product=product,
                                        quantity=quantity,
                                        unit_price=current_price,
                                        has_print_job=False,
                                        discount=Decimal(
                                            "0.00"
                                        ),
                                        notes=item_note.strip(),
                                    )

                                recalculate_order_totals(
                                    order
                                )

                                Order._sync_table_status(
                                    order.table_id
                                )

                                created_order = order

                            # ====================================
                            # ADD TO EXISTING ORDER
                            # ====================================

                            else:

                                # --------------------------------
                                # IMPORTANT:
                                #
                                # NEVER search for an existing
                                # OrderItem here.
                                #
                                # NEVER increase its quantity.
                                #
                                # ALWAYS create a completely
                                # separate OrderItem.
                                # --------------------------------

                                for (
                                    product,
                                    quantity,
                                    current_price,
                                    item_note,
                                ) in line_items:

                                    normalized_note = (
                                        item_note.strip()
                                    )

                                    OrderItem.objects.create(
                                        order=current_order,
                                        product=product,
                                        quantity=quantity,
                                        unit_price=current_price,
                                        discount=Decimal(
                                            "0.00"
                                        ),
                                        notes=normalized_note,
                                        has_print_job=False,
                                    )

                                recalculate_order_totals(
                                    current_order
                                )

                                Order._sync_table_status(
                                    current_order.table_id
                                )

                                created_order = current_order

                        # ====================================================
                        # IMPORTANT CHANGE
                        #
                        # DO NOT PRINT HERE.
                        #
                        # The old code had:
                        #
                        # OrderItem.print_pending_items(created_order)
                        #
                        # That was the reason newly-created items could
                        # immediately become has_print_job=True.
                        #
                        # Printing now happens ONLY from:
                        #
                        # action == "print_pending_items"
                        # OR
                        # action == "print_order_items"
                        # ====================================================

                        if action == "save_and_create_order":

                            return redirect(
                                "tables"
                            )

                        return redirect(
                            f"{request.path}"
                            "?created=1"
                        )

    # ============================================================
    # CURRENT ORDER
    # ============================================================

    order = get_current_order()

    current_order_items = []
    current_order_item_rows = []

    if order:

        current_order_items = list(
            order.items
            .select_related("product")
            .order_by("-created_at")
        )

        if not current_order_items:

            order.delete()
            order = None

        else:

            for item in current_order_items:

                line_total = (
                    item.unit_price
                    * Decimal(str(item.quantity))
                )

                quantity_display = (
                    format_quantity(
                        Decimal(
                            str(item.quantity)
                        )
                    )
                )

                unit_price_display = (
                    format_currency(
                        item.unit_price
                    )
                )

                line_total_display = (
                    format_currency(
                        line_total
                    )
                )

                current_order_item_rows.append(
                    {
                        "id": item.id,
                        "name": item.product.name,
                        "quantity": item.quantity,

                        # ------------------------------------------------
                        # This reflects the actual database value.
                        #
                        # False = not printed yet
                        # True  = already sent to printer
                        # ------------------------------------------------
                        "has_print_job": item.has_print_job,

                        "quantity_display": (
                            quantity_display
                        ),

                        "quantity_input": (
                            f"{Decimal(str(item.quantity)):.2f}"
                        ),

                        "notes": item.notes,

                        "unit_price_display": (
                            unit_price_display
                        ),

                        "line_total_display": (
                            line_total_display
                        ),

                        "summary_display": (
                            f"Qty: "
                            f"{quantity_display}"
                            f" · Price: "
                            f"{unit_price_display}"
                            f" · Total: "
                            f"{line_total_display}"
                        ),
                    }
                )

    # ============================================================
    # ORDER ITEM GROUPS
    # ============================================================

    current_order_item_rows_with_notes = [
        item
        for item in current_order_item_rows
        if item["notes"]
    ]

    current_order_item_rows_without_notes = [
        item
        for item in current_order_item_rows
        if not item["notes"]
    ]

    current_order_items_count = len(
        current_order_items
    )

    # ============================================================
    # ORDER SUMMARY
    # ============================================================

    waiter_name = ""
    order_total = None
    current_order_total_display = "N/A"

    if order:

        waiter_name = (
            order.waiter.full_name
            or order.waiter.username
        )

        order_total = order.total

        current_order_total_display = (
            format_currency(
                order.total
            )
        )

    order_total_display = (
        format_currency(order_total)
        if order_total is not None
        else "N/A"
    )

    # ============================================================
    # TABLE STATUS BACKGROUND
    # ============================================================

    status_background = {
        TableStatus.AVAILABLE: "#dcfce7",
        TableStatus.OCCUPIED: "#fee2e2",
        TableStatus.RESERVED: "#fef3c7",
        TableStatus.ON_PAYMENT: "#fde68a",
        TableStatus.CLOSED: "#e5e7eb",
    }

    # ============================================================
    # CONTEXT
    # ============================================================

    context = {
        "table": table,

        "section_blocks": section_blocks,

        "products_by_category": (
            products_by_category
        ),

        "products_flat": products_flat,

        "selected_quantities": (
            selected_quantities
        ),

        "form_error": form_error,

        "form_success": form_success,

        "delete_item_success": (
            delete_item_success
        ),

        "update_item_success": (
            update_item_success
        ),

        "delete_order_success": (
            delete_order_success
        ),

        "invoice_printed": invoice_printed,

        "order_items_printed": (
            order_items_printed
        ),

        "order_paid": order_paid,

        "table_changed": table_changed,

        "money_sources": money_sources,

        "current_order": order,

        "current_order_items": (
            current_order_items
        ),

        "current_order_item_rows": (
            current_order_item_rows
        ),

        "current_order_item_rows_with_notes": (
            current_order_item_rows_with_notes
        ),

        "current_order_item_rows_without_notes": (
            current_order_item_rows_without_notes
        ),

        "current_order_items_count": (
            current_order_items_count
        ),

        "current_order_total_display": (
            current_order_total_display
        ),

        "status_label": (
            table.get_status_display()
        ),

        "background_color": (
            status_background.get(
                table.status,
                "#ffffff",
            )
        ),

        "waiter_name": waiter_name,

        "order_total_display": (
            order_total_display
        ),

        "currency": settings.CURRENCY,

        "occupied_status": (
            TableStatus.OCCUPIED
        ),

        # --------------------------------------------------------
        # Change-table payload (sections → available tables)
        # --------------------------------------------------------
        "sections_payload": sections_payload,

        "admin_page": "tables",
    }

    return render(
        request,
        "ui/table_detail_admin.html",
        context,
    )