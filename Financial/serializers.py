from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from .models import (
    FinancialTransaction,
    MakePayment,
    MoneySource,
    ReceivePayment,
    Transfer,
)


# -------------------------------------------------------------------
# MoneySource
# -------------------------------------------------------------------
class MoneySourceSerializer(serializers.ModelSerializer):
    currency = serializers.ReadOnlyField()
    total_received = serializers.SerializerMethodField()
    total_paid = serializers.SerializerMethodField()
    total_transferred_in = serializers.SerializerMethodField()
    total_transferred_out = serializers.SerializerMethodField()

    class Meta:
        model = MoneySource
        fields = [
            "id",
            "name",
            "source_type",
            "balance",
            "currency",
            "bank_name",
            "account_number",
            "iban",
            "description",
            "is_active",
            "total_received",
            "total_paid",
            "total_transferred_in",
            "total_transferred_out",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "balance", "created_at", "updated_at"]

    def get_total_received(self, obj):
        result = obj.received_payments.aggregate(total=Sum("amount"))["total"]
        return result or Decimal("0.00")

    def get_total_paid(self, obj):
        result = obj.made_payments.aggregate(total=Sum("amount"))["total"]
        return result or Decimal("0.00")

    def get_total_transferred_in(self, obj):
        result = obj.transfers_in.aggregate(total=Sum("amount"))["total"]
        return result or Decimal("0.00")

    def get_total_transferred_out(self, obj):
        result = obj.transfers_out.aggregate(total=Sum("amount"))["total"]
        return result or Decimal("0.00")


class MoneySourceListSerializer(serializers.ModelSerializer):
    currency = serializers.ReadOnlyField()

    class Meta:
        model = MoneySource
        fields = [
            "id",
            "name",
            "source_type",
            "balance",
            "currency",
            "is_active",
        ]


# -------------------------------------------------------------------
# ReceivePayment
# -------------------------------------------------------------------
class ReceivePaymentSerializer(serializers.ModelSerializer):
    currency = serializers.ReadOnlyField()
    source_name = serializers.CharField(source="source.name", read_only=True)
    received_by_name = serializers.CharField(
        source="received_by.get_full_name", read_only=True
    )
    order_reference = serializers.CharField(
        source="order.__str__", read_only=True, allow_null=True
    )

    class Meta:
        model = ReceivePayment
        fields = [
            "id",
            "source",
            "source_name",
            "order",
            "order_reference",
            "payer_name",
            "amount",
            "currency",
            "reference",
            "notes",
            "received_by",
            "received_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "received_by", "created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value


# -------------------------------------------------------------------
# MakePayment
# -------------------------------------------------------------------
class MakePaymentSerializer(serializers.ModelSerializer):
    currency = serializers.ReadOnlyField()
    source_name = serializers.CharField(source="source.name", read_only=True)
    paid_by_name = serializers.CharField(
        source="paid_by.get_full_name", read_only=True
    )
    payment_type_display = serializers.CharField(
        source="get_payment_type_display", read_only=True
    )

    class Meta:
        model = MakePayment
        fields = [
            "id",
            "source",
            "source_name",
            "payment_type",
            "payment_type_display",
            "receiver_name",
            "amount",
            "currency",
            "reference",
            "notes",
            "paid_by",
            "paid_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "paid_by", "created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate(self, attrs):
        source = attrs.get("source")
        amount = attrs.get("amount")
        if source and amount and amount > source.balance:
            raise serializers.ValidationError(
                {
                    "amount": (
                        f"Insufficient balance. "
                        f"Available: {source.balance} {source.currency}"
                    )
                }
            )
        return attrs


# -------------------------------------------------------------------
# Transfer  ← NEW
# -------------------------------------------------------------------
class TransferSerializer(serializers.ModelSerializer):
    currency = serializers.ReadOnlyField()
    from_source_name = serializers.CharField(
        source="from_source.name", read_only=True
    )
    to_source_name = serializers.CharField(
        source="to_source.name", read_only=True
    )
    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True
    )

    class Meta:
        model = Transfer
        fields = [
            "id",
            "from_source",
            "from_source_name",
            "to_source",
            "to_source_name",
            "amount",
            "currency",
            "reference",
            "notes",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate(self, attrs):
        from_source = attrs.get("from_source")
        to_source = attrs.get("to_source")
        amount = attrs.get("amount")

        if from_source and to_source and from_source.pk == to_source.pk:
            raise serializers.ValidationError(
                "Source and destination must be different."
            )
        if from_source and not from_source.is_active:
            raise serializers.ValidationError(
                {"from_source": f"'{from_source.name}' is not active."}
            )
        if to_source and not to_source.is_active:
            raise serializers.ValidationError(
                {"to_source": f"'{to_source.name}' is not active."}
            )
        if from_source and amount and amount > from_source.balance:
            raise serializers.ValidationError(
                {
                    "amount": (
                        f"Insufficient balance in {from_source.name}. "
                        f"Available: {from_source.balance} {from_source.currency}"
                    )
                }
            )
        return attrs


# -------------------------------------------------------------------
# FinancialTransaction
# -------------------------------------------------------------------
class FinancialTransactionSerializer(serializers.ModelSerializer):
    currency = serializers.ReadOnlyField()
    source_name = serializers.CharField(source="source.name", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True
    )
    transaction_type_display = serializers.CharField(
        source="get_transaction_type_display", read_only=True
    )
    signed_amount = serializers.SerializerMethodField()

    class Meta:
        model = FinancialTransaction
        fields = [
            "id",
            "transaction_type",
            "transaction_type_display",
            "source",
            "source_name",
            "receive_payment",
            "make_payment",
            "transfer",
            "amount",
            "signed_amount",
            "currency",
            "balance_before",
            "balance_after",
            "description",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_signed_amount(self, obj):
        if obj.transaction_type in ("PAYMENT", "TRANSFER_OUT"):
            return -obj.amount
        return obj.amount