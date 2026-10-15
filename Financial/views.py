# financial/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView

from .forms import (
    MakePaymentForm,
    MoneySourceForm,
    ReceivePaymentForm,
    TransferForm,
)
from .models import (
    MakePayment,
    MoneySource,
    ReceivePayment,
    Transfer,
)


# ===================================================================
# HTML SHELLS — data is fetched from the API by JavaScript
# ===================================================================

@login_required
def dashboard(request):
    """
    Renders the dashboard shell.

    Data source:  GET /financial/api/transactions/dashboard/
    """
    return render(request, "financial/dashboard.html")


@login_required
def source_list(request):
    """
    Renders the money sources list shell.

    Data source:  GET /financial/api/sources/
    """
    return render(request, "financial/source_list.html")


@login_required
def receive_list(request):
    """
    Renders the receive payments list shell.

    Data source:  GET /financial/api/receive-payments/
    """
    return render(request, "financial/receive_payment_list.html")


@login_required
def make_list(request):
    """
    Renders the make payments list shell.

    Data source:  GET /financial/api/make-payments/
    """
    return render(request, "financial/make_payment_list.html")


@login_required
def transaction_list(request):
    """
    Renders the transactions list shell.

    Data source:  GET /financial/api/transactions/
    """
    return render(request, "financial/transaction_list.html")


@login_required
def transfer_list(request):
    """
    Renders the transfers list shell.

    Data source:  GET /financial/api/transfers/
    """
    return render(request, "financial/transfer_list.html")


# ===================================================================
# FORM PAGES — still need Django forms for CSRF + validation UX
# ===================================================================

class MoneySourceCreateView(LoginRequiredMixin, CreateView):
    model = MoneySource
    form_class = MoneySourceForm
    template_name = "financial/money_source_form.html"
    success_url = reverse_lazy("financial:source_list")

    def form_valid(self, form):
        messages.success(self.request, "Money source created successfully.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Please fix the errors below.")
        return super().form_invalid(form)


class MoneySourceUpdateView(LoginRequiredMixin, UpdateView):
    model = MoneySource
    form_class = MoneySourceForm
    template_name = "financial/money_source_form.html"
    success_url = reverse_lazy("financial:source_list")

    def form_valid(self, form):
        messages.success(self.request, "Money source updated successfully.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Please fix the errors below.")
        return super().form_invalid(form)


class ReceivePaymentCreateView(LoginRequiredMixin, CreateView):
    """
    Form page only. On submit, the view calls services.receive_money()
    which is a transactional operation that also updates the balance
    and creates a FinancialTransaction.
    """

    model = ReceivePayment
    form_class = ReceivePaymentForm
    template_name = "financial/receive_payment_form.html"
    success_url = reverse_lazy("financial:receive_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        from .services import receive_money

        data = form.cleaned_data
        try:
            receive_money(
                source=data["source"],
                amount=data["amount"],
                received_by=self.request.user,
                order=data.get("order"),
                payer_name=data.get("payer_name"),
                reference=data.get("reference"),
                notes=data.get("notes"),
            )
        except Exception as exc:
            messages.error(self.request, f"Failed: {exc}")
            return self.form_invalid(form)

        messages.success(
            self.request,
            f"Received {data['amount']} {data['source'].currency} successfully.",
        )
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, "Please fix the errors below.")
        return super().form_invalid(form)


class MakePaymentCreateView(LoginRequiredMixin, CreateView):
    """
    Form page only. On submit, the view calls services.make_payment()
    which is a transactional operation that also updates the balance
    and creates a FinancialTransaction.
    """

    model = MakePayment
    form_class = MakePaymentForm
    template_name = "financial/make_payment_form.html"
    success_url = reverse_lazy("financial:make_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        from .services import make_payment

        data = form.cleaned_data
        try:
            make_payment(
                source=data["source"],
                amount=data["amount"],
                paid_by=self.request.user,
                payment_type=data.get("payment_type", "EXPENSE"),
                receiver_name=data["receiver_name"],
                reference=data.get("reference"),
                notes=data.get("notes"),
            )
        except Exception as exc:
            messages.error(self.request, f"Failed: {exc}")
            return self.form_invalid(form)

        messages.success(
            self.request,
            f"Paid {data['amount']} {data['source'].currency} successfully.",
        )
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, "Please fix the errors below.")
        return super().form_invalid(form)


class TransferCreateView(LoginRequiredMixin, CreateView):
    """
    Form page only. On submit, the view calls services.transfer_money()
    which atomically updates both balances and writes both ledger legs.
    """

    model = Transfer
    form_class = TransferForm
    template_name = "financial/transfer_form.html"
    success_url = reverse_lazy("financial:transfer_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        from .services import transfer_money

        data = form.cleaned_data
        try:
            transfer_money(
                from_source=data["from_source"],
                to_source=data["to_source"],
                amount=data["amount"],
                user=self.request.user,
                reference=data.get("reference"),
                notes=data.get("notes"),
            )
        except Exception as exc:
            messages.error(self.request, f"Failed: {exc}")
            return self.form_invalid(form)

        messages.success(
            self.request,
            f"Transferred {data['amount']} "
            f"{data['from_source'].currency} from "
            f"{data['from_source'].name} to {data['to_source'].name}.",
        )
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, "Please fix the errors below.")
        return super().form_invalid(form)