# financial/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api_views, views

app_name = "financial"


# -------------------------------------------------------------------
# API Router
# -------------------------------------------------------------------
router = DefaultRouter()
router.register("sources", api_views.MoneySourceViewSet, basename="source")
router.register(
    "receive-payments",
    api_views.ReceivePaymentViewSet,
    basename="receive-payment",
)
router.register(
    "make-payments",
    api_views.MakePaymentViewSet,
    basename="make-payment",
)
router.register(
    "transactions",
    api_views.FinancialTransactionViewSet,
    basename="transaction",
)


# -------------------------------------------------------------------
# URL Patterns
# -------------------------------------------------------------------
urlpatterns = [
    # ---------------- HTML Views ----------------
    path("", views.dashboard, name="dashboard"),

    # Money Sources
    path("sources/", views.source_list, name="source_list"),
    path("sources/add/", views.MoneySourceCreateView.as_view(), name="source_add"),
    path(
        "sources/<int:pk>/edit/",
        views.MoneySourceUpdateView.as_view(),
        name="source_edit",
    ),

    # Receive Payments
    path(
        "receive-payments/",
        views.receive_list,
        name="receive_list",
    ),
    path(
        "receive-payments/add/",
        views.ReceivePaymentCreateView.as_view(),
        name="receive_add",
    ),

    # Make Payments
    path(
        "make-payments/",
        views.make_list,
        name="make_list",
    ),
    path(
        "make-payments/add/",
        views.MakePaymentCreateView.as_view(),
        name="make_add",
    ),

    # Transactions
    path(
        "transactions/",
        views.transaction_list,
        name="transaction_list",
    ),

    # ---------------- REST API ----------------
    path("api/", include(router.urls)),
]