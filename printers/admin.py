from django.contrib import admin

# Register your models here.

from django.contrib import admin

from .models import (
    Printer,
    PrintJob,
    MessageToPrinter,
)


class PrintJobInline(admin.TabularInline):
    model = PrintJob
    extra = 0

    fields = (
        "order",
        "section",
        "status",
        "content",
        "printed_at",
        "retry_count",
        "error_message",
        "created_at",
    )

    readonly_fields = (
        "created_at",
        "printed_at",
    )

    show_change_link = True


class MessageToPrinterInline(admin.TabularInline):
    model = MessageToPrinter
    extra = 0

    fields = (
        "table",
        "waiter",
        "message",
        "created_at",
    )

    readonly_fields = (
        "created_at",
    )

    show_change_link = True


@admin.register(Printer)
class PrinterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "section",
        "printer_type",
        "connection_type",
        "ip_address",
        "port",
        "is_active",
        "created_at",
        "is_cashier",
    )

    list_filter = (
        "printer_type",
        "connection_type",
        "is_active",
        "section",
        "created_at",
        "is_cashier"
    )

    search_fields = (
        "name",
        "ip_address",
        "usb_identifier",
        "section__name",
    )

    list_editable = (
        "is_active",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    autocomplete_fields = (
        "section",
    )

    ordering = (
        "name",
    )

    fieldsets = (
        (
            "Printer Information",
            {
                "fields": (
                    "name",
                    "section",
                    "printer_type",
                    "connection_type",
                    "is_active",
                    "is_cashier"
                )
            },
        ),
        (
            "Connection",
            {
                "fields": (
                    "ip_address",
                    "port",
                    "usb_identifier",
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

    inlines = (
        PrintJobInline,
        MessageToPrinterInline,
    )


@admin.register(PrintJob)
class PrintJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "section",
        "printer",
        "status",
        "retry_count",
        "printed_at",
        "created_at",
    )

    list_filter = (
        "status",
        "printer",
        "section",
        "created_at",
        "printed_at",
    )

    search_fields = (
        "id",
        "order__id",
        "printer__name",
        "section__name",
        "error_message",
        "content",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "printed_at",
    )

    autocomplete_fields = (
        "order",
        "section",
        "printer",
    )

    date_hierarchy = "created_at"

    ordering = (
        "-created_at",
    )

    fieldsets = (
        (
            "Print Job",
            {
                "fields": (
                    "order",
                    "section",
                    "printer",
                    "status",
                )
            },
        ),
        (
            "Print Content",
            {
                "fields": (
                    "content",
                )
            },
        ),
        (
            "Printing Status",
            {
                "fields": (
                    "printed_at",
                    "retry_count",
                    "error_message",
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
    

@admin.register(MessageToPrinter)
class MessageToPrinterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "printer",
        "table",
        "waiter",
        "message_preview",
        "created_at",
    )

    list_filter = (
        "printer",
        "table",
        "created_at",
    )

    search_fields = (
        "message",
        "printer__name",
        "table__table_number",
        "waiter__username",
        "waiter__full_name",
    )

    readonly_fields = (
        "created_at",
    )

    autocomplete_fields = (
        "printer",
        "table",
        "waiter",
    )

    date_hierarchy = "created_at"

    ordering = (
        "-created_at",
    )

    @admin.display(description="Message")
    def message_preview(self, obj):
        if not obj.message:
            return "-"

        if len(obj.message) > 60:
            return f"{obj.message[:60]}..."

        return obj.message
