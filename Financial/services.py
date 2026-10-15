# financial/services.py
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    FinancialTransaction,
    MakePayment,
    MoneySource,
    ReceivePayment,
    Transfer,
)


# ===================================================================
# Receive
# ===================================================================
@transaction.atomic
def receive_money(
    *,
    source,
    amount,
    received_by,
    order=None,
    payer_name=None,
    reference=None,
    notes=None,
):
    """Receive money into a MoneySource. Atomic."""
    amount = Decimal(str(amount))

    if amount <= 0:
        raise ValidationError("Receive amount must be greater than zero.")

    source = MoneySource.objects.select_for_update().get(pk=source.pk)

    balance_before = source.balance
    balance_after = balance_before + amount

    receive_payment = ReceivePayment.objects.create(
        source=source,
        order=order,
        payer_name=payer_name,
        amount=amount,
        reference=reference,
        notes=notes,
        received_by=received_by,
    )

    source._set_balance(balance_after)

    description = "Money received"
    if order:
        description = f"Payment received for Order #{order.pk}"
    elif payer_name:
        description = f"Money received from {payer_name}"

    financial_transaction = FinancialTransaction.objects.create(
        transaction_type="RECEIVE",
        source=source,
        receive_payment=receive_payment,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        description=description,
        created_by=received_by,
    )

    return receive_payment, financial_transaction


# ===================================================================
# Make Payment
# ===================================================================
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
    """Make a payment from a MoneySource. Atomic."""
    amount = Decimal(str(amount))

    if amount <= 0:
        raise ValidationError("Payment amount must be greater than zero.")

    source = MoneySource.objects.select_for_update().get(pk=source.pk)

    balance_before = source.balance

    if amount > balance_before:
        raise ValidationError(
            f"Insufficient balance. "
            f"Available: {balance_before} {source.currency}"
        )

    balance_after = balance_before - amount

    payment = MakePayment.objects.create(
        source=source,
        payment_type=payment_type,
        receiver_name=receiver_name,
        amount=amount,
        reference=reference,
        notes=notes,
        paid_by=paid_by,
    )

    source._set_balance(balance_after)

    financial_transaction = FinancialTransaction.objects.create(
        transaction_type="PAYMENT",
        source=source,
        make_payment=payment,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        description=f"Payment made to {receiver_name}",
        created_by=paid_by,
    )

    return payment, financial_transaction


# ===================================================================
# Transfer
# ===================================================================
@transaction.atomic
def transfer_money(
    *,
    from_source,
    to_source,
    amount,
    user,
    reference=None,
    notes=None,
):
    """
    Move money from one MoneySource to another, atomically.

    - Locks both source rows (sorted ID order to avoid deadlocks).
    - Validates both are active and source has sufficient balance.
    - Creates one Transfer row.
    - Writes TWO immutable ledger rows (TRANSFER_OUT + TRANSFER_IN).
    """
    amount = Decimal(str(amount))

    if amount <= 0:
        raise ValidationError("Transfer amount must be greater than zero.")

    if from_source.pk == to_source.pk:
        raise ValidationError("Cannot transfer to the same source.")

    ids = sorted([from_source.pk, to_source.pk])
    locked = {
        s.pk: s
        for s in MoneySource.objects.select_for_update().filter(pk__in=ids)
    }

    try:
        src = locked[from_source.pk]
        dst = locked[to_source.pk]
    except KeyError as exc:
        raise ValidationError(f"Money source not found: {exc}") from exc

    if not src.is_active:
        raise ValidationError(f"Source '{src.name}' is not active.")
    if not dst.is_active:
        raise ValidationError(f"Destination '{dst.name}' is not active.")

    if amount > src.balance:
        raise ValidationError(
            f"Insufficient balance in {src.name}. "
            f"Available: {src.balance} {src.currency}"
        )

    transfer = Transfer.objects.create(
        from_source=src,
        to_source=dst,
        amount=amount,
        reference=reference,
        notes=notes,
        created_by=user,
    )

    # Leg 1 — out
    src_before = src.balance
    src_after = src_before - amount
    src._set_balance(src_after)

    FinancialTransaction.objects.create(
        transaction_type="TRANSFER_OUT",
        source=src,
        transfer=transfer,
        amount=amount,
        balance_before=src_before,
        balance_after=src_after,
        description=f"Transfer to {dst.name}",
        created_by=user,
    )

    # Leg 2 — in
    dst_before = dst.balance
    dst_after = dst_before + amount
    dst._set_balance(dst_after)

    FinancialTransaction.objects.create(
        transaction_type="TRANSFER_IN",
        source=dst,
        transfer=transfer,
        amount=amount,
        balance_before=dst_before,
        balance_after=dst_after,
        description=f"Transfer from {src.name}",
        created_by=user,
    )

    return transfer