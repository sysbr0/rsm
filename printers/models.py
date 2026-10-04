from django.conf import settings
from django.db import models

class PrinterType(models.TextChoices):
    THERMAL = "THERMAL", "Thermal"
    A4 = "A4", "A4"
    RECEIPT = "RECEIPT", "Receipt"


class ConnectionType(models.TextChoices):
    USB = "USB", "USB"
    NETWORK = "NETWORK", "Network"


class PrintJobStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PRINTING = "PRINTING", "Printing"
    PRINTED = "PRINTED", "Printed"
    FAILED = "FAILED", "Failed"


class Printer(models.Model):
    section = models.ForeignKey(
        "menu.Section",
        on_delete=models.CASCADE,
        related_name="printers",
    )

    name = models.CharField(max_length=100)

    printer_type = models.CharField(
        max_length=20,
        choices=PrinterType.choices,
        default=PrinterType.THERMAL,
    )

    connection_type = models.CharField(
        max_length=20,
        choices=ConnectionType.choices,
        default=ConnectionType.NETWORK,
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
    )

    port = models.PositiveIntegerField(
        default=9100,
    )

    usb_identifier = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )
    is_cashier = models.BooleanField(
    default=False,
)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PrintJob(models.Model):
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="print_jobs",
        null=True,
        blank=True,
)
    

    section = models.ForeignKey(
        "menu.Section",
        on_delete=models.CASCADE,
        related_name="print_jobs",
    )

    printer = models.ForeignKey(
        Printer,
        on_delete=models.PROTECT,
        related_name="print_jobs",
    )

    order_items = models.ManyToManyField(
        "orders.OrderItem",
        related_name="print_jobs",
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=PrintJobStatus.choices,
        default=PrintJobStatus.PENDING,
    )

    content = models.TextField()

    printed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    error_message = models.TextField(
        blank=True,
        default="",
    )

    retry_count = models.PositiveIntegerField(
        default=0,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PrintJob #{self.id} - Order #{self.order_id}"

 



class MessageToPrinter(models.Model):
    printer = models.ForeignKey(
        Printer,
        on_delete=models.PROTECT,
        related_name="messages",
    )

    table = models.ForeignKey(
        "tables.RestaurantTable",
        on_delete=models.CASCADE,
        related_name="printer_messages",
    )

    waiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="printer_messages",
    )

    message = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Printer message #{self.id}"