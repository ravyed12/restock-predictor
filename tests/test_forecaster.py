"""Unit tests for the EMA/SMA forecaster."""

import sys
import os
from datetime import datetime, timedelta

# Ensure backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.forecaster import (
    compute_predictions,
    _compute_intervals,
    _compute_sma,
    _compute_ema,
    _determine_confidence,
    EMA_ALPHA,
)


def test_compute_intervals() -> None:
    """Test that inter-purchase intervals are computed correctly."""
    dates = [
        datetime(2025, 1, 1),
        datetime(2025, 1, 8),   # 7 days later
        datetime(2025, 1, 22),  # 14 days later
    ]
    intervals = _compute_intervals(dates)
    assert len(intervals) == 2
    assert abs(intervals[0] - 7.0) < 0.01, f"Expected ~7, got {intervals[0]}"
    assert abs(intervals[1] - 14.0) < 0.01, f"Expected ~14, got {intervals[1]}"
    print("✓ test_compute_intervals passed")


def test_compute_intervals_same_day() -> None:
    """Test that same-day purchases clamp to 0.5 days minimum."""
    dates = [
        datetime(2025, 1, 1, 10, 0),
        datetime(2025, 1, 1, 14, 0),  # same day, 4 hours later
    ]
    intervals = _compute_intervals(dates)
    assert len(intervals) == 1
    assert intervals[0] >= 0.5, f"Same-day interval should be ≥0.5, got {intervals[0]}"
    print("✓ test_compute_intervals_same_day passed")


def test_compute_sma() -> None:
    """Test SMA calculation over a window of 3."""
    intervals = [7.0, 14.0, 10.0, 8.0]
    sma = _compute_sma(intervals)
    # Should use last 3: [14, 10, 8] → avg = 10.67
    expected = (14.0 + 10.0 + 8.0) / 3
    assert abs(sma - expected) < 0.01, f"Expected {expected}, got {sma}"
    print("✓ test_compute_sma passed")


def test_compute_sma_fewer_than_window() -> None:
    """Test SMA with fewer intervals than the window size."""
    intervals = [7.0, 14.0]
    sma = _compute_sma(intervals)
    expected = (7.0 + 14.0) / 2
    assert abs(sma - expected) < 0.01, f"Expected {expected}, got {sma}"
    print("✓ test_compute_sma_fewer_than_window passed")


def test_compute_ema() -> None:
    """Test EMA calculation with α = 0.3."""
    intervals = [10.0, 14.0, 8.0]
    ema = _compute_ema(intervals)

    # Manual: EMA_0 = 10
    #         EMA_1 = 0.3 * 14 + 0.7 * 10 = 4.2 + 7.0 = 11.2
    #         EMA_2 = 0.3 * 8  + 0.7 * 11.2 = 2.4 + 7.84 = 10.24
    expected = 10.24
    assert abs(ema - expected) < 0.01, f"Expected {expected}, got {ema}"
    print("✓ test_compute_ema passed")


def test_determine_confidence() -> None:
    """Test confidence level assignment."""
    assert _determine_confidence(1) == "low"
    assert _determine_confidence(2) == "low"
    assert _determine_confidence(3) == "medium"
    assert _determine_confidence(4) == "medium"
    assert _determine_confidence(5) == "high"
    assert _determine_confidence(20) == "high"
    print("✓ test_determine_confidence passed")


def test_compute_predictions_single_purchase() -> None:
    """Test prediction with only 1 purchase (default 30-day interval)."""
    now = datetime.now()
    history = {"item-001": [now]}
    preds = compute_predictions(history)

    assert len(preds) == 1
    p = preds[0]
    assert p.item_id == "item-001"
    assert p.confidence == "low"
    assert p.avg_interval_days == 30.0
    assert p.ema_interval_days == 30.0
    assert p.predicted_restock_date == (now + timedelta(days=30)).date()
    print("✓ test_compute_predictions_single_purchase passed")


def test_compute_predictions_multiple_purchases() -> None:
    """Test prediction with 5 purchases (high confidence)."""
    base = datetime(2025, 1, 1)
    dates = [base + timedelta(days=i * 7) for i in range(5)]
    # All intervals are exactly 7 days

    history = {"item-002": dates}
    preds = compute_predictions(history)

    assert len(preds) == 1
    p = preds[0]
    assert p.item_id == "item-002"
    assert p.confidence == "high"
    assert p.times_purchased == 5
    assert abs(p.avg_interval_days - 7.0) < 0.1
    assert abs(p.ema_interval_days - 7.0) < 0.1
    assert p.predicted_restock_date == (dates[-1] + timedelta(days=7)).date()
    print("✓ test_compute_predictions_multiple_purchases passed")


def test_compute_predictions_empty() -> None:
    """Test that empty history returns no predictions."""
    preds = compute_predictions({})
    assert preds == []
    preds2 = compute_predictions({"item-x": []})
    assert preds2 == []
    print("✓ test_compute_predictions_empty passed")


if __name__ == "__main__":
    test_compute_intervals()
    test_compute_intervals_same_day()
    test_compute_sma()
    test_compute_sma_fewer_than_window()
    test_compute_ema()
    test_determine_confidence()
    test_compute_predictions_single_purchase()
    test_compute_predictions_multiple_purchases()
    test_compute_predictions_empty()
    print("\n✅ All forecaster tests passed!")
