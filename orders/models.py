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
from django.db import transaction
from django.core.exceptions import ValidationError

from Financial.services import receive_money
from django.core.exceptions import PermissionDenied
from django.db.models import Q


from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import transaction



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

    
ACTIVE_ORDER_STATUSES = (
    OrderStatus.OPEN,
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.SERVED,
)

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
        """
        Synchronize the status of a restaurant table based on whether it
        currently has any active (in-progress) orders.

        A table is marked as OCCUPIED when at least one order referencing it
        is in an active state (OPEN, CONFIRMED, PREPARING, READY, or SERVED).
        Otherwise, the table is marked as AVAILABLE.

        This method is idempotent and safe to call multiple times — it will
        only issue an UPDATE when the computed status differs from the stored
        status.

        Args:
            table_id: Primary key of the RestaurantTable to synchronize.
                If ``None`` or falsy, the method returns without doing anything.

        Returns:
            None
        """
        if not table_id:
            return

        # Determine whether an active order currently references this table.
        has_active_order = cls.objects.filter(
            table_id=table_id,
            status__in=ACTIVE_ORDER_STATUSES,
        ).exists()

        desired_status = (
            TableStatus.OCCUPIED if has_active_order else TableStatus.AVAILABLE
        )

        # Only write to the DB if the status actually needs to change.
        (
            RestaurantTable.objects
            .filter(pk=table_id)
            .exclude(status=desired_status)
            .update(status=desired_status)
        )

    # ------------------------------------------------------------------
    # Overridden ORM methods
    # ------------------------------------------------------------------


    # Overridden ORM methods
    # ------------------------------------------------------------------

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


    # ------------------------------------------------------------------
    # Change table
    # ------------------------------------------------------------------

    @transaction.atomic
    def change_table(self, new_table_id):
        """
        Change the table assigned to this order.

        Handles:
        - Guard against changing table on a paid/cancelled order
        - Validation that the new table exists and is available
        - Syncing status of both old and new tables
        """
        # ---- Guard: cannot move a closed/paid order ----
        if self.status in [OrderStatus.PAID, OrderStatus.CANCELLED]:
            raise ValidationError(
                "Cannot change the table of a paid or cancelled order."
            )

        # ---- Guard: same table, nothing to do ----
        if self.table_id == new_table_id:
            return self

        # ---- Validate new table exists (lock row for safety) ----
        try:
            new_table = (
                RestaurantTable.objects
                .select_for_update()
                .get(pk=new_table_id)
            )
        except RestaurantTable.DoesNotExist:
            raise ValidationError("Target table does not exist.")

        # ---- Prevent moving to a table that already has an active order ----
        occupied = (
            Order.objects
            .filter(
                table=new_table,
                status__in=ACTIVE_ORDER_STATUSES,
            )
            .exclude(pk=self.pk)
            .exists()
        )

        if occupied:
            raise ValidationError(
                f"Table {new_table} is already occupied by another active order."
            )

        old_table_id = self.table_id

        # ---- Swap the table (save() will sync both old and new tables) ----
        self.table = new_table
        self.save(update_fields=["table", "updated_at"])

        # ---- Explicit sync as a safety net (redundant with save(), harmless) ----
        self._sync_table_status(new_table_id)
        if old_table_id:
            self._sync_table_status(old_table_id)

        return self

    # ------------------------------------------------------------------
    # Cancel / print
    # ------------------------------------------------------------------


    def delete(self, *args, **kwargs):
        table_id = self.table_id

        super().delete(*args, **kwargs)

        self._sync_table_status(table_id)


    @transaction.atomic
    def set_order_as_paid(self, income_source_id, received_by_who):
        """
        Mark this order as paid, free the table, and record the receipt
        in the financial ledger.

        Atomic — either everything succeeds or nothing does.
        """
        # ---- Guard: don't double-charge ----
        if self.status == OrderStatus.PAID:
            raise ValidationError("This order has already been paid.")

        # ---- Guard: order must have a total ----
        if not self.total or self.total <= 0:
            raise ValidationError("Order total must be greater than zero.")

        # ---- Guard: source must exist ----
        from Financial.models import MoneySource
        try:
            source = MoneySource.objects.get(pk=income_source_id, is_active=True)
        except MoneySource.DoesNotExist:
            raise ValidationError("Invalid or inactive money source.")

        # ---- Determine payer name safely ----
        payer_name = "Unknown Payer"
        if self.waiter:
            # Adjust to whatever your User model exposes.
            # `get_full_name()` returns "" if both names are empty.
            payer_name = (
                self.waiter.get_full_name().strip()
                or self.waiter.username
            )

        # ---- Record the financial transaction (updates balance + ledger) ----
        receive_money(
            source=source,
            amount=self.total,
            received_by=received_by_who,
            order=self,
            payer_name=payer_name,
            reference=f"Order #{self.pk}",
            notes=f"Payment for order #{self.pk}",
        )

        # ---- Update order status ----
        self.status = OrderStatus.PAID
        self.save(update_fields=["status", "updated_at"])

        # ---- Free the table ----
        if self.table:
            self.table.status = TableStatus.AVAILABLE
            self.table.save(update_fields=["status"])

    @transaction.atomic
    def change_table(self, new_table_id):
        """
        Change the table assigned to this order.

        Handles:
        - Guard against changing table on a paid/cancelled order
        - Validation that the new table exists and is available
        - Syncing status of both old and new tables
        """
        # ---- Guard: cannot move a closed/paid order ----
        if self.status in [OrderStatus.PAID, OrderStatus.CANCELLED]:
            raise ValidationError(
                "Cannot change the table of a paid or cancelled order."
            )

        # ---- Guard: same table, nothing to do ----
        if self.table_id == new_table_id:
            return self

        # ---- Validate new table exists (lock row for safety) ----
        try:
            new_table = (
                RestaurantTable.objects
                .select_for_update()
                .get(pk=new_table_id)
            )
        except RestaurantTable.DoesNotExist:
            raise ValidationError("Target table does not exist.")

        # ---- Prevent moving to a table that already has an active order ----
        occupied = (
            Order.objects
            .filter(
                table=new_table,
                status__in=[
                    OrderStatus.OPEN,
                    OrderStatus.CONFIRMED,
                    OrderStatus.PREPARING,
                    OrderStatus.READY,
                    OrderStatus.SERVED,
                ],
            )
            .exclude(pk=self.pk)
            .exists()
        )

        if occupied:
            raise ValidationError(
                f"Table {new_table} is already occupied by another active order."
            )

        old_table_id = self.table_id

        # ---- Swap the table (save() will sync both old and new tables) ----
        self.table = new_table
        self.save(update_fields=["table", "updated_at"])

        # ---- Explicit sync as a safety net (redundant with save(), harmless) ----
        self._sync_table_status(new_table_id)
        if old_table_id:
            self._sync_table_status(old_table_id)

        return self





    def set_order_as_cancelled(self):
        self.status = OrderStatus.CANCELLED

        self.table.status = TableStatus.AVAILABLE
        self.table.save(update_fields=["status"])

        self.save()

    def set_order_as_printed(self):
        self.status = OrderStatus.SERVED

     
        from printers.services import print_customer_invoice

        self.save()

        print("started printing")
        if self.table.table_number:
                        
            RestaurantTable.objects.select_for_update().get(
                    pk=self.table.table_number).set_as_on_payment()
       
        return print_customer_invoice(self)

       
   

    


    @transaction.atomic
    def apply_discount(self, discount_amount: Decimal):
        """
        Apply a discount to this order and recalculate the total.

        The discount cannot be negative, and cannot exceed
        subtotal + tax (the total would otherwise go negative).
        """
        try:
            discount_amount = Decimal(str(discount_amount))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Invalid discount amount.")

        discount_amount = discount_amount.quantize(Decimal("0.01"))

        if discount_amount < Decimal("0.00"):
            raise ValidationError("Discount cannot be negative.")

        max_discount = (self.subtotal + self.tax).quantize(Decimal("0.01"))

        if discount_amount > max_discount:
            raise ValidationError(
                f"Discount cannot exceed the order subtotal + tax "
                f"({max_discount})."
            )

        self.discount = discount_amount
        self.total = max(
            Decimal("0.00"),
            self.subtotal + self.tax - self.discount,
        )

        self.save(update_fields=["discount", "total", "updated_at"])
        return self


    @transaction.atomic
    def clear_discount(self):
        self.discount = Decimal("0.00")
        self.total = self.subtotal + self.tax
        self.save(update_fields=["discount", "total", "updated_at"])
        return self




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
    def print_pending_items(cls, order , user):
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
                f"WAITER: {user.full_name }"
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

    
    @classmethod
    def cancel_and_print(cls, order_item):


        from printers.models import (
            PrintJob,
            PrintJobStatus,
            Printer,
        )
        from printers.services import process_print_job

        if not order_item.has_print_job:
            order_item.delete()
            return None

        order = order_item.order
        product = order_item.product
        section = product.section

        if section is None:
            order_item.delete()
            return None

        printer = (
            Printer.objects
            .filter(
                section=section,
                is_active=True,
            )
            .first()
        )

        if printer is None:
            order_item.delete()
            return None

        content_lines = [
            "================================",
            "          CANCELLATION",
            "================================",
            f"TABLE: {order.table}",
            f"WAITER: {order.waiter.full_name if order.waiter else '-'}",
            "",
            f"X {order_item.quantity:g}  {product.name}",
        ]

        if order_item.notes:
            content_lines.append(f"NOTE: {order_item.notes}")

        content_lines.extend([
            "",
            "        !!! CANCELLED !!!",
            "================================",
        ])

        content = "\n".join(content_lines)

        job = PrintJob.objects.create(
            order=order,
            section=section,
            printer=printer,
            status=PrintJobStatus.PENDING,
            content=content,
            cancelled_product_name=product.name,
            cancelled_quantity=order_item.quantity,
            cancelled_notes=order_item.notes,
        )

        # Delete original item after capturing details
        order_item.delete()

        # Send cancellation job to physical printer
        process_print_job(job)

        return job


