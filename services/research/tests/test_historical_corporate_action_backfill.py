from datetime import date
import unittest

from quantrade_research.historical_corporate_action_backfill import build_historical_corporate_action_chunks


class HistoricalCorporateActionBackfillTests(unittest.TestCase):
    def test_plans_one_quarterly_action_chunk_per_symbol_batch(self) -> None:
        chunks = build_historical_corporate_action_chunks(
            ("AAPL", "MSFT", "NVDA"), start_date=date(2025, 1, 1), end_date=date(2025, 4, 1), batch_size=2,
        )
        self.assertEqual(len(chunks), 4)
        self.assertEqual(chunks[0].symbols, ("AAPL", "MSFT"))
        self.assertEqual(chunks[0].adjustment_basis, "unadjusted")
        self.assertEqual(chunks[-1].start_date, date(2025, 4, 1))


if __name__ == "__main__":
    unittest.main()
