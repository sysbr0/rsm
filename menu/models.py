from django.db import models

# Create your models here.
from decimal import Decimal
from django.db.models import Q
from .utils import generate_uuid_str
from django.core.validators import MinValueValidator, MaxValueValidator

from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError


import uuid



from django.core.validators import FileExtensionValidator
from django.db import models


# ---------- Helper functions ----------

def generate_uuid_str() -> str:
    """Return a lowercase UUID4 as a 36-char string."""
    return str(uuid.uuid4()).lower()


def validate_icon_size(value):
    """Reject icons larger than 1 MB."""
    limit = 1024 * 1024  # 1 MB
    if value.size > limit:
        from django.core.exceptions import ValidationError
        raise ValidationError("Icon must be smaller than 1 MB.")




class LocalTimeStampedModel(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    version = models.PositiveBigIntegerField(default=1)
    is_synced = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk and not kwargs.get("update_fields"):
            self.version += 1
            self.is_synced = False
        super().save(*args, **kwargs)


class Section(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    display_order = models.PositiveIntegerField(
        default=0,
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

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name

# ---------- Model ----------

class Category(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    display_order = models.PositiveIntegerField(
        default=0,
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

    uuid = models.CharField(
        max_length=36,
        default=generate_uuid_str,
        editable=False,
        unique=True,
        # NOTE: db_index=True is redundant with unique=True.
        #       Remove it.
    )

    icon = models.FileField(
        upload_to="categories/icons/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["svg"]),
            validate_icon_size,
        ],
        help_text="Upload an SVG icon smaller than 1 MB.",
    )

    version        = models.PositiveBigIntegerField(default=1)
    is_synced      = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)


    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Normalize UUID to lowercase
        if self.uuid:
            self.uuid = self.uuid.lower()
        super().save(*args, **kwargs)




class Product(models.Model):
    # ... all your existing fields stay untouched ...

    sku = models.CharField(max_length=100, unique=True)
    uuid = models.CharField(
        max_length=36,
        default=generate_uuid_str,
        editable=False,
        unique=True,
        db_index=True,
    )
    name = models.CharField(max_length=150)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="products",
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
    )
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ==================================================
    # NEW — sync metadata
    # ==================================================
    is_synced = models.BooleanField(
        default=False,
        db_index=True,
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    local_version = models.PositiveBigIntegerField(
        default=1,
        help_text="Incremented on every local change.",
    )

    class Meta:
        ordering = [
            "category__display_order",
            "display_order",
            "name",
        ]

    def __str__(self):
        return self.name

    def get_current_price(self):
        return self.price




class ProductPrice(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="prices",
    )

    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )

    currency = models.CharField(
        max_length=10,
        default="TL",
    )

    is_active = models.BooleanField(
        default=True,
    )

    valid_from = models.DateTimeField(
        null=True,
        blank=True,
    )

    valid_until = models.DateTimeField(
        null=True,
        blank=True,
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
        return f"{self.product.name} - {self.price} {self.currency}"