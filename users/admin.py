


from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, Waiter, UserRole, Attendance


# ============================================================
# ATTENDANCE ADMIN
# ============================================================

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "check_in",
        "check_out",
        "working_hours_display",
        "attendance_status",
    )

    list_filter = (
        "check_in",
        "check_out",
        "user__role",
    )

    search_fields = (
        "user__username",
        "user__full_name",
        "user__email",
    )

    ordering = (
        "-check_in",
    )

    date_hierarchy = "check_in"

    list_select_related = ("user",)

    readonly_fields = (
        "created_at",
        "working_duration_display",
        "working_hours_display",
        "attendance_status",
    )

    fieldsets = (
        (
            "Employee",
            {
                "fields": (
                    "user",
                )
            },
        ),
        (
            "Attendance Times",
            {
                "fields": (
                    "check_in",
                    "check_out",
                    "created_at",
                )
            },
        ),
        (
            "Working Time",
            {
                "fields": (
                    "working_duration_display",
                    "working_hours_display",
                    "attendance_status",
                )
            },
        ),
    )

    @admin.display(description="Working hours")
    def working_hours_display(self, obj):
        return f"{obj.working_hours:.2f} hours"

    @admin.display(description="Duration")
    def working_duration_display(self, obj):
        return obj.working_time_display

    @admin.display(description="Status")
    def attendance_status(self, obj):
        if obj.is_working:
            return "Currently working"
        return "Checked out"


# ============================================================
# USER ADMIN
# ============================================================

@admin.register(User)
class UserAdmin(DjangoUserAdmin):

    list_display = (
        "username",
        "full_name",
        "email",
        "role",
        "daily_working_hours",
        "is_active",
        "is_staff",
        "date_joined",
    )

    list_filter = (
        "role",
        "state",
        "is_active",
        "is_staff",
        "is_superuser",
    )

    search_fields = (
        "username",
        "full_name",
        "email",
    )

    ordering = ("username",)

    fieldsets = (
        (
            "Account",
            {
                "fields": (
                    "username",
                    "password",
                )
            },
        ),
        (
            "Personal Information",
            {
                "fields": (
                    "full_name",
                    "email",
                )
            },
        ),
        (
            "Restaurant Access",
            {
                "fields": (
                    "role",
                    "pin_hash",
                    "state",
                    "daily_working_hours",
                    "is_active",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Important Dates",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                )
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "full_name",
                    "password1",
                    "password2",
                    "role",
                    "pin_hash",
                    "daily_working_hours",
                    "state",
                    "is_active",
                ),
            },
        ),
    )


# ============================================================
# WAITER ADMIN
# ============================================================

@admin.register(Waiter)
class WaiterAdmin(admin.ModelAdmin):

    list_display = (
        "username",
        "full_name",
        "email",
        "is_active",
    )

    list_filter = ("is_active",)

    search_fields = (
        "username",
        "full_name",
        "email",
    )

    ordering = ("username",)

    fieldsets = (
        (
            "Waiter Information",
            {
                "fields": (
                    "username",
                    "full_name",
                    "email",
                )
            },
        ),
        (
            "PIN Authentication",
            {
                "fields": ("pin_hash",)
            },
        ),
        (
            "Status",
            {
                "fields": ("is_active",)
            },
        ),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.filter(role=UserRole.WAITER)

    def save_model(self, request, obj, form, change):
        obj.role = UserRole.WAITER
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj)

from django.contrib import admin
from django.utils import timezone

from .models import DayOffRequest, DayOffStatus


@admin.register(DayOffRequest)
class DayOffRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "date",
        "status",
        "reason",
        "reviewed_by",
        "reviewed_at",
        "created_at",
    )

    list_filter = (
        "status",
        "date",
        "created_at",
    )

    search_fields = (
        "user__username",
        "user__full_name",
        "user__email",
        "reason",
        "review_note",
        "reviewed_by__username",
    )

    list_select_related = (
        "user",
        "reviewed_by",
    )

    date_hierarchy = "date"
    ordering = ("date", "-created_at")
    list_per_page = 25

    readonly_fields = (
        "created_at",
        "reviewed_at",
    )

    fieldsets = (
        ("Request Information", {
            "fields": (
                "user",
                "date",
                "reason",
                "status",
            )
        }),
        ("Review Information", {
            "fields": (
                "reviewed_by",
                "reviewed_at",
                "review_note",
            )
        }),
        ("System Information", {
            "fields": ("created_at",)
        }),
    )

    actions = (
        "approve_requests",
        "reject_requests",
    )

    @admin.action(description="Approve selected day-off requests")
    def approve_requests(self, request, queryset):
        updated = 0

        for day_off in queryset.exclude(
            status=DayOffStatus.APPROVED
        ):
            day_off.status = DayOffStatus.APPROVED
            day_off.reviewed_by = request.user
            day_off.reviewed_at = timezone.now()
            day_off.save()
            updated += 1

        self.message_user(
            request,
            f"{updated} day-off request(s) approved.",
        )

    @admin.action(description="Reject selected day-off requests")
    def reject_requests(self, request, queryset):
        updated = 0

        for day_off in queryset.exclude(
            status=DayOffStatus.REJECTED
        ):
            day_off.status = DayOffStatus.REJECTED
            day_off.reviewed_by = request.user
            day_off.reviewed_at = timezone.now()
            day_off.save()
            updated += 1

        self.message_user(
            request,
            f"{updated} day-off request(s) rejected.",
        )
