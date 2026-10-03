from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, Waiter, UserRole


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
        "is_active",
        "is_staff",
        "date_joined",
    )

    list_filter = (
        "role",
        "is_active",
        "is_staff",
        "is_superuser",
    )

    search_fields = (
        "username",
        "full_name",
        "email",
    )

    ordering = (
        "username",
    )

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
                "classes": (
                    "wide",
                ),
                "fields": (
                    "username",
                    "email",
                    "full_name",
                    "password1",
                    "password2",
                    "role",
                    "pin_hash",
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

    list_filter = (
        "is_active",
    )

    search_fields = (
        "username",
        "full_name",
        "email",
    )

    ordering = (
        "username",
    )

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
                "fields": (
                    "pin_hash",
                )
            },
        ),

        (
            "Status",
            {
                "fields": (
                    "is_active",
                )
            },
        ),
    )

    def get_queryset(self, request):
        """
        Only show users whose role is WAITER.
        """

        queryset = super().get_queryset(request)

        return queryset.filter(
            role=UserRole.WAITER
        )

    def save_model(self, request, obj, form, change):
        """
        Always force the user to be a waiter.
        """

        obj.role = UserRole.WAITER

        super().save_model(
            request,
            obj,
            form,
            change,
        )

    def get_readonly_fields(self, request, obj=None):
        """
        Prevent accidental changes to the role.
        """

        return ()

    def has_delete_permission(self, request, obj=None):
        """
        Allow deletion according to normal Django
        admin permissions.
        """

        return super().has_delete_permission(
            request,
            obj,
        )