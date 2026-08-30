from datetime import date, datetime
import math
import unittest
from zoneinfo import ZoneInfo

from quantrade_research.phase_9c_model_comparison import (
    ActiveFact,
    Example,
    _active_fundamentals,
    _tie_percentiles,
    fit_pairwise,
    fit_ridge,
    spearman,
)


def example(month: int, index: int) -> Example:
    value = (index - 10) / 10
    return Example(
        date(2023, month, 3), f"2023-{month:02d}", f"security-{index:02d}",
        value, value / 10, 1 / 20, (value, value / 2, -value, value, value / 3, value / 4),
        f"hash-{month}-{index}",
    )


class Phase9CModelComparisonTests(unittest.TestCase):
    def test_tie_percentiles_match_deployed_orientation(self) -> None:
        values = (("a", 1.0), ("b", 2.0), ("c", 2.0), ("d", 4.0))
        higher = _tie_percentiles(values, 1)
        lower = _tie_percentiles(values, -1)
        self.assertEqual(higher["a"], 0.0)
        self.assertEqual(higher["b"], higher["c"])
        self.assertEqual(higher["d"], 1.0)
        self.assertEqual(lower["a"], 1.0)
        self.assertEqual(lower["d"], 0.0)

    def test_ridge_and_pairwise_models_recover_ordering(self) -> None:
        rows = [example(month, index) for month in range(1, 4) for index in range(20)]
        models = (
            fit_ridge(rows, penalty=0.1, feature_getter=lambda row: row.family_features),
            fit_pairwise(rows, penalty=0.1),
        )
        for model in models:
            predictions = [
                (row.security_id, model.predict(row.family_features), row.target)
                for row in rows if row.calendar_month == "2023-03"
            ]
            self.assertTrue(all(math.isfinite(value) for _, value, _ in predictions))
            self.assertGreater(spearman(predictions), 0.99)

    def test_active_fundamentals_use_annual_facts_available_by_decision(self) -> None:
        tz = ZoneInfo("America/Toronto")
        facts = (
            ActiveFact("annual", "filing-a", "us-gaap", "NetIncomeLoss", "USD", 100.0,
                       date(2022, 1, 1), date(2022, 12, 31), datetime(2023, 2, 1, tzinfo=tz)),
            ActiveFact("later", "filing-b", "us-gaap", "NetIncomeLoss", "USD", 999.0,
                       date(2023, 1, 1), date(2023, 12, 31), datetime(2024, 2, 1, tzinfo=tz)),
            ActiveFact("shares", "filing-a", "dei", "EntityCommonStockSharesOutstanding", "shares", 10.0,
                       None, date(2022, 12, 31), datetime(2023, 2, 1, tzinfo=tz)),
            ActiveFact("assets-begin", "filing-a", "us-gaap", "Assets", "USD", 800.0,
                       None, date(2021, 12, 31), datetime(2023, 2, 1, tzinfo=tz)),
            ActiveFact("assets-end", "filing-a", "us-gaap", "Assets", "USD", 1200.0,
                       None, date(2022, 12, 31), datetime(2023, 2, 1, tzinfo=tz)),
        )
        earnings_yield, return_on_assets, lineage = _active_fundamentals(
            facts, (20.0, "price-bar"), date(2023, 3, 3),
        )
        self.assertAlmostEqual(earnings_yield or 0, 0.5)
        self.assertAlmostEqual(return_on_assets or 0, 0.1)
        self.assertNotIn("later", lineage)
        self.assertIn("annual", lineage)


if __name__ == "__main__":
    unittest.main()
