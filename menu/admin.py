from django.contrib import admin

# Register your models here.
from django.contrib import admin

from .models import (
    Category,
    Product,
    ProductPrice,
    Section,
)


# ============================================================
# PRODUCT PRICE INLINE
# ============================================================

class ProductPriceInline(admin.TabularInline):
    model = ProductPrice
    extra = 0
    fields = (
        "price",
        "currency",
        "is_active",
        "valid_from",
        "valid_until",
    )
    ordering = ("-created_at",)


# ============================================================
# SECTION ADMIN
# ============================================================

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "display_order",
        "is_active",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
        "description",
    )

    ordering = (
        "display_order",
        "name",
    )

    list_editable = (
        "display_order",
        "is_active",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Section Information",
            {
                "fields": (
                    "name",
                    "description",
                )
            },
        ),
        (
            "Display",
            {
                "fields": (
                    "display_order",
                    "is_active",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


# ============================================================
# CATEGORY ADMIN
# ============================================================

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "display_order",
        "is_active",
        "created_at",
        "updated_at",
        "icon"
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
        "description",
    )

    ordering = (
        "display_order",
        "name",
    )

    list_editable = (
        "display_order",
        "is_active",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Category Information",
            {
                "fields": (
                    "name",
                    "description",
                )
            },
        ),
        (
            "Display",
            {
                "fields": (
                    "display_order",
                    "is_active",
                    "icon",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


# ============================================================
# PRODUCT ADMIN
# ============================================================

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "name",
        "category",
        "section",
        "price",
        "tax_rate",
        "is_active",
        "display_order",
        "created_at",
    )

    list_filter = (
        "is_active",
        "category",
        "section",
    )

    search_fields = (
        "sku",
        "name",
        "description",
    )

    ordering = (
        "category__display_order",
        "display_order",
        "name",
    )

    list_editable = (
        "price",
        "tax_rate",
        "display_order",
        "is_active",
    )

    autocomplete_fields = (
        "category",
        "section",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    inlines = (
        ProductPriceInline,
    )

    fieldsets = (
        (
            "Product Information",
            {
                "fields": (
                    "sku",
                    "name",
                    "description",
                )
            },
        ),
        (
            "Classification",
            {
                "fields": (
                    "category",
                    "section",
                )
            },
        ),
        (
            "Pricing",
            {
                "fields": (
                    "price",
                    "tax_rate",
                )
            },
        ),
        (
            "Display",
            {
                "fields": (
                    "display_order",
                    "is_active",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


# ============================================================
# PRODUCT PRICE ADMIN
# ============================================================

@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "price",
        "currency",
        "is_active",
        "valid_from",
        "valid_until",
        "created_at",
    )

    list_filter = (
        "currency",
        "is_active",
        "product__category",
        "product__section",
    )

    search_fields = (
        "product__name",
        "product__sku",
        "currency",
    )

    ordering = (
        "-created_at",
    )

    list_editable = (
        "price",
        "currency",
        "is_active",
    )

    autocomplete_fields = (
        "product",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Price",
            {
                "fields": (
                    "product",
                    "price",
                    "currency",
                )
            },
        ),
        (
            "Validity",
            {
                "fields": (
                    "is_active",
                    "valid_from",
                    "valid_until",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )