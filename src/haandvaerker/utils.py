from decimal import Decimal


def to_decimal(v: float) -> Decimal:
    return Decimal(str(v))
