import unittest
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
