"""Held-out probes — withheld from the loop, run only at terminal verification.

These are the adversarial checks the flywheel promoted into the permanent
regression set: they exercise the exact two branches the repair added
(zero-quantity, negative base price). Passing them alongside the visible suite
is what makes ``false_completion: false`` a *measured* result rather than a
claim — a loop that overfit the visible tests would fail here.
"""

import unittest

import pricing


class ZeroQuantityBranch(unittest.TestCase):
    def test_zero_quantity_returns_base_price(self):
        # The repaired qty==0 branch (pricing.apply_discount).
        self.assertEqual(pricing.apply_discount(42.0, 0), 42.0)

    def test_zero_quantity_quote(self):
        self.assertEqual(pricing.quote({"unit_price": 42.0, "quantity": 0}), 42.0)


class NegativeBasePriceBranch(unittest.TestCase):
    def test_negative_base_price_raises(self):
        # The repaired base_price<0 guard (reached only when quantity != 0).
        with self.assertRaises(pricing.PricingError):
            pricing.apply_discount(-1.0, 5)


if __name__ == "__main__":
    unittest.main()
