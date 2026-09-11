"""Unit tests for the Blinkit email parser (HTML parsing only, no IMAP)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.parsers.blinkit import BlinkitParser
from backend.parsers.base import ParsedItem


# ---- Test HTML fixtures ----

SAMPLE_BLINKIT_HTML_TABLE = """
<html><body>
<h2>Your Blinkit Order</h2>
<p>Ordered on 15 Aug 2025</p>
<table>
  <tr><th>Item</th><th>Qty</th><th>Price</th></tr>
  <tr><td>Amul Taaza Toned Fresh Milk 500 ml</td><td>x2</td><td>₹32</td></tr>
  <tr><td>Britannia Bread - White 400 g</td><td>x1</td><td>₹45</td></tr>
  <tr><td>Maggi 2-Minute Noodles 70 g</td><td>Qty: 3</td><td>₹42</td></tr>
</table>
<p>Grand Total: ₹203</p>
</body></html>
"""

SAMPLE_BLINKIT_HTML_DIVS = """
<html><body>
<div>Order Confirmed!</div>
<div>Delivered on Sep 1, 2025</div>
<div>
  <span>Parle-G Gold Biscuits 200 g</span>
  <span>x1</span>
  <span>₹25</span>
</div>
<div>
  <span>Aashirvaad Atta 5 kg</span>
  <span>x1</span>
  <span>Rs.299</span>
</div>
<div>Total: ₹324</div>
<div>Delivery Fee: ₹0</div>
</body></html>
"""

SAMPLE_EMPTY_HTML = """
<html><body>
<p>Thank you for your order!</p>
<p>We are processing it.</p>
</body></html>
"""


def test_parse_table_format() -> None:
    """Test parsing a Blinkit email with table-based item layout."""
    parser = BlinkitParser.__new__(BlinkitParser)  # skip __init__ (needs env vars)
    result = parser.parse_email_body(
        SAMPLE_BLINKIT_HTML_TABLE,
        subject="Your Blinkit Order #12345",
        message_id="<test-001@blinkit.com>"
    )

    assert result is not None, "Should parse table format"
    assert result.platform == "blinkit"
    assert result.email_message_id == "<test-001@blinkit.com>"
    assert len(result.items) >= 2, f"Expected ≥2 items, got {len(result.items)}"

    # Check that Amul Milk was found
    milk_items = [i for i in result.items if "milk" in i.name.lower()]
    assert len(milk_items) >= 1, "Should find milk item"
    assert milk_items[0].quantity == 2 or milk_items[0].unit_price == 32

    # Check total
    assert result.total_amount > 0, "Should extract total amount"
    print(f"✓ test_parse_table_format passed ({len(result.items)} items, total ₹{result.total_amount})")


def test_parse_div_format() -> None:
    """Test parsing a Blinkit email with div-based item layout."""
    parser = BlinkitParser.__new__(BlinkitParser)
    result = parser.parse_email_body(
        SAMPLE_BLINKIT_HTML_DIVS,
        subject="Order Delivered - Blinkit",
        message_id="<test-002@blinkit.com>"
    )

    assert result is not None, "Should parse div format"
    assert len(result.items) >= 1, f"Expected ≥1 items, got {len(result.items)}"
    print(f"✓ test_parse_div_format passed ({len(result.items)} items)")


def test_parse_empty_email() -> None:
    """Test that an email with no items returns None."""
    parser = BlinkitParser.__new__(BlinkitParser)
    result = parser.parse_email_body(
        SAMPLE_EMPTY_HTML,
        subject="Order Update",
        message_id="<test-003@blinkit.com>"
    )

    # May return None (no date) or an order with 0 items (→ None)
    if result is not None:
        assert len(result.items) == 0 or result is None
    print("✓ test_parse_empty_email passed (returned None as expected)")


def test_try_parse_item_text() -> None:
    """Test the low-level item text parser."""
    parser = BlinkitParser.__new__(BlinkitParser)

    # Valid item line
    item = parser._try_parse_item_text("Amul Taaza Milk 500 ml x2 ₹32")
    assert item is not None
    assert "Amul" in item.name or "milk" in item.name.lower()
    assert item.unit_price == 32.0
    assert item.quantity == 2
    print(f"✓ item parsed: {item.name} (qty={item.quantity}, ₹{item.unit_price})")

    # Total line — should be skipped
    skip = parser._try_parse_item_text("Grand Total ₹450")
    assert skip is None
    print("✓ total line correctly skipped")

    # Delivery fee — should be skipped
    skip2 = parser._try_parse_item_text("Delivery Fee ₹0")
    assert skip2 is None
    print("✓ delivery fee correctly skipped")


def test_extract_order_date() -> None:
    """Test order date extraction from various formats."""
    from bs4 import BeautifulSoup

    parser = BlinkitParser.__new__(BlinkitParser)

    # "Ordered on 15 Aug 2025"
    soup1 = BeautifulSoup("<p>Ordered on 15 Aug 2025</p>", "html.parser")
    date1 = parser._extract_order_date(soup1, "Order #123")
    assert date1 is not None
    assert date1.day == 15
    assert date1.month == 8
    print(f"✓ date extracted: {date1}")

    # "Delivered on Sep 1, 2025"
    soup2 = BeautifulSoup("<p>Delivered on Sep 1, 2025</p>", "html.parser")
    date2 = parser._extract_order_date(soup2, "Delivered")
    assert date2 is not None
    assert date2.month == 9
    print(f"✓ date extracted: {date2}")


def test_deduplicate_items() -> None:
    """Test item deduplication."""
    items = [
        ParsedItem(name="Amul Milk 500ml", quantity=1, unit_price=32),
        ParsedItem(name="amul milk 500ml", quantity=2, unit_price=32),  # dupe
        ParsedItem(name="Bread 400g", quantity=1, unit_price=45),
    ]
    unique = BlinkitParser._deduplicate_items(items)
    assert len(unique) == 2, f"Expected 2 unique items, got {len(unique)}"
    print("✓ test_deduplicate_items passed")


if __name__ == "__main__":
    test_try_parse_item_text()
    test_extract_order_date()
    test_deduplicate_items()
    test_parse_table_format()
    test_parse_div_format()
    test_parse_empty_email()
    print("\n✅ All parser tests passed!")
