"""Invoice reporting."""
from decimal import Decimal


def invoice_total(amounts):
    """Return the total of the line `amounts` using precise decimal arithmetic."""
    # Convert each amount to string first to avoid floating point inaccuracies during Decimal conversion
    total = sum(Decimal(str(amount)) for amount in amounts)
    return float(total)
