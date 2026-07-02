"""Toy pricing module — the post-repair target of the coverage-repair example.

The narrative in ``../SPEC.md`` / ``../RUNLOG.md`` realized as runnable code:

  * criterion 2 — ``parse_request`` rejects malformed input (missing keys,
    non-numeric quantity, negative price) with a typed ``PricingError`` instead
    of leaking a bare ``KeyError`` / ``TypeError`` downstream.
  * criterion 1 — ``apply_discount`` gained a zero-quantity branch and a
    negative-price guard. Those two branches were the lines uncovered at 0.74;
    the held-out adversarial probes in ``test_holdout.py`` exercise exactly them,
    which is what lifted ``pricing.py`` coverage past the 0.80 gate after the
    repair.

Pure stdlib. No new third-party dependencies (a SPEC constraint).
"""

from __future__ import annotations


class PricingError(ValueError):
    """Raised when a pricing request is malformed or economically invalid."""


def parse_request(payload: dict) -> tuple[float, int]:
    """Validate a raw request dict into ``(unit_price, quantity)``.

    Rejects a non-mapping payload, missing keys, a non-integer quantity, a
    non-numeric price, and negatives — always with a typed ``PricingError``.
    """
    if not isinstance(payload, dict):
        raise PricingError("request must be a mapping")
    for key in ("unit_price", "quantity"):
        if key not in payload:
            raise PricingError(f"missing required key: {key}")
    unit_price = payload["unit_price"]
    quantity = payload["quantity"]
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise PricingError("quantity must be an int")
    if isinstance(unit_price, bool) or not isinstance(unit_price, (int, float)):
        raise PricingError("unit_price must be numeric")
    if unit_price < 0:
        raise PricingError("unit_price must not be negative")
    if quantity < 0:
        raise PricingError("quantity must not be negative")
    return float(unit_price), quantity


def apply_discount(base_price: float, quantity: int) -> float:
    """Volume-discount a line: ``base_price`` per unit, ``quantity`` units.

    The repair added the first two branches (previously uncovered at 0.74):
    """
    if quantity == 0:                       # zero-qty branch — was uncovered
        return base_price
    if base_price < 0:                      # negative-price guard — was uncovered
        raise PricingError("base_price must not be negative")
    subtotal = base_price * quantity
    if quantity >= 100:
        return round(subtotal * 0.80, 2)
    if quantity >= 10:
        return round(subtotal * 0.90, 2)
    return round(subtotal, 2)


def quote(payload: dict) -> float:
    """End-to-end: validate a request, then return its discounted total."""
    unit_price, quantity = parse_request(payload)
    return apply_discount(unit_price, quantity)
