"""Sync orchestrator — entry point for GitHub Actions.

Pipeline:
  1. Fetch new Blinkit order emails via IMAP
  2. Upsert items into the `items` table
  3. Insert orders + order_items (skip duplicates via email_message_id)
  4. Compute SMA/EMA predictions
  5. Upsert predictions into the `predictions` table
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

from supabase import create_client, Client

from backend.parsers.blinkit import BlinkitParser
from backend.parsers.base import ParsedOrder
from backend.forecaster import compute_predictions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def get_supabase_client() -> Client:
    """Create a Supabase client using the service-role key.

    Returns:
        Authenticated Supabase client with full write access.

    Raises:
        RuntimeError: If required environment variables are missing.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY env vars"
        )
    return create_client(url, key)


def get_last_sync_date(client: Client) -> str | None:
    """Get the most recent order date from the database (high-water mark).

    Args:
        client: Supabase client.

    Returns:
        ISO date string of the latest order, or None if no orders exist.
    """
    result = (
        client.table("orders")
        .select("order_date")
        .order("order_date", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["order_date"][:10]  # "YYYY-MM-DD"
    return None


def upsert_items(client: Client, orders: list[ParsedOrder]) -> dict[str, str]:
    """Upsert all unique items from parsed orders into the items table.

    Args:
        client: Supabase client.
        orders: List of parsed orders containing items.

    Returns:
        Mapping of item_name (lowercase) → item_id (UUID).
    """
    # Collect unique items
    unique_items: dict[str, dict] = {}
    for order in orders:
        for item in order.items:
            key = item.name.lower().strip()
            if key not in unique_items:
                unique_items[key] = {
                    "name": item.name.strip(),
                    "unit": item.unit,
                }

    if not unique_items:
        return {}

    # Upsert — on conflict(name) do nothing (preserve existing)
    rows = list(unique_items.values())
    client.table("items").upsert(
        rows, on_conflict="name", ignore_duplicates=True
    ).execute()

    # Fetch back all items to get IDs
    result = client.table("items").select("id, name").execute()
    return {row["name"].lower().strip(): row["id"] for row in result.data}


def insert_orders(
    client: Client,
    orders: list[ParsedOrder],
    item_map: dict[str, str],
) -> int:
    """Insert new orders and their line items, skipping duplicates.

    Args:
        client:   Supabase client.
        orders:   List of parsed orders.
        item_map: Mapping of item_name (lowercase) → item_id.

    Returns:
        Number of new orders inserted.
    """
    # Get existing message IDs to skip duplicates
    existing = client.table("orders").select("email_message_id").execute()
    existing_ids: set[str] = {
        row["email_message_id"] for row in existing.data if row["email_message_id"]
    }

    inserted_count = 0

    for order in orders:
        if order.email_message_id in existing_ids:
            logger.debug("Skipping duplicate: %s", order.email_message_id)
            continue

        # Insert order
        order_row = {
            "platform": order.platform,
            "order_date": order.order_date.isoformat(),
            "email_subject": order.email_subject,
            "email_message_id": order.email_message_id,
            "total_amount": order.total_amount,
        }
        result = client.table("orders").insert(order_row).execute()
        order_id = result.data[0]["id"]

        # Insert order items
        order_item_rows = []
        for item in order.items:
            item_id = item_map.get(item.name.lower().strip())
            if not item_id:
                logger.warning("Item not found in map: %s", item.name)
                continue
            order_item_rows.append({
                "order_id": order_id,
                "item_id": item_id,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
            })

        if order_item_rows:
            client.table("order_items").insert(order_item_rows).execute()

        inserted_count += 1
        logger.info(
            "Inserted order %s with %d items",
            order.email_subject[:50], len(order_item_rows),
        )

    return inserted_count


def build_purchase_history(client: Client) -> dict[str, list[datetime]]:
    """Build per-item purchase history from the database.

    Args:
        client: Supabase client.

    Returns:
        Mapping of item_id → list of order datetimes.
    """
    result = (
        client.table("order_items")
        .select("item_id, orders!inner(order_date)")
        .execute()
    )

    history: dict[str, list[datetime]] = {}
    for row in result.data:
        item_id = row["item_id"]
        order_date_str = row["orders"]["order_date"]
        try:
            from dateutil import parser as dp
            dt = dp.parse(order_date_str)
        except (ValueError, TypeError):
            continue

        if item_id not in history:
            history[item_id] = []
        history[item_id].append(dt)

    return history


def upsert_predictions(client: Client, predictions: list) -> None:
    """Write prediction results to the predictions table.

    Args:
        client:      Supabase client.
        predictions: List of Prediction dataclass instances.
    """
    if not predictions:
        return

    rows = [
        {
            "item_id": p.item_id,
            "avg_interval_days": p.avg_interval_days,
            "ema_interval_days": p.ema_interval_days,
            "last_ordered": p.last_ordered.isoformat(),
            "predicted_restock_date": p.predicted_restock_date.isoformat(),
            "confidence": p.confidence,
            "times_purchased": p.times_purchased,
            "updated_at": datetime.utcnow().isoformat(),
        }
        for p in predictions
    ]

    client.table("predictions").upsert(
        rows, on_conflict="item_id"
    ).execute()

    logger.info("Upserted %d predictions", len(rows))


def main() -> None:
    """Run the full sync pipeline."""
    logger.info("=== Restock Predictor Sync Started ===")

    # 1. Initialize
    client = get_supabase_client()
    parser = BlinkitParser()

    # 2. Determine search window
    last_sync = get_last_sync_date(client)
    if last_sync:
        logger.info("Last sync: %s — fetching newer emails", last_sync)
    else:
        logger.info("First run — looking back 90 days")

    # 3. Fetch & parse emails
    orders = parser.fetch_emails(since_date=last_sync, lookback_days=90)
    logger.info("Parsed %d orders from email", len(orders))

    if not orders:
        logger.info("No new orders found — running predictions on existing data")
    else:
        # 4. Upsert items
        item_map = upsert_items(client, orders)
        logger.info("Item catalog: %d items", len(item_map))

        # 5. Insert orders
        new_count = insert_orders(client, orders, item_map)
        logger.info("Inserted %d new orders", new_count)

    # 6. Compute & store predictions (always, even if no new orders)
    history = build_purchase_history(client)
    predictions = compute_predictions(history)
    upsert_predictions(client, predictions)

    logger.info("=== Sync Complete: %d predictions updated ===", len(predictions))


if __name__ == "__main__":
    main()
