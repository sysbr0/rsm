from django.contrib import admin

from .models import (
    FinancialTransaction,
    MakePayment,
    MoneySource,
    ReceivePayment,
)


@admin.register(MoneySource)
class MoneySourceAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "source_type",
        "balance_display",
        "is_active",
        "created_at",
    )

    list_filter = (
        "source_type",
        "is_active",
    )

    search_fields = (
        "name",
        "bank_name",
        "account_number",
        "iban",
    )

    readonly_fields = (
        "balance",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Balance")
    def balance_display(self, obj):
        return f"{obj.balance} {obj.currency}"


@admin.register(ReceivePayment)
class ReceivePaymentAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "source",
        "payer_name",
        "amount_display",
  
        "order",
        "received_by",
        "created_at",
    )

    list_filter = (
  
        "created_at",
    )

    search_fields = (
        "payer_name",
        "reference",
        "notes",
    )

    readonly_fields = (
        "created_at",
    )

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return f"{obj.amount} {obj.currency}"


@admin.register(MakePayment)
class MakePaymentAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "source",
        "payment_type",
        "receiver_name",
        "amount_display",
        "paid_by",
        "created_at",
    )

    list_filter = (
        "payment_type",
        "created_at",
    )

    search_fields = (
        "receiver_name",
        "reference",
        "notes",
    )

    readonly_fields = (
        "created_at",
    )

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return f"{obj.amount} {obj.currency}"


@admin.register(FinancialTransaction)
class FinancialTransactionAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "transaction_type",
        "source",
        "amount_display",
        "balance_before_display",
        "balance_after_display",
        "created_by",
        "created_at",
    )

    list_filter = (
        "transaction_type",
        "created_at",
        "source",
    )

    search_fields = (
        "description",
    )

    readonly_fields = (
        "transaction_type",
        "source",
        "receive_payment",
        "make_payment",
        "amount",
        "balance_before",
        "balance_after",
        "description",
        "created_by",
        "created_at",
    )

    @admin.display(description="Amount")
    def amount_display(self, obj):
        sign = "+"

        if obj.transaction_type == "PAYMENT":
            sign = "-"

        return f"{sign}{obj.amount} {obj.currency}"

    @admin.display(description="Before")
    def balance_before_display(self, obj):
        return f"{obj.balance_before} {obj.currency}"

    @admin.display(description="After")
    def balance_after_display(self, obj):
        return f"{obj.balance_after} {obj.currency}"