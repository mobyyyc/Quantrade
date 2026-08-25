from datetime import date, datetime, timezone
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.historical_market_backfill import (
    FREE_TRACK_HOLDOUT_END_DATE,
    FREE_TRACK_START_DATE,
    build_historical_market_chunks,
    calendar_quarters,
    historical_eod_available_at,
    validate_free_track_backfill_window,
)


class HistoricalMarketBackfillTests(unittest.TestCase):
    def test_market_availability_is_a_conservative_same_day_toronto_cutoff(self) -> None:
        self.assertEqual(
            historical_eod_available_at(date(2026, 8, 24)),
            datetime(2026, 8, 24, 22, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            historical_eod_available_at(date(2026, 1, 5)),
            datetime(2026, 1, 5, 23, 0, tzinfo=timezone.utc),
        )

    def test_calendar_quarters_are_contiguous_and_inclusive(self) -> None:
        ranges = calendar_quarters(date(2025, 2, 15), date(2025, 7, 2))
        self.assertEqual(
            tuple((value.start_date, value.end_date) for value in ranges),
            (
                (date(2025, 2, 15), date(2025, 3, 31)),
                (date(2025, 4, 1), date(2025, 6, 30)),
                (date(2025, 7, 1), date(2025, 7, 2)),
            ),
        )

    def test_chunk_plan_batches_symbols_quarterly_for_both_price_bases(self) -> None:
        chunks = build_historical_market_chunks(
            ["MSFT", "AAPL", "NVDA"], start_date=date(2025, 1, 1), end_date=date(2025, 4, 1), batch_size=2,
        )
        self.assertEqual(len(chunks), 8)
        self.assertEqual(chunks[0].symbols, ("AAPL", "MSFT"))
        self.assertEqual(chunks[0].adjustment_basis, "unadjusted")
        self.assertEqual(chunks[1].adjustment_basis, "split_adjusted")
        self.assertEqual(chunks[-1].start_date, date(2025, 4, 1))
        self.assertEqual(chunks[-1].end_date, date(2025, 4, 1))
        self.assertNotEqual(chunks[0].key, chunks[1].key)

    def test_free_track_rejects_the_unaudited_pre_2021_period(self) -> None:
        with self.assertRaisesRegex(ValueError, "begins on 2021-01-01"):
            validate_free_track_backfill_window(date(2020, 12, 31), FREE_TRACK_HOLDOUT_END_DATE)
        validate_free_track_backfill_window(FREE_TRACK_START_DATE, FREE_TRACK_HOLDOUT_END_DATE)


if __name__ == "__main__":
    unittest.main()
