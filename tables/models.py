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

    class Meta:
        ordering = ["table_number"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = f"Table {self.table_number}"

        super().save(*args, **kwargs)

    def set_as_reserved(self):
        self.status = TableStatus.RESERVED
        self.save(update_fields=["status"])

    def set_as_occupied(self):
        self.status = TableStatus.OCCUPIED
        self.save(update_fields=["status"])