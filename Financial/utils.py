from decimal import Decimal

from django.conf import settings


def format_currency(amount):
    """
    Format an amount using the restaurant currency
    configured in settings.py.

    Example:
        1250 -> 1,250.00 ₺
    """

    if amount is None:
        amount = Decimal("0.00")

    amount = Decimal(str(amount))

    currency = getattr(
        settings,
        "CURRENCY",
        "₺",
    )

    return f"{amount:,.2f} {currency}"