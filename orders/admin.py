from django.contrib import admin

# Register your models here.
from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0

    fields = (
        "product",
        "quantity",
        "unit_price",
        "discount",
        "notes",
        "status",
        "has_print_job",
    )

    readonly_fields = (
        "unit_price",
        "has_print_job",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "table",
        "waiter",
        "status",
        "subtotal",
        "tax",
        "discount",
        "total",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
        "table",
    )

    search_fields = (
        "id",
        "table__table_number",
        "table__name",
        "waiter__username",
        "waiter__full_name",
    )

    readonly_fields = (
        "subtotal",
        "tax",
        "discount",
        "total",
        "created_at",
        "updated_at",
    )

    autocomplete_fields = (
        "table",
        "waiter",
    )

    date_hierarchy = "created_at"

    ordering = (
        "-created_at",
    )

    inlines = (
        OrderItemInline,
    )

    fieldsets = (
        (
            "Order Information",
            {
                "fields": (
                    "table",
                    "waiter",
                    "status",
                )
            },
        ),
        (
            "Financial Information",
            {
                "fields": (
                    "subtotal",
                    "tax",
                    "discount",
                    "total",
                )
            },
        ),
        (
            "System Information",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "product",
        "quantity",
        "unit_price",
        "discount",
        "status",
        "has_print_job",
        "created_at",
    )

    list_filter = (
        "status",
        "has_print_job",
        "created_at",
    )

    search_fields = (
        "order__id",
        "product__name",
        "notes",
    )

    readonly_fields = (
        "unit_price",
        "created_at",
        "updated_at",
    )

    autocomplete_fields = (
        "order",
        "product",
    )

    date_hierarchy = "created_at"

    ordering = (
        "-created_at",
    )
