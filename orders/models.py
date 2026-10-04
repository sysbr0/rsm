from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models
from  common.models import TimeStampedModel
from config import settings
from menu.models import Product
from printers.models import * 
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
    ON_PAYMENT = "ON_PAYMENT", "On Payment"
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

    def set_order_as_paid(self, income_source_id: int, received_by_who) :
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
         
            order=self,
            received_by =received_by_who

        )



        self.save()

    def set_order_as_cancelled(self):
        self.status = OrderStatus.CANCELLED

        self.table.status = TableStatus.AVAILABLE
        self.table.save(update_fields=["status"])

        self.save()

    def set_order_as_printed(self):
        self.status = OrderStatus.SERVED

        self.table.status = TableStatus.ON_PAYMENT
        self.table.save(update_fields=["status"])
        from printers.services import print_customer_invoice

        self.save()
        return print_customer_invoice(self)

       
   

    

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

    def set_as_printed(self):
        """
        Mark this OrderItem as successfully printed.
        """

        self.has_print_job = True
        self.status = OrderItemStatus.PRINTED

        self.save(
            update_fields=[
                "has_print_job",
                "status",
            ]
        )

        print(
            f"[PRINT] OrderItem #{self.id} "
            f"marked as PRINTED."
        )

    @classmethod
    def print_pending_items(cls, order):
        """
        Create and process PrintJobs for all unprinted OrderItems.

        Rules:

        - Only has_print_job=False items are selected.
        - OrderItems are NEVER merged.
        - One PrintJob is created per section.
        - Every PrintJob receives its exact OrderItems through M2M.
        - The PrintJob is processed ONLY AFTER order_items.set().
        - OrderItems are marked printed ONLY after successful printing.
        - Failed printing leaves has_print_job=False.
        """

        from collections import defaultdict

        from django.utils import timezone

        from printers.models import (
            Printer,
            PrintJob,
            PrintJobStatus,
        )

        from printers.services import process_print_job

        # ============================================================
        # GET UNPRINTED ITEMS
        # ============================================================

        items = list(
            cls.objects
            .select_related(
                "product",
                "product__section",
                "order",
                "order__table",
                "order__waiter",
            )
            .filter(
                order=order,
                has_print_job=False,
            )
            .order_by("id")
        )

        if not items:

            print(
                f"[PRINT] No unprinted OrderItems "
                f"for Order #{order.id}."
            )

            return []

        # ============================================================
        # GROUP BY SECTION
        # ============================================================

        sections = defaultdict(list)

        for item in items:

            if not item.product:

                print(
                    f"[PRINT] OrderItem #{item.id} "
                    f"has no product. Skipping."
                )

                continue

            if not item.product.section_id:

                print(
                    f"[PRINT] OrderItem #{item.id} "
                    f"has no section. Skipping."
                )

                continue

            sections[
                item.product.section_id
            ].append(item)

        # ============================================================
        # DEBUG
        # ============================================================

        print("=" * 60)

        print(
            f"[PRINT] Printing pending items "
            f"for Order #{order.id}"
        )

        print("=" * 60)

        for item in items:

            print(
                f"[PRINT] OrderItem #{item.id} | "
                f"Product: {item.product.name} | "
                f"Section: {item.product.section_id} | "
                f"has_print_job={item.has_print_job}"
            )

        # ============================================================
        # JOBS
        # ============================================================

        jobs = []

        # ============================================================
        # PROCESS EACH SECTION
        # ============================================================

        for section_id, section_items in sections.items():

            print("-" * 60)

            print(
                f"[PRINT] Processing section: "
                f"{section_id}"
            )

            # ========================================================
            # FIND PRINTER
            # ========================================================

            printer = (
                Printer.objects
                .filter(
                    section_id=section_id,
                    is_active=True,
                )
                .select_related("section")
                .first()
            )

            print(
                f"[PRINT] Printer for section "
                f"{section_id}: {printer}"
            )

            # ========================================================
            # NO PRINTER
            # ========================================================

            if not printer:

                print(
                    f"[PRINT] No active printer for "
                    f"section {section_id}."
                )

                continue

            # ========================================================
            # BUILD TICKET
            # ========================================================

            width = 32

            lines = []

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

            # ========================================================
            # ORDER INFORMATION
            # ========================================================

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
                f"WAITER: {waiter_name}"
            )

            lines.append(
                f"TIME: "
                f"{current_time.strftime('%d/%m/%Y %H:%M')}"
            )

            lines.append(
                f"ORDER #{order.id}"
            )

            lines.append("-" * width)

            # ========================================================
            # ORDER ITEMS
            # ========================================================

            for item in section_items:

                product = item.product

                quantity = item.quantity

                notes = (
                    item.notes or ""
                ).strip()

                quantity_text = (
                    f"{quantity:.2f}"
                )

                product_name = str(
                    product.name
                )

                product_line = (
                    f"{quantity_text} x "
                    f"{product_name}"
                )

                # ====================================================
                # PRODUCT NAME
                # ====================================================

                if len(product_line) <= width:

                    lines.append(
                        product_line
                    )

                else:

                    prefix = (
                        f"{quantity_text} x "
                    )

                    available_width = (
                        width - len(prefix)
                    )

                    first_part = (
                        product_name[
                            :available_width
                        ]
                    )

                    remaining = (
                        product_name[
                            available_width:
                        ]
                    )

                    lines.append(
                        prefix + first_part
                    )

                    while remaining:

                        lines.append(
                            " " * len(prefix)
                            + remaining[
                                :available_width
                            ]
                        )

                        remaining = (
                            remaining[
                                available_width:
                            ]
                        )

                # ====================================================
                # NOTES
                # ====================================================

                if notes:

                    note_prefix = "   NOTE: "

                    available_width = (
                        width - len(note_prefix)
                    )

                    note_parts = [
                        notes[i:i + available_width]
                        for i in range(
                            0,
                            len(notes),
                            available_width,
                        )
                    ]

                    for index, note_part in enumerate(
                        note_parts
                    ):

                        if index == 0:

                            lines.append(
                                note_prefix
                                + note_part
                            )

                        else:

                            lines.append(
                                " " * len(note_prefix)
                                + note_part
                            )

                lines.append("")

            # ========================================================
            # FOOTER
            # ========================================================

            lines.append("-" * width)

            lines.append(
                f"ORDER #{order.id}"
            )

            lines.append("=" * width)

            content = (
                "\n".join(lines)
                + "\n"
            )

            # ========================================================
            # CREATE PRINT JOB
            # ========================================================

            print(
                f"[PRINT] Creating PrintJob "
                f"for section {section_id}..."
            )

            job = PrintJob.objects.create(
                order_id=order.id,
                section_id=section_id,
                printer=printer,
                status=PrintJobStatus.PENDING,
                content=content,
            )

            print(
                f"[PRINT] Created PrintJob #{job.id}"
            )

            # ========================================================
            # ATTACH ITEMS FIRST
            #
            # THIS MUST HAPPEN BEFORE process_print_job()
            # ========================================================

            job.order_items.set(
                section_items
            )

            # Force M2M save to database and verify it.
            attached_ids = list(
                job.order_items.values_list(
                    "id",
                    flat=True,
                )
            )

            print(
                f"[PRINT] Attached "
                f"{len(attached_ids)} OrderItem(s) "
                f"to PrintJob #{job.id}"
            )

            print(
                f"[PRINT] Attached OrderItem IDs: "
                f"{attached_ids}"
            )

            # ========================================================
            # SAFETY CHECK
            # ========================================================

            if not attached_ids:

                print(
                    f"[PRINT ERROR] PrintJob #{job.id} "
                    f"has no OrderItems after attachment."
                )

                job.status = PrintJobStatus.FAILED

                job.error_message = (
                    "No OrderItems attached to PrintJob."
                )

                job.save(
                    update_fields=[
                        "status",
                        "error_message",
                        "updated_at",
                    ]
                )

                jobs.append(job)

                continue

            # ========================================================
            # PROCESS PRINT JOB
            #
            # THIS IS THE ONLY PLACE WE START PRINTING.
            # ========================================================

            print(
                f"[PRINT] Sending PrintJob #{job.id} "
                f"to printer {printer.name}..."
            )

            job = process_print_job(
                job
            )

            # ========================================================
            # REFRESH
            # ========================================================

            job.refresh_from_db()

            print(
                f"[PRINT] PrintJob #{job.id} "
                f"status: {job.status}"
            )

            # ========================================================
            # SUCCESS
            # ========================================================

            if job.status == PrintJobStatus.PRINTED:

                print(
                    f"[PRINT] PrintJob #{job.id} "
                    f"printed successfully."
                )

                # Verify exact OrderItems
                printed_items = list(
                    job.order_items.all()
                )

                for item in printed_items:

                    item.refresh_from_db()

                    print(
                        f"[PRINT] VERIFY "
                        f"OrderItem #{item.id}: "
                        f"has_print_job="
                        f"{item.has_print_job}, "
                        f"status={item.status}"
                    )

            # ========================================================
            # FAILURE
            # ========================================================

            elif job.status == PrintJobStatus.FAILED:

                print(
                    f"[PRINT ERROR] PrintJob #{job.id} "
                    f"failed."
                )

                print(
                    f"[PRINT ERROR] "
                    f"{job.error_message}"
                )

            # ========================================================
            # ADD JOB
            # ========================================================

            jobs.append(job)

        # ============================================================
        # FINISHED
        # ============================================================

        print("=" * 60)

        print(
            f"[PRINT] Finished processing "
            f"{len(jobs)} PrintJob(s)"
        )

        print("=" * 60)

        return jobs