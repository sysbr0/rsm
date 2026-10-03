from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from  common.models import TimeStampedModel
from config import settings
from menu.models import Product
from printers.models import * 
from printers.models import PrintJobStatus
from tables.models import RestaurantTable, TableStatus
from users.models import User

from collections import defaultdict
from Financial.models import  *
from django.utils import timezone

class OrderStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    CONFIRMED = "CONFIRMED", "Confirmed"
    PREPARING = "PREPARING", "Preparing"
    READY = "READY", "Ready"
    SERVED = "SERVED", "Served"
    PAID = "PAID", "Paid"
    CANCELLED = "CANCELLED", "Cancelled"


class Order(TimeStampedModel):
    table = models.ForeignKey(
        RestaurantTable,
        on_delete=models.PROTECT,
        related_name="orders",
    )

    waiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders"
    )

    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.OPEN,
    )

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    @classmethod
    def _sync_table_status(cls, table_id: int | None) -> None:
        if not table_id:
            return

        active_order_exists = cls.objects.filter(
            table_id=table_id,
            status__in=[
                OrderStatus.OPEN,
                OrderStatus.CONFIRMED,
                OrderStatus.PREPARING,
                OrderStatus.READY,
                OrderStatus.SERVED,
            ],
        ).exists()

        if not active_order_exists:
            return

    def save(self, *args, **kwargs):
        previous_table_id = None

        if self.pk:
            previous_table_id = (
                Order.objects
                .filter(pk=self.pk)
                .values_list("table_id", flat=True)
                .first()
            )

        super().save(*args, **kwargs)

        self._sync_table_status(self.table_id)

        if previous_table_id and previous_table_id != self.table_id:
            self._sync_table_status(previous_table_id)

    def delete(self, *args, **kwargs):
        table_id = self.table_id

        super().delete(*args, **kwargs)

        self._sync_table_status(table_id)

    def set_order_as_paid(self, income_source_id: int):
        self.status = OrderStatus.PAID

        self.table.status = TableStatus.AVAILABLE
        self.table.save(update_fields=["status"])



      

        ReceivePayment.objects.create(
            source_id=income_source_id,
            payer_name=(
                self.waiter.full_name
                if self.waiter
                else "Unknown Waiter"
            ),
            amount=self.total,
            payment_method="CASH",
            order=self,
        )



        self.save()

    def set_order_as_cancelled(self):
        self.status = OrderStatus.CANCELLED

        self.table.status = TableStatus.AVAILABLE
        self.table.save(update_fields=["status"])

        self.save()

    def set_order_as_printed(self):
        self.status = OrderStatus.SERVED

        self.table.status = TableStatus.ON_PayMENT
        self.table.save(update_fields=["status"])

        self.save()

    def apply_discount(self, discount_amount: Decimal):
        self.discount = discount_amount

        self.total = max(
            Decimal("0.00"),
            self.subtotal + self.tax - self.discount,
        )

        self.save()

    def __str__(self):
        return f"Order #{self.id}"

    def print_customer_invoice(self, width=42):
  
    

        # ==========================================================
        # HELPERS
        # ==========================================================

        lines = []

        def separator(char="-"):
            return char * width

        def centered(text):
            return str(text).center(width)

        def money(value):
            value = Decimal(value or 0)
            return f"{value:,.2f}"

        def add_line(text=""):
            lines.append(str(text))

        # ==========================================================
        # DATE / TIME
        # ==========================================================

        order_time = getattr(self, "created_at", None)

        if order_time:
            order_time = timezone.localtime(order_time)
        else:
            order_time = timezone.localtime()

        # ==========================================================
        # HEADER
        # ==========================================================

        add_line(centered("SYSBR RESTAURANT"))
        add_line(centered("CUSTOMER INVOICE"))
        add_line(separator("="))

        # ==========================================================
        # ORDER INFORMATION
        # ==========================================================

        add_line(f"Order #: {self.pk}")

        add_line(
            f"Date: {order_time.strftime('%d/%m/%Y')}"
        )

        add_line(
            f"Time: {order_time.strftime('%H:%M')}"
        )

        # ==========================================================
        # TABLE
        # ==========================================================

        if self.table:

            table_number = getattr(
                self.table,
                "table_number",
                None,
            )

            table_name = getattr(
                self.table,
                "name",
                None,
            )

            if table_name:
                add_line(
                    f"Table: {table_number} - {table_name}"
                )
            else:
                add_line(
                    f"Table: {table_number}"
                )

        # ==========================================================
        # WAITER
        # ==========================================================

        if self.waiter:

            waiter_name = ""

            if hasattr(self.waiter, "get_full_name"):
                waiter_name = self.waiter.get_full_name()

            if not waiter_name:
                waiter_name = getattr(
                    self.waiter,
                    "username",
                    "",
                )

            if not waiter_name:
                waiter_name = getattr(
                    self.waiter,
                    "email",
                    "",
                )

            if waiter_name:
                add_line(
                    f"Waiter: {waiter_name}"
                )

        add_line(separator("-"))

        # ==========================================================
        # MERGE ORDER ITEMS
        # ==========================================================

        merged_items = OrderedDict()

        for item in self.items.select_related("product").all():

            product = item.product

            if product:
                product_name = (
                    getattr(product, "name", None)
                    or str(product)
                )

                merge_key = product.pk

            else:
                product_name = "Unknown Item"
                merge_key = f"unknown-{item.pk}"

            quantity = Decimal(
                getattr(item, "quantity", 0) or 0
            )

            unit_price = Decimal(
                getattr(item, "unit_price", 0) or 0
            )

            # ------------------------------------------------------
            # First occurrence
            # ------------------------------------------------------

            if merge_key not in merged_items:

                merged_items[merge_key] = {
                    "name": product_name,
                    "quantity": Decimal("0"),
                    "unit_price": unit_price,
                }

            # ------------------------------------------------------
            # Merge quantity
            # ------------------------------------------------------

            merged_items[merge_key]["quantity"] += quantity

        # ==========================================================
        # ITEM HEADER
        # ==========================================================

        add_line(
            f"{'Item':<18}"
            f"{'Qty':>5}"
            f"{'Price':>9}"
            f"{'Total':>10}"
        )

        add_line(separator("-"))

        # ==========================================================
        # ITEMS
        # ==========================================================

        calculated_subtotal = Decimal("0")

        for item in merged_items.values():

            name = item["name"]
            quantity = item["quantity"]
            unit_price = item["unit_price"]

            # ------------------------------------------------------
            # Line total
            # ------------------------------------------------------

            line_total = quantity * unit_price

            calculated_subtotal += line_total

            # ------------------------------------------------------
            # Limit product name
            # ------------------------------------------------------

            name = name[:18]

            # ------------------------------------------------------
            # Quantity formatting
            # ------------------------------------------------------

            if quantity == quantity.to_integral_value():
                quantity_text = str(int(quantity))
            else:
                quantity_text = f"{quantity:g}"

            # ------------------------------------------------------
            # Print item
            # ------------------------------------------------------

            add_line(
                f"{name:<18}"
                f"{quantity_text:>5}"
                f"{money(unit_price):>9}"
                f"{money(line_total):>10}"
            )

        # ==========================================================
        # TOTALS
        # ==========================================================

        add_line(separator("-"))

        # ----------------------------------------------------------
        # SUBTOTAL
        # ----------------------------------------------------------

        if self.subtotal is not None:
            subtotal = Decimal(self.subtotal)
        else:
            subtotal = calculated_subtotal

        add_line(
            f"{'Subtotal:':<30}"
            f"{money(subtotal):>12}"
        )

        # ==========================================================
        # DISCOUNT
        # ==========================================================

        discount = Decimal(
            getattr(self, "discount", 0) or 0
        )

        if discount > 0:

            add_line(
                f"{'Discount:':<30}"
                f"-{money(discount):>11}"
            )

        # ==========================================================
        # TAX
        # ==========================================================

        tax = Decimal(
            getattr(self, "tax", 0) or 0
        )

        if tax > 0:

            add_line(
                f"{'Tax:':<30}"
                f"{money(tax):>12}"
            )

        # ==========================================================
        # GRAND TOTAL
        # ==========================================================

        if self.total is not None:

            total = Decimal(self.total)

        else:

            total = (
                subtotal
                - discount
                + tax
            )

        add_line(separator("="))

        add_line(
            f"{'TOTAL:':<30}"
            f"{money(total):>12}"
        )

        add_line(separator("="))

        # ==========================================================
        # FOOTER
        # ==========================================================

        add_line("")
        add_line(centered("Thank you!"))
        add_line(centered("Please visit us again."))
        add_line("")

        # ==========================================================
        # COMPLETE INVOICE CONTENT
        # ==========================================================

        invoice = "\n".join(lines)

        # ==========================================================
        # FIND CASHIER PRINTER
        # ==========================================================

        cashier_printer = (
            Printer.objects
            .select_related("section")
            .filter(
                is_active=True,
                is_cashear_printer=True,
            )
            .first()
        )

        if not cashier_printer:

            raise ValueError(
                "No active cashier printer is configured."
            )

        # ==========================================================
        # CREATE PRINT JOB
        # ==========================================================

        print_job = PrintJob.objects.create(
            order_id=self.pk,
            section=cashier_printer.section,
            printer=cashier_printer,
            content=invoice,
        )

        # ==========================================================
        # RETURN
        # ==========================================================

        return print_job


