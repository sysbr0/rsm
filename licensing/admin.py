from django.contrib import admin

from .models import LocalLicense


@admin.register(LocalLicense)
class LocalLicenseAdmin(admin.ModelAdmin):
    list_display = (
        "license_key", "customer_name", "plan",
        "status", "is_active", "expires_at",
        "days_left", "warning_level_display", "valid_flag",
    )
    list_filter  = ("status", "is_active", "plan")
    search_fields = ("license_key", "customer_name")
    readonly_fields = (
        "installation_id", "created_at", "updated_at",
        "last_warning_shown_at",
    )

    @admin.display(description="Days left")
    def days_left(self, obj):
        return obj.days_remaining

    @admin.display(description="Warning")
    def warning_level_display(self, obj):
        return obj.warning_level or "—"

    @admin.display(boolean=True, description="Valid")
    def valid_flag(self, obj):
        return obj.is_valid()