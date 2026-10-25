from django.contrib import admin

# Register your models here.

from django.contrib import admin
from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sender",
        "recipient",
        "sent_at",
        "is_read",
    )
    list_filter = ("is_read", "sent_at")
    search_fields = ("content",)
    readonly_fields = ("sent_at",)
