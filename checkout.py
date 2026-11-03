def calculate_discount(price, discount):
    """Return the final price after a percentage discount (0 through 100)."""
    if price < 0 or not 0 <= discount <= 100:
        raise ValueError("Price must be non-negative and discount between 0 and 100")
    return price * (1 - discount / 100)
