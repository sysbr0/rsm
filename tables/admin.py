from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.utils.html import format_html
from .models import SectionBlock, RestaurantTable, TableStatus


class RestaurantTableInline(admin.TabularInline):
    model = RestaurantTable
    extra = 1
    fields = ("table_number", "name", "capacity", "status", "is_active")
    ordering = ("table_number",)


@admin.register(SectionBlock)
class SectionBlockAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "location",
        "table_count",
        "display_order",
        "is_active",
    )
    list_filter = ("is_active", "location")
    search_fields = ("name", "description", "location")
    list_editable = ("display_order", "is_active")
    ordering = ("display_order", "name")
    inlines = [RestaurantTableInline]

    @admin.display(description="Total Tables")
    def table_count(self, obj):
        return obj.tables.count()


@admin.register(RestaurantTable)
class RestaurantTableAdmin(admin.ModelAdmin):
    list_display = (
        "table_number",
        "name",
        "section_block",
        "capacity",
        "status_badge",
        "location",
        "is_active",
    )
    list_filter = ("status", "section_block", "is_active", "location")
    search_fields = ("table_number", "name", "section_block__name")
    list_editable = ("is_active",)
    ordering = ("table_number",)
    actions = [
        "mark_as_available",
        "mark_as_occupied",
        "mark_as_reserved",
        "mark_as_closed",
    ]

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        color_map = {
            TableStatus.AVAILABLE: ("#166534", "#dcfce7"),  # Green
            TableStatus.OCCUPIED: ("#991b1b", "#fee2e2"),   # Red
            TableStatus.RESERVED: ("#92400e", "#fef3c7"),   # Amber
            TableStatus.ON_PAYMENT: ("#5b21b6", "#ede9fe"), # Purple
            TableStatus.CLOSED: ("#374151", "#f3f4f6"),     # Gray
        }
        text_color, bg_color = color_map.get(
            obj.status, ("#374151", "#f3f4f6")
        )
        return format_html(
            '<span style="background-color: {}; color: {}; padding: 4px 10px; '
            'border-radius: 9999px; font-weight: 700; font-size: 11px;">{}</span>',
            bg_color,
            text_color,
            obj.get_status_display(),
        )

    # Custom Admin Batch Actions
    @admin.action(description="Mark selected tables as Available")
    def mark_as_available(self, request, queryset):
        queryset.update(status=TableStatus.AVAILABLE)

    @admin.action(description="Mark selected tables as Occupied")
    def mark_as_occupied(self, request, queryset):
        queryset.update(status=TableStatus.OCCUPIED)

    @admin.action(description="Mark selected tables as Reserved")
    def mark_as_reserved(self, request, queryset):
        queryset.update(status=TableStatus.RESERVED)

    @admin.action(description="Mark selected tables as Closed")
    def mark_as_closed(self, request, queryset):
        queryset.update(status=TableStatus.CLOSED)