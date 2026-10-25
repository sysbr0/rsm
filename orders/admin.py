from django.contrib import admin

from .models import Order, OrderItem, ChangeOrderWaiter


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


class ChangeOrderWaiterInline(admin.TabularInline):
    model = ChangeOrderWaiter
    extra = 0
    can_delete = False
    
    fields = (
        "current_waiter",
        "seted_waiter",
        "is_approved",
        "approved_by",
        "created_at",
    )
    
    readonly_fields = (
        "current_waiter",
        "seted_waiter",
        "is_approved",
        "approved_by",
        "created_at",
    )

    def has_add_permission(self, request, obj=None):
        # Prevent adding history directly from the Order page
        return False


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
        ChangeOrderWaiterInline,
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


@admin.register(ChangeOrderWaiter)
class ChangeOrderWaiterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "current_waiter",
        "seted_waiter",
        "is_approved",
        "approved_by",
        "created_at",
    )

    list_filter = (
        "is_approved",
        "created_at",
    )

    search_fields = (
        "order__id",
        "current_waiter__username",
        "seted_waiter__username",
    )

    autocomplete_fields = (
        "order",
        "current_waiter",
        "seted_waiter",
        "approved_by",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    date_hierarchy = "created_at"

    ordering = (
        "-created_at",
    )

    actions = ["approve_transfers"]

    @admin.action(description="Approve selected waiter transfers")
    def approve_transfers(self, request, queryset):
        updated_count = 0
        for change_req in queryset.filter(is_approved=False):
            # 1. Mark as approved
            change_req.is_approved = True
            change_req.approved_by = request.user
            change_req.save()

            # 2. Update the actual Order's waiter
            order = change_req.order
            order.waiter = change_req.seted_waiter
            order.save()
            
            updated_count += 1
            
        self.message_user(
            request, 
            f"{updated_count} waiter transfer(s) successfully approved and applied to orders."
        )