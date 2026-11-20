from decimal import Decimal

def invoice_total(amounts):
    """Return the rounded total of the line `amounts`."""
    # Convert amounts to Decimals to ensure precise arithmetic
    total = sum(Decimal(str(a)) for a in amounts)
    # Return as a float to maintain compatibility with existing API
    return float(total)
