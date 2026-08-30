from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.phase_9c_features import (
    FAMILY_KEYS, RAW_FEATURE_SPECS, PriceBar, RawFeatureCell,
    centered_cross_sectional_ranks, compose_families, market_feature_cells,
)


UTC = timezone.utc


def bars(security: str, count: int, *, multiplier: Decimal = Decimal("1")):
    start = date(2023, 1, 1)
    return tuple(
        PriceBar(
            f"{security}-{index}", security, start + timedelta(days=index),
            multiplier * Decimal(index + 100), datetime(2025, 1, 1, tzinfo=UTC), "split_adjusted",
        )
        for index in range(count)
    )


class Phase9CFeatureTests(unittest.TestCase):
    def test_market_features_use_frozen_windows_and_produce_lineage(self) -> None:
        stock = bars("stock", 253)
        benchmark = bars("SPY", 253, multiplier=Decimal("0.5"))
        result = market_feature_cells(stock, benchmark, formation_date=stock[-1].session_date)
        self.assertEqual(set(result), {
            "momentum_12_1", "relative_strength_6m", "short_term_reversal_20d",
            "realized_volatility_60d", "idiosyncratic_volatility_60d",
        })
        self.assertTrue(all(item.available for item in result.values()))
        self.assertTrue(all(item.lineage for item in result.values()))
        self.assertEqual(result["relative_strength_6m"].value, Decimal("0"))

    def test_missing_market_history_is_explicit(self) -> None:
        stock = bars("stock", 20)
        result = market_feature_cells(stock, bars("SPY", 20), formation_date=stock[-1].session_date)
        self.assertFalse(result["momentum_12_1"].available)
        self.assertEqual(result["momentum_12_1"].exclusion, "insufficient_253_session_history")

    def test_centered_ranks_are_tie_aware_oriented_and_neutral_when_missing(self) -> None:
        cells = {
            "a": RawFeatureCell(Decimal("1"), ("a",)),
            "b": RawFeatureCell(Decimal("2"), ("b",)),
            "c": RawFeatureCell(Decimal("2"), ("c",)),
            "d": RawFeatureCell(None, (), "missing"),
        }
        ranked = centered_cross_sectional_ranks(cells, direction=-1)
        self.assertEqual(ranked["a"].centered_rank, Decimal("1"))
        self.assertEqual(ranked["b"].centered_rank, Decimal("-0.5"))
        self.assertEqual(ranked["c"].centered_rank, Decimal("-0.5"))
        self.assertEqual(ranked["d"].centered_rank, Decimal("0"))

    def test_family_values_use_fixed_denominators_and_separate_availability(self) -> None:
        ranked = {}
        for spec in RAW_FEATURE_SPECS:
            cell = RawFeatureCell(Decimal("1"), (spec.key,))
            ranked[spec.key] = centered_cross_sectional_ranks({"stock": cell}, direction=spec.direction)["stock"]
        ranked["earnings_yield_ttm"] = centered_cross_sectional_ranks(
            {"stock": RawFeatureCell(None, (), "missing")}, direction=1,
        )["stock"]
        families = compose_families(ranked)
        self.assertEqual(tuple(families), FAMILY_KEYS)
        self.assertEqual(families["value"].availability, Decimal("2") / Decimal("3"))
        self.assertEqual(families["value"].available_feature_count, 2)
        self.assertTrue(families["value"].informative)


if __name__ == "__main__":
    unittest.main()
