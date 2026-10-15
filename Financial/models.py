from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


def get_system_currency():
    return getattr(settings, "CURRENCY", "₺")


# ===================================================================
# MoneySource
# ===================================================================
class MoneySource(models.Model):
    SOURCE_TYPES = (
        ("CASH", "Cash"),
        ("BANK", "Bank"),
        ("OTHER", "Other"),
    )

    name = models.CharField(max_length=150)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES, default="CASH")

    balance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
        help_text="Derived from payments. Do not edit directly.",
    )

    bank_name = models.CharField(max_length=150, blank=True, null=True)
    account_number = models.CharField(max_length=100, blank=True, null=True)
    iban = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Money Source"
        verbose_name_plural = "Money Sources"

    def __str__(self):
        return f"{self.name} - {self.balance} {self.currency}"

    @property
    def currency(self):
        return get_system_currency()

    def _set_balance(self, new_balance):
        self.balance = Decimal(str(new_balance))
        self.save(update_fields=["balance", "updated_at"])

    def increase_balance(self, amount):
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValidationError("Amount must be greater than zero.")
        self._set_balance(self.balance + amount)

    def decrease_balance(self, amount):
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValidationError("Amount must be greater than zero.")
        if amount > self.balance:
            raise ValidationError(
                f"Insufficient balance. Available: {self.balance} {self.currency}"
            )
        self._set_balance(self.balance - amount)

    def recalculate_balance(self, save=True):
        """Recompute balance from all money movements."""
        from django.db.models import Sum

        received = (
            self.received_payments.aggregate(t=Sum("amount"))["t"]
            or Decimal("0.00")
        )
        paid = (
            self.made_payments.aggregate(t=Sum("amount"))["t"]
            or Decimal("0.00")
        )
        transferred_in = (
            self.transfers_in.aggregate(t=Sum("amount"))["t"]
            or Decimal("0.00")
        )
        transferred_out = (
            self.transfers_out.aggregate(t=Sum("amount"))["t"]
            or Decimal("0.00")
        )

        self.balance = received + transferred_in - paid - transferred_out
        if save:
            self.save(update_fields=["balance", "updated_at"])
        return self.balance


# ===================================================================
# ReceivePayment
# ===================================================================
class ReceivePayment(models.Model):
    source = models.ForeignKey(
        MoneySource, on_delete=models.PROTECT, related_name="received_payments"
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="receive_payments",
        blank=True, null=True,
    )
    payer_name = models.CharField(max_length=150, blank=True, null=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    reference = models.CharField(max_length=150, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="received_payments_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Receive Payment"
        verbose_name_plural = "Receive Payments"

    def __str__(self):
        return f"Receive {self.amount} {self.currency} - {self.source.name}"

    @property
    def currency(self):
        return get_system_currency()

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError("Receive amount must be greater than zero.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Receive payments cannot be deleted directly. "
            "Reverse it with an adjusting entry instead."
        )


# ===================================================================
# MakePayment
# ===================================================================
class MakePayment(models.Model):
    PAYMENT_TYPES = (
        ("EMPLOYEE", "Employee"),
        ("SUPPLIER", "Supplier"),
        ("CLIENT", "Client"),
        ("EXPENSE", "Expense"),
        ("OTHER", "Other"),
    )

    source = models.ForeignKey(
        MoneySource, on_delete=models.PROTECT, related_name="made_payments"
    )
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES, default="EXPENSE")
    receiver_name = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    reference = models.CharField(max_length=150, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="make_payments_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Make Payment"
        verbose_name_plural = "Make Payments"

    def __str__(self):
        return f"Payment {self.amount} {self.currency} - {self.receiver_name}"

    @property
    def currency(self):
        return get_system_currency()

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError("Payment amount must be greater than zero.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Make payments cannot be deleted directly. "
            "Reverse it with an adjusting entry instead."
        )


# ===================================================================
# Transfer
# ===================================================================
class Transfer(models.Model):
    """
    Move money between two MoneySources atomically.
    Always go through services.transfer_money().
    """

    from_source = models.ForeignKey(
        MoneySource,
        on_delete=models.PROTECT,
        related_name="transfers_out",
    )
    to_source = models.ForeignKey(
        MoneySource,
        on_delete=models.PROTECT,
        related_name="transfers_in",
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    reference = models.CharField(max_length=150, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transfers_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Transfer"
        verbose_name_plural = "Transfers"

    def __str__(self):
        return (
            f"Transfer {self.amount} {self.currency}: "
            f"{self.from_source} → {self.to_source}"
        )

    @property
    def currency(self):
        return get_system_currency()

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError("Transfer amount must be greater than zero.")
        if self.from_source_id and self.to_source_id:
            if self.from_source_id == self.to_source_id:
                raise ValidationError("Cannot transfer to the same source.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Transfers cannot be deleted directly. Reverse with a new entry."
        )


# ===================================================================
# FinancialTransaction — immutable ledger
# ===================================================================
class FinancialTransaction(models.Model):
    TRANSACTION_TYPES = (
        ("RECEIVE", "Receive"),
        ("PAYMENT", "Payment"),
        ("TRANSFER_OUT", "Transfer Out"),
        ("TRANSFER_IN", "Transfer In"),
    )

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    source = models.ForeignKey(
        MoneySource, on_delete=models.PROTECT, related_name="financial_transactions"
    )
    receive_payment = models.OneToOneField(
        ReceivePayment,
        on_delete=models.PROTECT,
        related_name="financial_transaction",
        blank=True, null=True,
    )
    make_payment = models.OneToOneField(
        MakePayment,
        on_delete=models.PROTECT,
        related_name="financial_transaction",
        blank=True, null=True,
    )
    # FK (not OneToOne) — a Transfer produces TWO ledger rows.
    transfer = models.ForeignKey(
        Transfer,
        on_delete=models.PROTECT,
        related_name="financial_transactions",
        blank=True, null=True,
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    balance_before = models.DecimalField(max_digits=18, decimal_places=2)
    balance_after = models.DecimalField(max_digits=18, decimal_places=2)
    description = models.CharField(max_length=255, blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="financial_transactions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Financial Transaction"
        verbose_name_plural = "Financial Transactions"

    def __str__(self):
        sign = "−" if self.transaction_type in ("PAYMENT", "TRANSFER_OUT") else "+"
        return f"{sign}{self.amount} {self.currency} - {self.source.name}"

    @property
    def currency(self):
        return get_system_currency()

    @property
    def signed_amount(self):
        if self.transaction_type in ("PAYMENT", "TRANSFER_OUT"):
            return -self.amount
        return self.amount

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError("Transaction amount must be greater than zero.")
        if self.transaction_type == "RECEIVE" and not self.receive_payment:
            raise ValidationError("Receive transaction must have a receive payment.")
        if self.transaction_type == "PAYMENT" and not self.make_payment:
            raise ValidationError("Payment transaction must have a make payment.")
        if self.transaction_type in ("TRANSFER_OUT", "TRANSFER_IN") and not self.transfer:
            raise ValidationError("Transfer transaction must have a transfer.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Financial transactions are immutable. Reverse with a new entry."
        )