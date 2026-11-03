BUGGY = '''def calculate_discount(price, discount):
    """Return the final price after a percentage discount (0 through 100)."""
    return price / discount
'''

FIXED = '''def calculate_discount(price, discount):
    """Return the final price after a percentage discount (0 through 100)."""
    if price < 0 or not 0 <= discount <= 100:
        raise ValueError("Price must be non-negative and discount between 0 and 100")
    return price * (1 - discount / 100)
'''

SAMPLE_LOG = '''2026-01-15T10:42:31Z ERROR checkout.payment Payment calculation failed
Traceback (most recent call last):
  File "checkout.py", line 3, in calculate_discount
    return price / discount
ZeroDivisionError: division by zero
request_context: price=100, discount=0
'''

# Only these immutable, application-owned strings may be executed on the host.
REGRESSION_TEST = '''import unittest
from checkout import calculate_discount

class DiscountTests(unittest.TestCase):
    def test_zero_discount(self):
        self.assertEqual(calculate_discount(100, 0), 100)

    def test_percentage_discount(self):
        self.assertEqual(calculate_discount(100, 20), 80)

    def test_full_discount(self):
        self.assertEqual(calculate_discount(100, 100), 0)

    def test_invalid_inputs(self):
        for price, discount in [(-1, 0), (100, -1), (100, 101)]:
            with self.assertRaises(ValueError):
                calculate_discount(price, discount)

if __name__ == "__main__":
    unittest.main(verbosity=2)
'''