from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

# Keep your existing TimeStampedModel import.
# from your_app.models import TimeStampedModel


class TransferStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    DENIED = "DENIED", "Denied"


class ChangeOrderWaiter(TimeStampedModel):
    order = models.ForeignKey(
        "Order",
        on_delete=models.CASCADE,
        related_name="waiter_changes",
    )

    current_waiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_waiter_changes",
    )

    seted_waiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="seted_waiter_changes",
    )

    # Kept for compatibility with your existing API.
    # True means approved; False means pending or denied.
    is_approved = models.BooleanField(default=False)

    status = models.CharField(
        max_length=10,
        choices=TransferStatus.choices,
        default=TransferStatus.PENDING,
        db_index=True,
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_waiter_changes",
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    denial_reason = models.TextField(
        blank=True,
        default="",
    )

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(
                fields=["order", "status"],
                name="waiter_change_order_status_idx",
            ),
        ]

    def __str__(self):
        return (
            f"Transfer for Order {self.order_id}: "
            f"{self.current_waiter_id} -> {self.seted_waiter_id} "
            f"({self.status})"
        )

    @staticmethod
    def _is_manager(user):
        if not user or not user.is_authenticated:
            return False

        return (
            user.is_staff
            or user.is_superuser
            or getattr(user, "role", "") == "MANAGER"
        )

    @staticmethod
    def _is_active_waiter(user):
        if user is None or not user.is_active:
            return False

        return getattr(user, "role", "") == "WAITER"

    @classmethod
    def create_transfer_request(
        cls,
        order,
        created_by_user,
        seted_waiter,
    ):
        """
        Create a waiter transfer request.

        Manager:
            Approves the transfer immediately.

        Waiter:
            Creates a pending request requiring approval
            from a manager or the receiving waiter.
        """

        if not created_by_user or not created_by_user.is_authenticated:
            raise PermissionDenied("Authentication is required.")

        with transaction.atomic():
            # Lock the order to prevent concurrent transfer requests
            # from processing against the same order simultaneously.
            order = (
                order.__class__.objects
                .select_for_update()
                .get(pk=order.pk)
            )

            order_status = getattr(order.status, "value", order.status)

            if order_status in ("PAID", "CANCELLED"):
                raise ValidationError(
                    "Cannot transfer a paid or cancelled order."
                )

            if order_status not in (
                "OPEN",
                "CONFIRMED",
                "PREPARING",
                "READY",
                "SERVED",
            ):
                raise ValidationError(
                    "The order is not active."
                )

            if not cls._is_active_waiter(seted_waiter):
                raise ValidationError(
                    "The selected user must be an active waiter."
                )

            if order.waiter_id == seted_waiter.pk:
                raise ValidationError(
                    "The new waiter is already assigned to this order."
                )

            is_manager = cls._is_manager(created_by_user)

            # Only a manager or the current waiter can initiate a transfer.
            if not is_manager and order.waiter_id != created_by_user.pk:
                raise PermissionDenied(
                    "Only the current waiter or a manager can request "
                    "a waiter transfer."
                )

            # Keep only one pending transfer per order.
            cls.objects.filter(
                order=order,
                status=TransferStatus.PENDING,
            ).delete()

            transfer = cls.objects.create(
                order=order,
                current_waiter=order.waiter,
                seted_waiter=seted_waiter,
                is_approved=False,
                status=TransferStatus.PENDING,
            )

            if is_manager:
                transfer._approve_locked(
                    actioning_user=created_by_user,
                    order=order,
                )

            return transfer

    def _approve_locked(self, actioning_user, order):
        """
        Internal helper. Call inside transaction.atomic()
        with the order row locked.
        """

        if self.status != TransferStatus.PENDING:
            raise ValidationError(
                "This transfer request has already been processed."
            )

        if self.seted_waiter_id is None:
            raise ValidationError(
                "The receiving waiter no longer exists."
            )

        if not self._is_active_waiter(self.seted_waiter):
            raise ValidationError(
                "The receiving waiter is no longer active."
            )

        order_status = getattr(order.status, "value", order.status)

        if order_status not in (
            "OPEN",
            "CONFIRMED",
            "PREPARING",
            "READY",
            "SERVED",
        ):
            raise ValidationError(
                "The order is no longer active."
            )

        # Ensure the order has not changed waiters since the request.
        if order.waiter_id != self.current_waiter_id:
            raise ValidationError(
                "The order's assigned waiter has changed. "
                "Create a new transfer request."
            )

        order.waiter = self.seted_waiter
        order.save(update_fields=["waiter"])

        self.is_approved = True
        self.status = TransferStatus.APPROVED
        self.approved_by = actioning_user
        self.resolved_at = timezone.now()
        self.denial_reason = ""

        self.save(
            update_fields=[
                "is_approved",
                "status",
                "approved_by",
                "resolved_at",
                "denial_reason",
            ]
        )

    def approve_or_deny_transfer(
        self,
        actioning_user,
        approve=True,
        denial_reason="",
    ):
        """
        Approve or deny a pending transfer.

        Authorized users:
            - Managers
            - The receiving waiter

        Denied requests are retained for auditing.
        """

        if not actioning_user or not actioning_user.is_authenticated:
            raise PermissionDenied("Authentication is required.")

        if not isinstance(approve, bool):
            raise ValidationError(
                "The approve argument must be a Boolean."
            )

        with transaction.atomic():
            # Lock the order first, using a consistent lock order.
            order = (
                self.order.__class__.objects
                .select_for_update()
                .get(pk=self.order_id)
            )

            # Lock and refresh the transfer record.
            transfer = (
                ChangeOrderWaiter.objects
                .select_for_update()
                .get(pk=self.pk)
            )

            if transfer.status != TransferStatus.PENDING:
                raise ValidationError(
                    "This transfer request has already been processed."
                )

            is_manager = self._is_manager(actioning_user)
            is_receiving_waiter = (
                transfer.seted_waiter_id == actioning_user.pk
            )

            if not (is_manager or is_receiving_waiter):
                raise PermissionDenied(
                    "Only a manager or the receiving waiter can "
                    "approve or deny this transfer."
                )

            if approve:
                transfer._approve_locked(
                    actioning_user=actioning_user,
                    order=order,
                )
            else:
                transfer.status = TransferStatus.DENIED
                transfer.is_approved = False
                transfer.approved_by = actioning_user
                transfer.resolved_at = timezone.now()
                transfer.denial_reason = denial_reason

                transfer.save(
                    update_fields=[
                        "status",
                        "is_approved",
                        "approved_by",
                        "resolved_at",
                        "denial_reason",
                    ]
                )

            # Refresh the current Python instance for callers
            # that use the original object after processing.
            self.refresh_from_db()

            return self
