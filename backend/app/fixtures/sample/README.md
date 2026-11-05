# Deliberately buggy checkout

`calculate_discount(price, discount)` returns the final price after a percentage discount.
The price must be non-negative and discount must be between 0 and 100 inclusive.
Zero percent returns the original price, 20 percent of 100 returns 80, and 100 percent returns zero.
Invalid values must raise `ValueError`.

The implementation deliberately violates this contract. AutoRCA-X never edits this file.
The deterministic demo copies trusted fixture constants to a temporary directory and runs
regression tests before and after the proposed fix. These tests are not an arbitrary-code sandbox.
