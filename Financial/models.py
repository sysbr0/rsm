from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def get_system_currency():
    """
    Get the restaurant currency from settings.py.

    Example:
        CURRENCY = os.getenv("CURRENCY", "₺")
    """
    return getattr(settings, "CURRENCY", "₺")


class MoneySource(models.Model):
    """
    Where the restaurant keeps its money.

    Examples:
    - Main Cash
    - Restaurant Bank Account
    - Safe
    - Other
    """

    SOURCE_TYPES = (
        ("CASH", "Cash"),
        ("BANK", "Bank"),
        ("OTHER", "Other"),
    )

    name = models.CharField(max_length=150)

    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_TYPES,
        default="CASH",
    )

    balance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    # Bank information
    bank_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    account_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    iban = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Money Source"
        verbose_name_plural = "Money Sources"

    def __str__(self):
        return f"{self.name} - {self.balance} {self.currency}"

    @property
    def currency(self):
        return get_system_currency()

    def increase_balance(self, amount):
        """
        Increase this source balance.
        """

        amount = Decimal(str(amount))

        if amount <= 0:
            raise ValidationError(
                "Amount must be greater than zero."
            )

        self.balance += amount
        self.save(update_fields=["balance", "updated_at"])

    def decrease_balance(self, amount):
        """
        Decrease this source balance.
        """

        amount = Decimal(str(amount))

        if amount <= 0:
            raise ValidationError(
                "Amount must be greater than zero."
            )

        if amount > self.balance:
            raise ValidationError(
                f"Insufficient balance. "
                f"Available: {self.balance} {self.currency}"
            )

        self.balance -= amount
        self.save(update_fields=["balance", "updated_at"])


class ReceivePayment(models.Model):
    """
    Money received by the restaurant.

    Example:
        Customer pays 500₺ for a restaurant order.

    Result:
        MoneySource balance +500₺
        FinancialTransaction created
    """


    source = models.ForeignKey(
        MoneySource,
        on_delete=models.PROTECT,
        related_name="received_payments",
    )

    # Optional connection to restaurant order
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="receive_payments",
        blank=True,
        null=True,
    )

    payer_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )

   

    reference = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    notes = models.TextField(
        blank=True,
        null=True,
    )

    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="received_payments_created",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Receive Payment"
        verbose_name_plural = "Receive Payments"

    def __str__(self):
        return (
            f"Receive {self.amount} "
            f"{self.currency} - {self.source.name}"
        )

    @property
    def currency(self):
        return get_system_currency()

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError(
                "Receive amount must be greater than zero."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MakePayment(models.Model):
    """
    Money paid by the restaurant.

    Examples:
        - Employee salary
        - Supplier payment
        - Client refund
        - Electricity expense
        - Other expense

    Result:
        MoneySource balance decreases
        FinancialTransaction created
    """

    PAYMENT_TYPES = (
        ("EMPLOYEE", "Employee"),
        ("SUPPLIER", "Supplier"),
        ("CLIENT", "Client"),
        ("EXPENSE", "Expense"),
        ("OTHER", "Other"),
    )

    source = models.ForeignKey(
        MoneySource,
        on_delete=models.PROTECT,
        related_name="made_payments",
    )

    payment_type = models.CharField(
        max_length=20,
        choices=PAYMENT_TYPES,
        default="EXPENSE",
    )

    receiver_name = models.CharField(
        max_length=150,
    )

    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )

    reference = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    notes = models.TextField(
        blank=True,
        null=True,
    )

    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="make_payments_created",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Make Payment"
        verbose_name_plural = "Make Payments"

    def __str__(self):
        return (
            f"Payment {self.amount} "
            f"{self.currency} - {self.receiver_name}"
        )

    @property
    def currency(self):
        return get_system_currency()

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError(
                "Payment amount must be greater than zero."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class FinancialTransaction(models.Model):
    """
    Permanent financial history.

    Every ReceivePayment or MakePayment should have
    one corresponding FinancialTransaction.
    """

    TRANSACTION_TYPES = (
        ("RECEIVE", "Receive"),
        ("PAYMENT", "Payment"),
    )

    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES,
    )

    source = models.ForeignKey(
        MoneySource,
        on_delete=models.PROTECT,
        related_name="financial_transactions",
    )

    receive_payment = models.OneToOneField(
        ReceivePayment,
        on_delete=models.PROTECT,
        related_name="financial_transaction",
        blank=True,
        null=True,
    )

    make_payment = models.OneToOneField(
        MakePayment,
        on_delete=models.PROTECT,
        related_name="financial_transaction",
        blank=True,
        null=True,
    )

    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )

    balance_before = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )

    balance_after = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="financial_transactions_created",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Financial Transaction"
        verbose_name_plural = "Financial Transactions"

    def __str__(self):
        sign = "+"

        if self.transaction_type == "PAYMENT":
            sign = "-"

        return (
            f"{sign}{self.amount} "
            f"{self.currency} - {self.source.name}"
        )

    @property
    def currency(self):
        return get_system_currency()

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError(
                "Transaction amount must be greater than zero."
            )

        if (
            self.transaction_type == "RECEIVE"
            and not self.receive_payment
        ):
            raise ValidationError(
                "Receive transaction must have a receive payment."
            )

        if (
            self.transaction_type == "PAYMENT"
            and not self.make_payment
        ):
            raise ValidationError(
                "Payment transaction must have a make payment."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)