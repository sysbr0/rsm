# financial/api_views.py
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    FinancialTransaction,
    MakePayment,
    MoneySource,
    ReceivePayment,
    Transfer,
)
from .serializers import (
    FinancialTransactionSerializer,
    MakePaymentSerializer,
    MoneySourceListSerializer,
    MoneySourceSerializer,
    ReceivePaymentSerializer,
    TransferSerializer,
)
from .services import make_payment, receive_money, transfer_money


# ===================================================================
# MoneySource
# ===================================================================
class MoneySourceViewSet(viewsets.ModelViewSet):
    """
    CRUD for MoneySource.

    Extra actions:
        GET /financial/api/sources/summary/
        GET /financial/api/sources/{id}/transactions/
    """

    queryset = MoneySource.objects.all()
    serializer_class = MoneySourceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "bank_name", "iban"]
    ordering_fields = ["name", "balance", "created_at"]

    def get_queryset(self):
        return MoneySource.objects.all().order_by("name")

    def get_serializer_class(self):
        if self.action == "list":
            return MoneySourceListSerializer
        return MoneySourceSerializer

    # ---------------------------------------------------------------
    # GET /financial/api/sources/summary/
    # ---------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        qs = MoneySource.objects.filter(is_active=True)
        total = qs.aggregate(total=Sum("balance"))["total"] or Decimal("0.00")
        return Response(
            {
                "total_balance": str(total),
                "currency": qs.first().currency if qs.exists() else "₺",
                "sources_count": qs.count(),
                "sources": MoneySourceListSerializer(qs, many=True).data,
            }
        )

    # ---------------------------------------------------------------
    # GET /financial/api/sources/{id}/transactions/
    # ---------------------------------------------------------------
    @action(detail=True, methods=["get"], url_path="transactions")
    def transactions(self, request, pk=None):
        source = self.get_object()
        qs = (
            source.financial_transactions
            .select_related("created_by")
            .order_by("-created_at")[:100]
        )
        return Response(FinancialTransactionSerializer(qs, many=True).data)


