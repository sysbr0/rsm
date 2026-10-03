from rest_framework import serializers

from .models import (
    FinancialTransaction,
    MakePayment,
    MoneySource,
    ReceivePayment,
)


class MoneySourceSerializer(serializers.ModelSerializer):

    currency = serializers.ReadOnlyField()

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
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "balance",
            "currency",
            "created_at",
            "updated_at",
        ]


class ReceivePaymentSerializer(serializers.ModelSerializer):

    currency = serializers.ReadOnlyField()

    source_name = serializers.CharField(
        source="source.name",
        read_only=True,
    )

    class Meta:
        model = ReceivePayment

        fields = [
            "id",
            "source",
            "source_name",
            "order",
            "payer_name",
            "amount",
            "currency",
            "payment_method",
            "reference",
            "notes",
            "received_by",
            "created_at",
        ]

        read_only_fields = [
            "received_by",
            "currency",
            "created_at",
        ]

    def validate_amount(self, value):

        if value <= 0:
            raise serializers.ValidationError(
                "Amount must be greater than zero."
            )

        return value


class MakePaymentSerializer(serializers.ModelSerializer):

    currency = serializers.ReadOnlyField()

    source_name = serializers.CharField(
        source="source.name",
        read_only=True,
    )

    class Meta:
        model = MakePayment

        fields = [
            "id",
            "source",
            "source_name",
            "payment_type",
            "receiver_name",
            "amount",
            "currency",
            "reference",
            "notes",
            "paid_by",
            "created_at",
        ]

        read_only_fields = [
            "paid_by",
            "currency",
            "created_at",
        ]

    def validate_amount(self, value):

        if value <= 0:
            raise serializers.ValidationError(
                "Amount must be greater than zero."
            )

        return value


class FinancialTransactionSerializer(
    serializers.ModelSerializer
):

    currency = serializers.ReadOnlyField()

    source_name = serializers.CharField(
        source="source.name",
        read_only=True,
    )

    class Meta:
        model = FinancialTransaction

        fields = [
            "id",
            "transaction_type",
            "source",
            "source_name",
            "receive_payment",
            "make_payment",
            "amount",
            "currency",
            "balance_before",
            "balance_after",
            "description",
            "created_by",
            "created_at",
        ]

        read_only_fields = [
            "currency",
            "balance_before",
            "balance_after",
            "created_by",
            "created_at",
        ]