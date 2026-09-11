"""Consumption forecaster using SMA and EMA.

Calculates inter-purchase intervals for each item and predicts
the next restock date using Exponential Moving Average.

Formulas:
  SMA   = (1/N) × Σ intervals[i]   for the last N intervals
  EMA_t = α × interval_t + (1 - α) × EMA_{t-1},  where α = 0.3
  predicted_restock_date = last_order_date + round(EMA)

Confidence levels:
  high   = ≥ 5 data points (purchases)
  medium = 3–4 data points
  low    = 1–2 data points
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

# EMA smoothing factor — higher α = more weight on recent intervals
EMA_ALPHA: float = 0.3

# Number of intervals used for SMA (or all available if fewer)
SMA_WINDOW: int = 3


@dataclass
class Prediction:
    """Forecasted restock info for a single item."""
    item_id: str
    avg_interval_days: float
    ema_interval_days: float
    last_ordered: datetime
    predicted_restock_date: date
    confidence: str           # "high", "medium", "low"
    times_purchased: int


def compute_predictions(
    purchase_history: dict[str, list[datetime]],
) -> list[Prediction]:
    """Compute restock predictions for all items.

    Args:
        purchase_history: Mapping of item_id → list of order dates
                          (need not be sorted; will be sorted internally).

    Returns:
        List of Prediction objects, one per item with ≥ 1 purchase.
    """
    predictions: list[Prediction] = []

    for item_id, dates in purchase_history.items():
        if not dates:
            continue

        sorted_dates = sorted(dates)
        times_purchased = len(sorted_dates)
        last_ordered = sorted_dates[-1]

        if times_purchased < 2:
            # Not enough data to compute intervals — use a default 30-day guess
            predictions.append(Prediction(
                item_id=item_id,
                avg_interval_days=30.0,
                ema_interval_days=30.0,
                last_ordered=last_ordered,
                predicted_restock_date=(last_ordered + timedelta(days=30)).date(),
                confidence="low",
                times_purchased=times_purchased,
            ))
            continue

        # Calculate inter-purchase intervals in days
        intervals = _compute_intervals(sorted_dates)

        sma = _compute_sma(intervals)
        ema = _compute_ema(intervals)
        confidence = _determine_confidence(times_purchased)

        predicted_date = (last_ordered + timedelta(days=round(ema))).date()

        predictions.append(Prediction(
            item_id=item_id,
            avg_interval_days=round(sma, 2),
            ema_interval_days=round(ema, 2),
            last_ordered=last_ordered,
            predicted_restock_date=predicted_date,
            confidence=confidence,
            times_purchased=times_purchased,
        ))

        logger.debug(
            "Item %s: %d purchases, SMA=%.1fd, EMA=%.1fd → restock %s (%s)",
            item_id, times_purchased, sma, ema, predicted_date, confidence,
        )

    return predictions


def _compute_intervals(sorted_dates: list[datetime]) -> list[float]:
    """Compute gaps (in days) between consecutive purchases.

    Args:
        sorted_dates: Chronologically sorted list of purchase datetimes.

    Returns:
        List of interval lengths in days.
    """
    intervals: list[float] = []
    for i in range(1, len(sorted_dates)):
        delta = sorted_dates[i] - sorted_dates[i - 1]
        days = delta.total_seconds() / 86400.0
        # Clamp minimum interval to 0.5 days (same-day re-orders)
        intervals.append(max(days, 0.5))
    return intervals


def _compute_sma(intervals: list[float]) -> float:
    """Simple Moving Average of the most recent N intervals.

    Formula: SMA = (1/N) × Σ intervals[i]  for the last SMA_WINDOW intervals

    Args:
        intervals: List of inter-purchase intervals in days.

    Returns:
        SMA value in days.
    """
    window = intervals[-SMA_WINDOW:] if len(intervals) > SMA_WINDOW else intervals
    return sum(window) / len(window)


def _compute_ema(intervals: list[float]) -> float:
    """Exponential Moving Average over all intervals.

    Formula: EMA_t = α × interval_t + (1 - α) × EMA_{t-1}
             where α = EMA_ALPHA (0.3)

    Initialized with the first interval value.

    Args:
        intervals: List of inter-purchase intervals in days.

    Returns:
        EMA value in days.
    """
    ema = intervals[0]
    for interval in intervals[1:]:
        ema = EMA_ALPHA * interval + (1 - EMA_ALPHA) * ema
    return ema


def _determine_confidence(times_purchased: int) -> str:
    """Map purchase count to a confidence label.

    Args:
        times_purchased: Total number of times the item was ordered.

    Returns:
        "high" (≥5), "medium" (3-4), or "low" (1-2).
    """
    if times_purchased >= 5:
        return "high"
    elif times_purchased >= 3:
        return "medium"
    else:
        return "low"
