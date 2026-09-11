"""Blinkit order-confirmation email parser.

Connects to Gmail via IMAP, fetches Blinkit order emails, and extracts
structured order data (items, quantities, prices) from the HTML body.

Blinkit email characteristics (verified pattern):
  - Sender: noreply@blinkit.com or support@blinkit.com
  - Subject: contains "order" and/or "delivered" with order ID
  - Body: HTML table with item rows containing name, qty, price
"""

from __future__ import annotations

import email
import imaplib
import logging
import os
import re
from datetime import datetime
from email.header import decode_header
from typing import Optional

from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from backend.parsers.base import EmailParser, ParsedItem, ParsedOrder

logger = logging.getLogger(__name__)


class BlinkitParser(EmailParser):
    """Parser for Blinkit (Zomato) order-confirmation emails."""

    PLATFORM = "blinkit"
    SENDER_ADDRESSES = [
        "noreply@blinkit.com",
        "support@blinkit.com",
        "no-reply@blinkit.com",
        "noreply@grofers.com",       # legacy Grofers addresses
        "support@grofers.com",
    ]
    SUBJECT_PATTERNS = [
        r"order\s*(#|id|no)?[\s:]*\w+",
        r"order\s+confirmed",
        r"order\s+delivered",
        r"delivery\s+confirmed",
    ]

    def __init__(self) -> None:
        self._gmail_address: str = os.environ["GMAIL_ADDRESS"]
        self._gmail_password: str = os.environ["GMAIL_APP_PASSWORD"]

    def fetch_emails(self, since_date: Optional[str] = None,
                     lookback_days: int = 90) -> list[ParsedOrder]:
        """Fetch and parse Blinkit order emails from Gmail.

        Args:
            since_date: ISO date string (YYYY-MM-DD). If provided, fetch
                        emails after this date. Overrides lookback_days.
            lookback_days: Number of days to look back if since_date is None.

        Returns:
            List of successfully parsed orders, newest first.
        """
        orders: list[ParsedOrder] = []

        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(self._gmail_address, self._gmail_password)
            mail.select("INBOX", readonly=True)
        except imaplib.IMAP4.error as e:
            logger.error("IMAP login failed: %s", e)
            raise

        try:
            search_criteria = self._build_search_criteria(since_date, lookback_days)
            logger.info("IMAP search: %s", search_criteria)

            status, message_ids = mail.search(None, search_criteria)
            if status != "OK" or not message_ids[0]:
                logger.info("No matching emails found")
                return orders

            id_list = message_ids[0].split()
            logger.info("Found %d candidate emails", len(id_list))

            for msg_id in id_list:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK" or not msg_data[0]:
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Check sender
                sender = msg.get("From", "").lower()
                if not any(addr in sender for addr in self.SENDER_ADDRESSES):
                    continue

                # Get subject
                subject = self._decode_header(msg.get("Subject", ""))

                # Get message ID for dedup
                message_id = msg.get("Message-ID", "").strip()
                if not message_id:
                    message_id = f"blinkit-{msg_id.decode()}-{hash(subject)}"

                # Extract HTML body
                html_body = self._get_html_body(msg)
                if not html_body:
                    logger.debug("No HTML body in email: %s", subject)
                    continue

                # Parse the order
                parsed = self.parse_email_body(html_body, subject, message_id)
                if parsed:
                    orders.append(parsed)
                    logger.info("Parsed order: %s (%d items)",
                                subject[:60], len(parsed.items))
                else:
                    logger.warning("Could not parse email: %s", subject[:80])

        finally:
            mail.logout()

        # Newest first
        orders.sort(key=lambda o: o.order_date, reverse=True)
        return orders

    def parse_email_body(self, html_body: str, subject: str,
                         message_id: str) -> ParsedOrder | None:
        """Parse a Blinkit order-confirmation HTML body.

        Args:
            html_body: Raw HTML content of the email.
            subject:   Email subject line.
            message_id: IMAP Message-ID for dedup.

        Returns:
            ParsedOrder with items extracted, or None if unparseable.
        """
        soup = BeautifulSoup(html_body, "html.parser")

        # --- Extract order date ---
        order_date = self._extract_order_date(soup, subject)
        if not order_date:
            logger.debug("Could not extract order date from: %s", subject[:60])
            return None

        # --- Extract items ---
        items = self._extract_items(soup)
        if not items:
            logger.debug("No items extracted from: %s", subject[:60])
            return None

        # --- Extract total ---
        total_amount = self._extract_total(soup)

        return ParsedOrder(
            platform=self.PLATFORM,
            order_date=order_date,
            email_subject=subject,
            email_message_id=message_id,
            total_amount=total_amount,
            items=items,
        )

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _build_search_criteria(self, since_date: Optional[str],
                                lookback_days: int) -> str:
        """Build an IMAP SEARCH query string.

        Args:
            since_date:    ISO date to search from (takes priority).
            lookback_days: Fallback lookback window in days.

        Returns:
            IMAP-compatible search criteria string.
        """
        from datetime import timedelta

        if since_date:
            dt = dateutil_parser.parse(since_date)
        else:
            dt = datetime.now() - timedelta(days=lookback_days)

        # IMAP date format: DD-Mon-YYYY
        imap_date = dt.strftime("%d-%b-%Y")

        # Search for emails from any known Blinkit sender
        # IMAP OR is binary, so we chain: (OR (FROM a) (OR (FROM b) (FROM c)))
        senders = self.SENDER_ADDRESSES
        if len(senders) == 1:
            sender_clause = f'FROM "{senders[0]}"'
        else:
            # Build nested OR tree
            sender_clause = f'FROM "{senders[-1]}"'
            for addr in reversed(senders[:-1]):
                sender_clause = f'OR FROM "{addr}" {sender_clause}'

        return f'({sender_clause} SINCE {imap_date})'

    @staticmethod
    def _decode_header(header_value: str) -> str:
        """Decode a possibly-encoded email header into a plain string.

        Args:
            header_value: Raw header value from email.

        Returns:
            Decoded UTF-8 string.
        """
        if not header_value:
            return ""
        parts = decode_header(header_value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return " ".join(decoded)

    @staticmethod
    def _get_html_body(msg: email.message.Message) -> Optional[str]:
        """Extract the HTML body from an email message.

        Args:
            msg: Parsed email Message object.

        Returns:
            HTML string, or None if no HTML part found.
        """
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/html":
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        else:
            if msg.get_content_type() == "text/html":
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return None

    def _extract_order_date(self, soup: BeautifulSoup,
                            subject: str) -> Optional[datetime]:
        """Try multiple strategies to extract the order date.

        Args:
            soup:    Parsed HTML of the email body.
            subject: Email subject line (used as fallback).

        Returns:
            Datetime of the order, or None if extraction fails.
        """
        # Strategy 1: Look for date patterns in the HTML text
        text = soup.get_text(separator=" ", strip=True)
        date_patterns = [
            # "Ordered on 12 Sep 2025" / "Delivered on Sep 12, 2025"
            r"(?:ordered|delivered|placed)\s+on\s+(\d{1,2}\s+\w+\s+\d{4})",
            r"(?:ordered|delivered|placed)\s+on\s+(\w+\s+\d{1,2},?\s+\d{4})",
            # "12/09/2025" or "2025-09-12"
            r"(\d{1,2}/\d{1,2}/\d{4})",
            r"(\d{4}-\d{2}-\d{2})",
            # "12 Sep, 2025"
            r"(\d{1,2}\s+\w{3,9},?\s+\d{4})",
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return dateutil_parser.parse(match.group(1), fuzzy=True)
                except (ValueError, OverflowError):
                    continue

        # Strategy 2: Try subject line
        for pattern in date_patterns:
            match = re.search(pattern, subject, re.IGNORECASE)
            if match:
                try:
                    return dateutil_parser.parse(match.group(1), fuzzy=True)
                except (ValueError, OverflowError):
                    continue

        # Strategy 3: "Date" header fallback — will be set by _extract_from_header
        return None

    def _extract_items(self, soup: BeautifulSoup) -> list[ParsedItem]:
        """Extract line items from the Blinkit order email HTML.

        Uses multiple strategies to handle format variations:
        1. HTML table rows with item data
        2. Structured divs/spans with item info
        3. Regex fallback on visible text

        Args:
            soup: Parsed HTML of the email body.

        Returns:
            List of parsed items (may be empty).
        """
        items: list[ParsedItem] = []

        # Strategy 1: Look for table-based layouts (common in Blinkit)
        # Blinkit typically uses tables where each item row has:
        #   - Item name (often in a <td> or <span>)
        #   - Quantity (e.g., "x2", "Qty: 2")
        #   - Price (e.g., "₹49", "Rs. 49.00")
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    row_text = row.get_text(separator=" ", strip=True)
                    item = self._try_parse_item_text(row_text)
                    if item:
                        items.append(item)

        if items:
            return self._deduplicate_items(items)

        # Strategy 2: Look for div-based layouts
        text_blocks = soup.find_all(["div", "span", "p"])
        for block in text_blocks:
            block_text = block.get_text(separator=" ", strip=True)
            # Only consider blocks that look like item lines (have a price)
            if re.search(r"[₹Rs]\s*\.?\s*\d+", block_text):
                item = self._try_parse_item_text(block_text)
                if item:
                    items.append(item)

        if items:
            return self._deduplicate_items(items)

        # Strategy 3: Full text regex fallback
        full_text = soup.get_text(separator="\n", strip=True)
        for line in full_text.split("\n"):
            if re.search(r"[₹Rs]\s*\.?\s*\d+", line):
                item = self._try_parse_item_text(line)
                if item:
                    items.append(item)

        return self._deduplicate_items(items)

    def _try_parse_item_text(self, text: str) -> Optional[ParsedItem]:
        """Attempt to parse an item name, quantity, and price from text.

        Args:
            text: A line/block of text that may contain item info.

        Returns:
            ParsedItem if successfully parsed, None otherwise.
        """
        text = re.sub(r"\s+", " ", text).strip()

        # Skip header-like rows, totals, delivery charges, etc.
        skip_keywords = [
            "total", "subtotal", "delivery", "discount", "coupon",
            "handling", "gst", "tax", "charges", "fee", "savings",
            "you saved", "order id", "order no", "payment",
        ]
        text_lower = text.lower()
        if any(kw in text_lower for kw in skip_keywords):
            return None

        # Extract price: ₹49, Rs.49, ₹ 49.00, Rs 49
        price_match = re.search(
            r"[₹][\s]*(\d+(?:\.\d{1,2})?)|Rs\.?\s*(\d+(?:\.\d{1,2})?)",
            text
        )
        if not price_match:
            return None

        price_str = price_match.group(1) or price_match.group(2)
        try:
            unit_price = float(price_str)
        except ValueError:
            return None

        # Skip very small or very large prices (likely not item prices)
        if unit_price < 1 or unit_price > 10000:
            return None

        # Extract quantity: "x2", "x 2", "Qty: 2", "Qty 2", "× 2"
        qty_match = re.search(
            r"(?:x|×|qty[:\s]*)\s*(\d+)", text, re.IGNORECASE
        )
        quantity = int(qty_match.group(1)) if qty_match else 1

        # Item name: everything before the price/qty, cleaned up
        # Remove price and qty from text to isolate the name
        name = text
        name = re.sub(
            r"[₹][\s]*\d+(?:\.\d{1,2})?|Rs\.?\s*\d+(?:\.\d{1,2})?",
            "", name
        )
        name = re.sub(r"(?:x|×|qty[:\s]*)\s*\d+", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\s+", " ", name).strip(" -·|")

        # Skip if name is too short or too long (likely noise)
        if len(name) < 3 or len(name) > 200:
            return None

        # Try to detect unit from name
        unit = "pcs"
        unit_patterns = {
            "kg": r"\d+\s*kg\b",
            "g": r"\d+\s*g\b",
            "ml": r"\d+\s*ml\b",
            "L": r"\d+\s*(?:l|ltr|litre)\b",
        }
        for u, pat in unit_patterns.items():
            if re.search(pat, name, re.IGNORECASE):
                unit = u
                break

        return ParsedItem(
            name=name,
            quantity=quantity,
            unit_price=unit_price,
            unit=unit,
        )

    @staticmethod
    def _deduplicate_items(items: list[ParsedItem]) -> list[ParsedItem]:
        """Remove duplicate items (same name), keeping the first occurrence.

        Args:
            items: List of parsed items, possibly with duplicates.

        Returns:
            De-duplicated list preserving original order.
        """
        seen: set[str] = set()
        unique: list[ParsedItem] = []
        for item in items:
            key = item.name.lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique

    def _extract_total(self, soup: BeautifulSoup) -> float:
        """Extract the order total amount from the email.

        Args:
            soup: Parsed HTML of the email body.

        Returns:
            Total amount as a float, or 0.0 if not found.
        """
        text = soup.get_text(separator=" ", strip=True)

        # Look for "Total: ₹XXX" or "Grand Total ₹XXX" etc.
        total_patterns = [
            r"(?:grand\s+)?total[:\s]*[₹Rs\.]*\s*(\d+(?:\.\d{1,2})?)",
            r"amount\s+paid[:\s]*[₹Rs\.]*\s*(\d+(?:\.\d{1,2})?)",
            r"bill\s+total[:\s]*[₹Rs\.]*\s*(\d+(?:\.\d{1,2})?)",
        ]

        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue

        return 0.0
