"""Visible checks — the suite the loop could see and optimized against.

Covers criterion 2 (typed rejection of malformed input) and the happy-path
discount tiers. It deliberately does NOT touch the two repaired branches
(zero-quantity, negative base price) — those are exercised only by the withheld
probes in ``test_holdout.py``, so the visible suite maps to the pre-repair
coverage state the RUNLOG describes.
"""

import unittest

import pricing


class ParseRequestRejection(unittest.TestCase):
    def test_non_mapping_rejected(self):
        with self.assertRaises(pricing.PricingError):
            pricing.parse_request(["unit_price", 10])

    def test_missing_key_rejected(self):
        with self.assertRaises(pricing.PricingError):
            pricing.parse_request({"unit_price": 10.0})

    def test_non_int_quantity_rejected(self):
        with self.assertRaises(pricing.PricingError):
            pricing.parse_request({"unit_price": 10.0, "quantity": "5"})

    def test_bool_quantity_rejected(self):
        with self.assertRaises(pricing.PricingError):
            pricing.parse_request({"unit_price": 10.0, "quantity": True})

    def test_non_numeric_price_rejected(self):
        with self.assertRaises(pricing.PricingError):
            pricing.parse_request({"unit_price": "cheap", "quantity": 5})

    def test_negative_price_rejected(self):
        with self.assertRaises(pricing.PricingError):
            pricing.parse_request({"unit_price": -1.0, "quantity": 5})

    def test_negative_quantity_rejected(self):
        with self.assertRaises(pricing.PricingError):
            pricing.parse_request({"unit_price": 10.0, "quantity": -3})

    def test_valid_request_parses(self):
        self.assertEqual(
            pricing.parse_request({"unit_price": 10, "quantity": 5}), (10.0, 5)
        )


class DiscountHappyPath(unittest.TestCase):
    def test_no_discount_below_ten(self):
        self.assertEqual(pricing.quote({"unit_price": 10.0, "quantity": 5}), 50.0)

    def test_ten_percent_at_ten(self):
        self.assertEqual(pricing.quote({"unit_price": 2.0, "quantity": 10}), 18.0)

    def test_twenty_percent_at_hundred(self):
        self.assertEqual(pricing.quote({"unit_price": 1.0, "quantity": 100}), 80.0)


if __name__ == "__main__":
    unittest.main()
