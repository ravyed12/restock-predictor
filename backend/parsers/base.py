"""Abstract base class for email parsers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ParsedItem:
    """A single line-item extracted from an order email."""
    name: str
    quantity: int
    unit_price: float
    unit: str = "pcs"


@dataclass
class ParsedOrder:
    """A complete order extracted from an order-confirmation email."""
    platform: str
    order_date: datetime
    email_subject: str
    email_message_id: str
    total_amount: float
    items: list[ParsedItem] = field(default_factory=list)


class EmailParser(ABC):
    """Base class for platform-specific email parsers.

    Subclasses implement `parse_email_body` to extract order data
    from the HTML body of a confirmation email. The IMAP connection
    and email-fetching logic lives in the base class.
    """

    PLATFORM: str = ""
    SENDER_ADDRESSES: list[str] = []
    SUBJECT_PATTERNS: list[str] = []

    @abstractmethod
    def parse_email_body(self, html_body: str, subject: str,
                         message_id: str) -> ParsedOrder | None:
        """Parse an HTML email body into a ParsedOrder.

        Args:
            html_body: The raw HTML content of the email.
            subject: The email subject line.
            message_id: The IMAP Message-ID header (used for dedup).

        Returns:
            A ParsedOrder if parsing succeeded, None if the email
            couldn't be parsed (logged as a warning, not an error).
        """
        ...
