from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    FinancialTransaction,
    MakePayment,
    MoneySource,
    ReceivePayment,
    Transfer,
)


class BaseStyledForm(forms.ModelForm):
    """Applies consistent Tailwind classes to all widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            css = "form-input"
            if isinstance(widget, forms.Select):
                css = "form-select"
            elif isinstance(widget, forms.Textarea):
                css = "form-textarea"
            elif isinstance(widget, forms.CheckboxInput):
                css = "form-checkbox"
            existing = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{existing} {css}".strip()
            if isinstance(widget, (forms.TextInput, forms.NumberInput, forms.Textarea)):
                widget.attrs.setdefault("placeholder", field.label or name.title())


# ===================================================================
# MoneySource
# ===================================================================
class MoneySourceForm(BaseStyledForm):
    class Meta:
        model = MoneySource
        fields = [
            "name",
            "source_type",
            "bank_name",
            "account_number",
            "iban",
            "description",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        source_type = cleaned.get("source_type")
        if source_type == "BANK":
            if not cleaned.get("bank_name"):
                self.add_error("bank_name", "Bank name is required for bank accounts.")
            if not cleaned.get("iban") and not cleaned.get("account_number"):
                self.add_error(
                    "iban",
                    "Provide either IBAN or account number for bank accounts.",
                )
        return cleaned


# ===================================================================
# ReceivePayment
# ===================================================================
class ReceivePaymentForm(BaseStyledForm):
    class Meta:
        model = ReceivePayment
        fields = [
            "source",
            "order",
            "payer_name",
            "amount",
            "reference",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["source"].queryset = (
            MoneySource.objects.filter(is_active=True).order_by("name")
        )
        self.fields["source"].empty_label = "— Select source —"
        # Order is optional. If the orders app isn't installed, drop it.
        if "order" in self.fields:
            self.fields["order"].required = False

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is not None and amount <= 0:
            raise ValidationError("Amount must be greater than zero.")
        return amount

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user and not instance.received_by_id:
            instance.received_by = self.user
        if commit:
            instance.save()
        return instance


# ===================================================================
# MakePayment
# ===================================================================
class MakePaymentForm(BaseStyledForm):
    class Meta:
        model = MakePayment
        fields = [
            "source",
            "payment_type",
            "receiver_name",
            "amount",
            "reference",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["source"].queryset = (
            MoneySource.objects.filter(is_active=True).order_by("name")
        )
        self.fields["source"].empty_label = "— Select source —"

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is not None and amount <= 0:
            raise ValidationError("Amount must be greater than zero.")
        return amount

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("source")
        amount = cleaned.get("amount")
        if source and amount and amount > source.balance:
            raise ValidationError(
                {
                    "amount": (
                        f"Insufficient balance. Available: "
                        f"{source.balance} {source.currency}"
                    )
                }
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user and not instance.paid_by_id:
            instance.paid_by = self.user
        if commit:
            instance.save()
        return instance


# ===================================================================
# Transfer  ← NEW
# ===================================================================
class TransferForm(BaseStyledForm):
    """
    Form for moving money between two MoneySources.

    On submit, the view calls services.transfer_money() so both
    balances update and both ledger legs are written atomically.
    """

    class Meta:
        model = Transfer
        fields = [
            "from_source",
            "to_source",
            "amount",
            "reference",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        active = MoneySource.objects.filter(is_active=True).order_by("name")
        self.fields["from_source"].queryset = active
        self.fields["to_source"].queryset = active
        self.fields["from_source"].empty_label = "— Select source —"
        self.fields["to_source"].empty_label = "— Select destination —"

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is not None and amount <= 0:
            raise ValidationError("Amount must be greater than zero.")
        return amount

    def clean(self):
        cleaned = super().clean()
        src = cleaned.get("from_source")
        dst = cleaned.get("to_source")
        amount = cleaned.get("amount")

        if src and dst and src.pk == dst.pk:
            raise ValidationError("Source and destination must be different.")

        if src and amount is not None and amount > src.balance:
            raise ValidationError(
                {
                    "amount": (
                        f"Insufficient balance in {src.name}. "
                        f"Available: {src.balance} {src.currency}"
                    )
                }
            )
        return cleaned

    def save(self, commit=True):
        # NOTE: TransferCreateView calls services.transfer_money()
        # directly and does NOT call form.save(). This save() exists
        # only for admin/API use where the service isn't invoked.
        instance = super().save(commit=False)
        if self.user and not instance.created_by_id:
            instance.created_by = self.user
        if commit:
            instance.save()
        return instance


# ===================================================================
# FinancialTransaction (admin/debug only — do not use in views)
# ===================================================================
class FinancialTransactionForm(BaseStyledForm):
    class Meta:
        model = FinancialTransaction
        fields = "__all__"


# ===================================================================
# Filter form (transactions list)
# ===================================================================
class TransactionFilterForm(forms.Form):
    source = forms.ModelChoiceField(
        queryset=MoneySource.objects.all(),
        required=False,
        empty_label="All sources",
    )
    transaction_type = forms.ChoiceField(
        choices=[("", "All types")] + list(FinancialTransaction.TRANSACTION_TYPES),
        required=False,
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-input"
            )
            field.widget.attrs["class"] = css