from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    FinancialTransaction,
    MakePayment,
    MoneySource,
    ReceivePayment,
)


@transaction.atomic
def receive_money(
    *,
    source,
    amount,
    received_by,
    order=None,
    payer_name=None,
    payment_method="CASH",
    reference=None,
    notes=None,
):
    """
    Receive money into a MoneySource.

    Example:

        receive_money(
            source=source,
            amount=500,
            received_by=request.user,
            order=order,
            payer_name="Customer",
        )

    This will:

        1. Lock the money source.
        2. Read the old balance.
        3. Create ReceivePayment.
        4. Increase source balance.
        5. Create FinancialTransaction.
    """

    amount = Decimal(str(amount))

    if amount <= 0:
        raise ValidationError(
            "Receive amount must be greater than zero."
        )

    # Lock source to prevent simultaneous balance changes.
    source = (
        MoneySource.objects
        .select_for_update()
        .get(pk=source.pk)
    )

    balance_before = source.balance
    balance_after = balance_before + amount

    receive_payment = ReceivePayment.objects.create(
        source=source,
        order=order,
        payer_name=payer_name,
        amount=amount,
        payment_method=payment_method,
        reference=reference,
        notes=notes,
        received_by=received_by,
    )

    source.balance = balance_after
    source.save(
        update_fields=[
            "balance",
            "updated_at",
        ]
    )

    description = "Money received"

    if payer_name:
        description = f"Money received from {payer_name}"

    if order:
        description = (
            f"Payment received for Order #{order.pk}"
        )

    financial_transaction = (
        FinancialTransaction.objects.create(
            transaction_type="RECEIVE",
            source=source,
            receive_payment=receive_payment,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            description=description,
            created_by=received_by,
        )
    )

    return (
        receive_payment,
        financial_transaction,
    )


@transaction.atomic
def make_payment(
    *,
    source,
    amount,
    paid_by,
    payment_type="EXPENSE",
    receiver_name,
    reference=None,
    notes=None,
):
    """
    Make a payment from a MoneySource.

    This will:

        1. Lock the money source.
        2. Check available balance.
        3. Create MakePayment.
        4. Decrease source balance.
        5. Create FinancialTransaction.
    """

    amount = Decimal(str(amount))

    if amount <= 0:
        raise ValidationError(
            "Payment amount must be greater than zero."
        )

    # Lock source.
    source = (
        MoneySource.objects
        .select_for_update()
        .get(pk=source.pk)
    )

    balance_before = source.balance

    if amount > balance_before:
        raise ValidationError(
            f"Insufficient balance. "
            f"Available: {balance_before} "
            f"{source.currency}"
        )

    balance_after = balance_before - amount

    make_payment_obj = MakePayment.objects.create(
        source=source,
        payment_type=payment_type,
        receiver_name=receiver_name,
        amount=amount,
        reference=reference,
        notes=notes,
        paid_by=paid_by,
    )

    source.balance = balance_after

    source.save(
        update_fields=[
            "balance",
            "updated_at",
        ]
    )

    description = (
        f"Payment made to {receiver_name}"
    )

    financial_transaction = (
        FinancialTransaction.objects.create(
            transaction_type="PAYMENT",
            source=source,
            make_payment=make_payment_obj,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            description=description,
            created_by=paid_by,
        )
    )

    return (
        make_payment_obj,
        financial_transaction,
    )