from django.shortcuts import render

# Create your views here.
from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    FinancialTransaction,
    MakePayment,
    MoneySource,
    ReceivePayment,
)
from .serializers import (
    FinancialTransactionSerializer,
    MakePaymentSerializer,
    MoneySourceSerializer,
    ReceivePaymentSerializer,
)
from .services import (
    make_payment,
    receive_money,
)


class MoneySourceViewSet(viewsets.ModelViewSet):

    queryset = MoneySource.objects.all()
    serializer_class = MoneySourceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return MoneySource.objects.all().order_by("name")


class ReceivePaymentViewSet(viewsets.ModelViewSet):

    queryset = ReceivePayment.objects.all()
    serializer_class = ReceivePaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            ReceivePayment.objects
            .select_related(
                "source",
                "order",
                "received_by",
            )
            .order_by("-created_at")
        )

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        try:

            receive_payment, transaction = (
                receive_money(
                    source=data["source"],
                    amount=data["amount"],
                    received_by=request.user,
                    order=data.get("order"),
                    payer_name=data.get(
                        "payer_name"
                    ),
                    payment_method=data.get(
                        "payment_method",
                        "CASH",
                    ),
                    reference=data.get(
                        "reference"
                    ),
                    notes=data.get(
                        "notes"
                    ),
                )
            )

        except ValidationError as exc:

            return Response(
                {
                    "detail": exc.message
                    if hasattr(exc, "message")
                    else str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_serializer = (
            self.get_serializer(
                receive_payment
            )
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        return Response(
            {
                "detail": (
                    "Receive payments cannot be "
                    "edited after creation."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(
        self,
        request,
        *args,
        **kwargs,
    ):
        return Response(
            {
                "detail": (
                    "Receive payments cannot be "
                    "edited after creation."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(
        self,
        request,
        *args,
        **kwargs,
    ):
        return Response(
            {
                "detail": (
                    "Financial payments cannot be "
                    "deleted."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class MakePaymentViewSet(viewsets.ModelViewSet):

    queryset = MakePayment.objects.all()
    serializer_class = MakePaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            MakePayment.objects
            .select_related(
                "source",
                "paid_by",
            )
            .order_by("-created_at")
        )

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        try:

            payment, transaction = (
                make_payment(
                    source=data["source"],
                    amount=data["amount"],
                    paid_by=request.user,
                    payment_type=data.get(
                        "payment_type",
                        "EXPENSE",
                    ),
                    receiver_name=data[
                        "receiver_name"
                    ],
                    reference=data.get(
                        "reference"
                    ),
                    notes=data.get(
                        "notes"
                    ),
                )
            )

        except ValidationError as exc:

            return Response(
                {
                    "detail": exc.message
                    if hasattr(exc, "message")
                    else str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_serializer = (
            self.get_serializer(payment)
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        return Response(
            {
                "detail": (
                    "Make payments cannot be "
                    "edited after creation."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(
        self,
        request,
        *args,
        **kwargs,
    ):
        return Response(
            {
                "detail": (
                    "Make payments cannot be "
                    "edited after creation."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(
        self,
        request,
        *args,
        **kwargs,
    ):
        return Response(
            {
                "detail": (
                    "Financial payments cannot be "
                    "deleted."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class FinancialTransactionViewSet(
    viewsets.ReadOnlyModelViewSet
):

    queryset = FinancialTransaction.objects.all()
    serializer_class = FinancialTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        return (
            FinancialTransaction.objects
            .select_related(
                "source",
                "receive_payment",
                "make_payment",
                "created_by",
            )
            .order_by("-created_at")
        )