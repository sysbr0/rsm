from django.db import models


class TableStatus(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    OCCUPIED = "OCCUPIED", "Occupied"
    RESERVED = "RESERVED", "Reserved"
    ON_PAYMENT = "ON_PAYMENT", "On Payment"
    CLOSED = "CLOSED", "Closed"


class SectionBlock(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    location = models.CharField(
        max_length=100,
        default="main",
    )
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name

from django.db import models


class RestaurantTable(models.Model):
    table_number = models.PositiveIntegerField(unique=True)

    name = models.CharField(
        max_length=80,
        blank=True,
    )

    section_block = models.ForeignKey(
        SectionBlock,
        on_delete=models.PROTECT,
        related_name="tables",
        null=True,
        blank=True,
    )

    capacity = models.PositiveIntegerField(default=4)

    status = models.CharField(
        max_length=20,
        choices=TableStatus.choices,
        default=TableStatus.AVAILABLE,
    )

    location = models.CharField(
        max_length=100,
        default="main",
    )

    is_active = models.BooleanField(default=True)
    worning = models.BooleanField(default=False)

    class Meta:
        ordering = ["table_number"]

    def __str__(self):
        return self.name or f"Table {self.table_number}"

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = f"Table {self.table_number}"

        super().save(*args, **kwargs)

    # ==================================================
    # TABLE STATUS
    # ==================================================

    def set_as_reserved(self):
        self.status = TableStatus.RESERVED
        self.save(update_fields=["status"])

    def set_as_occupied(self):
        self.status = TableStatus.OCCUPIED
        self.save(update_fields=["status"])

    def set_as_on_payment(self):
        self.status = TableStatus.ON_PAYMENT
        self.save(update_fields=["status"])

    # ==================================================
    # WARNING CONTROL
    # ==================================================

    def activate_warning(self):
        if not self.worning:
            self.worning = True
            self.save(update_fields=["worning"])

    def deactivate_warning(self):
        if self.worning:
            self.worning = False
            self.save(update_fields=["worning"])

    # ==================================================
    # GET WARNING DETAILS
    # ==================================================

    def get_warning_details(self):
        from orders.models import (
            OrderItem,
            ChangeOrderWaiter,
            TransferStatus,
            OrderStatus,
        )

        warnings = []

        # ----------------------------------------------
        # 1. Pending waiter transfers
        # ----------------------------------------------

        pending_transfers = (
            ChangeOrderWaiter.objects.filter(
                order__table_id=self.pk,
                status=TransferStatus.PENDING,
            )
            .select_related(
                "current_waiter",
                "seted_waiter",
            )
        )

        for transfer in pending_transfers:
            warnings.append({
                "type": "TRANSFER_PENDING",
                "message": (
                    "Waiter transfer is awaiting approval."
                ),
                "transfer_id": transfer.pk,
                "from_waiter": (
                    transfer.current_waiter.full_name
                    if transfer.current_waiter
                    else None
                ),
                "to_waiter": (
                    transfer.seted_waiter.full_name
                    if transfer.seted_waiter
                    else None
                ),
            })

        # ----------------------------------------------
        # 2. Order items awaiting printing
        # ----------------------------------------------

        active_statuses = [
            OrderStatus.OPEN,
            OrderStatus.CONFIRMED,
            OrderStatus.PREPARING,
            OrderStatus.READY,
            OrderStatus.SERVED,
        ]

        pending_items = OrderItem.objects.filter(
            order__table_id=self.pk,
            order__status__in=active_statuses,
            has_print_job=False,
        )

        pending_item_count = pending_items.count()

        if pending_item_count:
            warnings.append({
                "type": "ITEMS_NOT_PRINTED",
                "message": (
                    "Some order items have not been printed."
                ),
                "item_count": pending_item_count,
            })

        # ----------------------------------------------
        # 3. Return the result for this table
        # ----------------------------------------------

        return {
            "table_id": self.pk,
            "table_number": self.table_number,
            "table_name": self.name,
            "has_warning": bool(warnings),
            "warnings": warnings,
        }

    # ==================================================
    # SYNCHRONIZE WARNING BOOLEAN
    # ==================================================

    def sync_warning(self):
        """
        Update the worning field based on pending transfers
        and order items awaiting printing.
        """
        details = self.get_warning_details()
        has_warning = details["has_warning"]

        if self.worning != has_warning:
            self.worning = has_warning
            self.save(update_fields=["worning"])

        return details



    @classmethod
    def sync_all_occupied_warnings(cls):
        """
        Synchronize warnings for all occupied tables.
        Returns a summary of tables requiring attention.
        """
        tables = cls.objects.filter(
            status=TableStatus.OCCUPIED
        )

        results = {
            "checked": 0,
            "need_attention": 0,
            "no_attention": 0,
            "tables": [],
        }

        for table in tables.iterator():
            details = table.sync_warning()

            results["checked"] += 1

            if details["has_warning"]:
                results["need_attention"] += 1
            else:
                results["no_attention"] += 1

            results["tables"].append(details)

        return results