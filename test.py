class ShoppingCart:
    def __init__(self):
        self._items: dict[str, float] = {}
        self._discount_applied = False
        self._is_checked_out = False

    def add_item(self, name: str, price: float) -> None:
        # Add item to cart, but reject if already checked out
        if self._is_checked_out:
            print("Error: Cannot add item. Cart is already checked out.")
            return
        self._items[name] = price

    def apply_discount(self, code: str) -> bool:
        # If code is "SAVE10" and no discount applied yet and not checked out,
        # mark discount as applied and return True. Otherwise return False.
        # 1. Guard Clause: Catch all reasons why we CAN'T apply a code
        if self._discount_applied or self._is_checked_out or code != "SAVE10":
            print("Error: Discount could not be applied. Check code or cart status.")
            return False

        # 2. Success Path: If we got here, we know the code is valid and the cart is ready
        self._discount_applied = True
        return True

    def get_total(self) -> float:
        # Sum all item prices. If discount was applied, subtract 10%.
        if self._discount_applied:
            return 0.9 * (sum(self._items.values()))
        return sum(self._items.values())

    def checkout(self) -> None:
        # Mark cart as checked out (only if it has items and isn't already checked out)
        if len(self._items) < 1 or self._is_checked_out:
            print("Error: Checkout was unsuccessful. Check cart status")
            return
        self._is_checked_out = True


if __name__ == "__main__":
    cart = ShoppingCart()
    cart.add_item("Laptop", 999.99)
    cart.add_item("Mouse", 29.99)

    print(f"Total: ${cart.get_total():.2f}")  # 1029.98

    print(f"Discount: {str(cart.apply_discount('SAVE10')).lower()}")  # true
    print(f"Total: ${cart.get_total():.2f}")  # 926.98

    print(f"Discount: {str(cart.apply_discount('SAVE10')).lower()}")  # false

    cart.checkout()
    cart.add_item("Keyboard", 79.99)  # Should be rejected
    print(f"Total: ${cart.get_total():.2f}")  # 926.98