# ===================================================================
# ReceivePayment
# ===================================================================
class ReceivePaymentViewSet(viewsets.ModelViewSet):
    """
    Receive money into a source.

    Extra actions:
        None (create/list/retrieve only — no edit/delete).
    """

    queryset = ReceivePayment.objects.all()
    serializer_class = ReceivePaymentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["payer_name", "reference", "source__name"]
    ordering_fields = ["created_at", "amount"]

    def get_queryset(self):
        qs = (
            ReceivePayment.objects
            .select_related("source", "order", "received_by")
            .order_by("-created_at")
        )
        source = self.request.query_params.get("source")
        if source:
            qs = qs.filter(source_id=source)
        return qs

    # ---------------------------------------------------------------
    # POST /financial/api/receive-payments/
    # ---------------------------------------------------------------
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            receive_payment, _ = receive_money(
                source=data["source"],
                amount=data["amount"],
                received_by=request.user,
                order=data.get("order"),
                payer_name=data.get("payer_name"),
                reference=data.get("reference"),
                notes=data.get("notes"),
            )
        except ValidationError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            self.get_serializer(receive_payment).data,
            status=status.HTTP_201_CREATED,
        )

    # ---------------------------------------------------------------
    # Locked methods
    # ---------------------------------------------------------------
    def update(self, request, *args, **kwargs):
        return Response(
            {"detail": "Receive payments cannot be edited after creation."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "Financial payments cannot be deleted."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


# ===================================================================
# MakePayment
# ===================================================================
class MakePaymentViewSet(viewsets.ModelViewSet):
    """
    Pay money out of a source.

    Extra actions:
        None (create/list/retrieve only — no edit/delete).
    """

    queryset = MakePayment.objects.all()
    serializer_class = MakePaymentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["receiver_name", "reference", "source__name"]
    ordering_fields = ["created_at", "amount"]

    def get_queryset(self):
        qs = (
            MakePayment.objects
            .select_related("source", "paid_by")
            .order_by("-created_at")
        )
        source = self.request.query_params.get("source")
        if source:
            qs = qs.filter(source_id=source)
        ptype = self.request.query_params.get("payment_type")
        if ptype:
            qs = qs.filter(payment_type=ptype)
        return qs

    # ---------------------------------------------------------------
    # POST /financial/api/make-payments/
    # ---------------------------------------------------------------
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            payment, _ = make_payment(
                source=data["source"],
                amount=data["amount"],
                paid_by=request.user,
                payment_type=data.get("payment_type", "EXPENSE"),
                receiver_name=data["receiver_name"],
                reference=data.get("reference"),
                notes=data.get("notes"),
            )
        except ValidationError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            self.get_serializer(payment).data,
            status=status.HTTP_201_CREATED,
        )

    # ---------------------------------------------------------------
    # Locked methods
    # ---------------------------------------------------------------
    def update(self, request, *args, **kwargs):
        return Response(
            {"detail": "Make payments cannot be edited after creation."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "Financial payments cannot be deleted."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


# ===================================================================
# Transfer
# ===================================================================
class TransferViewSet(viewsets.ModelViewSet):
    """
    Move money between two MoneySources.

    Extra actions:
        None (create/list/retrieve only — no edit/delete).

    Filtering:
        ?source=<id>          → transfers involving that source
                                (either side)
    """

    queryset = Transfer.objects.all()
    serializer_class = TransferSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = [
        "from_source__name",
        "to_source__name",
        "reference",
        "notes",
    ]
    ordering_fields = ["created_at", "amount"]

    def get_queryset(self):
        qs = (
            Transfer.objects
            .select_related("from_source", "to_source", "created_by")
            .order_by("-created_at")
        )

        source = self.request.query_params.get("source")
        if source:
            qs = qs.filter(
                Q(from_source_id=source) | Q(to_source_id=source)
            )

        return qs

    # ---------------------------------------------------------------
    # POST /financial/api/transfers/
    # ---------------------------------------------------------------
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            transfer = transfer_money(
                from_source=data["from_source"],
                to_source=data["to_source"],
                amount=data["amount"],
                user=request.user,
                reference=data.get("reference"),
                notes=data.get("notes"),
            )
        except ValidationError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            self.get_serializer(transfer).data,
            status=status.HTTP_201_CREATED,
        )

    # ---------------------------------------------------------------
    # Locked methods
    # ---------------------------------------------------------------
    def update(self, request, *args, **kwargs):
        return Response(
            {"detail": "Transfers cannot be edited after creation."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "Transfers cannot be deleted. Reverse with a new transfer."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


# ===================================================================
# FinancialTransaction (read-only)
# ===================================================================
class FinancialTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only transaction history.

    Extra actions:
        GET /financial/api/transactions/stats/
        GET /financial/api/transactions/dashboard/
    """

    queryset = FinancialTransaction.objects.all()
    serializer_class = FinancialTransactionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["description", "source__name"]
    ordering_fields = ["created_at", "amount"]

    def get_queryset(self):
        qs = (
            FinancialTransaction.objects
            .select_related(
                "source",
                "receive_payment",
                "make_payment",
                "transfer",
                "created_by",
            )
            .order_by("-created_at")
        )

        source = self.request.query_params.get("source")
        if source:
            qs = qs.filter(source_id=source)

        ttype = self.request.query_params.get("transaction_type")
        if ttype:
            qs = qs.filter(transaction_type=ttype)

        date_from = self.request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = self.request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        return qs

    # ---------------------------------------------------------------
    # GET /financial/api/transactions/stats/
    # ---------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        qs = self.get_queryset()

        received = (
            qs.filter(transaction_type="RECEIVE")
            .aggregate(t=Sum("amount"))["t"]
            or Decimal("0.00")
        )
        paid = (
            qs.filter(transaction_type="PAYMENT")
            .aggregate(t=Sum("amount"))["t"]
            or Decimal("0.00")
        )
        transfer_out = (
            qs.filter(transaction_type="TRANSFER_OUT")
            .aggregate(t=Sum("amount"))["t"]
            or Decimal("0.00")
        )
        transfer_in = (
            qs.filter(transaction_type="TRANSFER_IN")
            .aggregate(t=Sum("amount"))["t"]
            or Decimal("0.00")
        )

        return Response(
            {
                "total_received": str(received),
                "total_paid": str(paid),
                "total_transferred_out": str(transfer_out),
                "total_transferred_in": str(transfer_in),
                "net": str(received - paid),
                "count": qs.count(),
            }
        )

    # ---------------------------------------------------------------
    # GET /financial/api/transactions/dashboard/
    # Used by templates/financial/dashboard.html
    # ---------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="dashboard")
    def dashboard(self, request):
        sources_qs = MoneySource.objects.filter(is_active=True).order_by("name")

        total_balance = (
            sources_qs.aggregate(t=Sum("balance"))["t"] or Decimal("0.00")
        )
        total_received = (
            ReceivePayment.objects.aggregate(t=Sum("amount"))["t"]
            or Decimal("0.00")
        )
        total_paid = (
            MakePayment.objects.aggregate(t=Sum("amount"))["t"]
            or Decimal("0.00")
        )
        total_transferred = (
            Transfer.objects.aggregate(t=Sum("amount"))["t"]
            or Decimal("0.00")
        )

        # Active sources with display labels
        sources = [
            {
                "id": s.id,
                "name": s.name,
                "source_type": s.source_type,
                "source_type_display": s.get_source_type_display(),
                "balance": str(s.balance),
                "currency": s.currency,
                "is_active": s.is_active,
            }
            for s in sources_qs
        ]

        # Latest 10 transactions
        recent = (
            FinancialTransaction.objects
            .select_related("source")
            .order_by("-created_at")[:10]
        )
        recent_data = [
            {
                "id": t.id,
                "transaction_type": t.transaction_type,
                "transaction_type_display": t.get_transaction_type_display(),
                "source_name": t.source.name,
                "description": t.description or "",
                "amount": str(t.amount),
                "signed_amount": str(t.signed_amount),
                "balance_after": str(t.balance_after),
                "currency": t.currency,
                "created_at": t.created_at.isoformat(),
            }
            for t in recent
        ]

        currency = sources[0]["currency"] if sources else "₺"

        return Response(
            {
                "total_balance": str(total_balance),
                "total_received": str(total_received),
                "total_paid": str(total_paid),
                "total_transferred": str(total_transferred),
                "net_flow": str(total_received - total_paid),
                "currency": currency,
                "sources_count": len(sources),
                "sources": sources,
                "recent_transactions": recent_data,
            }
        )