class OrderItemStatus(models.TextChoices):
    NEW = "NEW", "New"
    PRINTED = "PRINTED", "Printed"
    PREPARING = "PREPARING", "Preparing"
    READY = "READY", "Ready"
    SERVED = "SERVED", "Served"
    CANCELLED = "CANCELLED", "Cancelled"


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
    )

    quantity = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[
            MinValueValidator(Decimal("0.50"))
        ],
    )

    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    notes = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    status = models.CharField(
        max_length=20,
        choices=OrderItemStatus.choices,
        default=OrderItemStatus.NEW,
    )

    has_print_job = models.BooleanField(
        default=False,
    )

    def save(self, *args, **kwargs):

        if self._state.adding:
            self.unit_price = self.product.get_current_price()

        if self.product.name.lower() == "reserve":
            self.order.table.set_as_reserved()
        else:
            self.order.table.set_as_occupied()

        super().save(*args, **kwargs)

    def __str__(self):
        return super().__str__()



    @classmethod
    def print_pending_items(cls, order):
        """
        Create PrintJobs for all unprinted OrderItems belonging to this order.

        Print format is designed for a 32-column thermal printer.
        """

        items = list(
            cls.objects
            .select_related(
                "product",
                "product__section",
            )
            .filter(
                order=order,
                has_print_job=False,
            )
            .order_by("id")
        )

        if not items:
            return []

        # ---------------------------------------------------------
        # Group items by section
        # ---------------------------------------------------------

        sections = defaultdict(list)

        for item in items:
            sections[item.product.section_id].append(item)

        jobs = []

        # ---------------------------------------------------------
        # Create one print job per section/printer
        # ---------------------------------------------------------

        for section_id, section_items in sections.items():

            printer = (
                Printer.objects
                .filter(
                    section_id=section_id,
                    is_active=True,
                )
                .select_related("section")
                .first()
            )

            # No printer configured for this section
            if not printer:
                continue

            # -----------------------------------------------------
            # Merge identical products without notes
            # Keep products with notes separate
            # -----------------------------------------------------

            merged = {}
            separate = []

            for item in section_items:

                notes = (item.notes or "").strip()

                # Items with notes must remain separate
                if notes:
                    separate.append(
                        {
                            "product": item.product,
                            "quantity": item.quantity,
                            "notes": notes,
                            "items": [item],
                        }
                    )
                    continue

                product_id = item.product_id

                if product_id not in merged:

                    merged[product_id] = {
                        "product": item.product,
                        "quantity": item.quantity,
                        "notes": "",
                        "items": [item],
                    }

                else:

                    merged[product_id]["quantity"] += item.quantity
                    merged[product_id]["items"].append(item)

            printable_items = (
                list(merged.values())
                + separate
            )

            # -----------------------------------------------------
            # THERMAL PRINT SETTINGS
            # -----------------------------------------------------

            width = 32

            lines = []

            # =====================================================
            # HEADER
            # =====================================================

            lines.append("=" * width)

            section_name = (
                printer.section.name
                if printer.section
                else "KITCHEN"
            )

            lines.append(
                section_name.upper().center(width)
            )

            lines.append("=" * width)

            # =====================================================
            # ORDER INFORMATION
            # =====================================================

            table_number = (
                order.table.table_number
                if order.table
                else "-"
            )

            waiter_name = (
                order.waiter.full_name
                if order.waiter
                else "-"
            )

            current_time = timezone.localtime()

            lines.append(
                f"TABLE: {table_number}"
            )

            lines.append(
                f"WAITER: #{waiter_name}"
            )

            lines.append(
                f"TIME: {current_time.strftime('%d/%m/%Y %H:%M')}"
            )

            # =====================================================
            # SEPARATOR
            # =====================================================

            lines.append("-" * width)

            # =====================================================
            # PRODUCTS
            # =====================================================

            for row in printable_items:

                quantity = row["quantity"]
                product = row["product"]
                notes = row["notes"]

                # -------------------------------------------------
                # Quantity
                # Example:
                #
                # 5.00 x adana lahmacun
                # -------------------------------------------------

                try:
                    quantity_text = f"{float(quantity):.2f}"
                except (TypeError, ValueError):
                    quantity_text = str(quantity)

                product_name = str(product.name)

                product_line = (
                    f"{quantity_text} x {product_name}"
                )

                # -------------------------------------------------
                # Handle long product names
                # -------------------------------------------------

                if len(product_line) <= width:

                    lines.append(product_line)

                else:

                    # Keep quantity on first line
                    prefix = f"{quantity_text} x "

                    available_width = width - len(prefix)

                    first_part = product_name[:available_width]

                    remaining = product_name[available_width:]

                    lines.append(
                        prefix + first_part
                    )

                    while remaining:

                        lines.append(
                            " " * len(prefix)
                            + remaining[:available_width]
                        )

                        remaining = remaining[available_width:]

                # -------------------------------------------------
                # NOTE
                #
                # Example:
                #
                #    NOTE: revan hizli
                # -------------------------------------------------

                if notes:

                    note_prefix = "   NOTE: "

                    available_width = width - len(note_prefix)

                    note_parts = [
                        notes[i:i + available_width]
                        for i in range(
                            0,
                            len(notes),
                            available_width,
                        )
                    ]

                    for index, note_part in enumerate(note_parts):

                        if index == 0:

                            lines.append(
                                note_prefix + note_part
                            )

                        else:

                            lines.append(
                                " " * len(note_prefix)
                                + note_part
                            )

                # -------------------------------------------------
                # Space between products
                # -------------------------------------------------

                lines.append("")

            # =====================================================
            # FOOTER
            # =====================================================

            lines.append("-" * width)

            lines.append(
                f"ORDER #{order.id}"
            )

            lines.append("=" * width)

            # Final newline
            content = "\n".join(lines) + "\n"

            # =====================================================
            # CREATE PRINT JOB
            # =====================================================

            job = PrintJob.objects.create(
                order_id=order.id,
                section_id=section_id,
                printer=printer,
                status=PrintJobStatus.PENDING,
                content=content,
            )

            jobs.append(job)

        return jobs


    def __str__(self):
        return str(self.product)