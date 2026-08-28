from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.monthly_feature_panel import (
    ActionInput, PriceInput, accrual_quality, asset_growth, net_share_issuance, short_term_reversal,
)
from quantrade_research.sec_fact_resolver import LEGACY_AVAILABILITY_RULE, ResolvedSecFact


UTC = timezone.utc


def sec_fact(key, concept, value, end, *, start=None, unit="USD"):
    return ResolvedSecFact(
        key, "filing-" + key, "security", key, "10-K", False, "us-gaap" if unit == "USD" else "dei",
        concept, unit, Decimal(value), start, end, 2024, "FY", datetime(2025, 2, 1, tzinfo=UTC), None,
        datetime(2025, 2, 1, 0, 5, tzinfo=UTC), LEGACY_AVAILABILITY_RULE, "source", None,
    )


class MonthlyFeaturePanelTests(unittest.TestCase):
    def test_reversal_excludes_formation_session(self) -> None:
        prices = [
            PriceInput(str(index), "security", date(2025, 1, index + 1), Decimal(index + 1), datetime(2025, 2, 1, tzinfo=UTC), "source")
            for index in range(22)
        ]
        self.assertEqual(short_term_reversal(prices).value, Decimal("21") / Decimal("1") - 1)

    def test_asset_growth_uses_comparable_annual_endpoints(self) -> None:
        result = asset_growth([
            sec_fact("old", "Assets", "100", date(2023, 12, 31)),
            sec_fact("new", "Assets", "125", date(2024, 12, 31)),
        ])
        self.assertEqual(result.value, Decimal("0.25"))

    def test_share_issuance_reconciles_forward_split(self) -> None:
        facts = [
            sec_fact("old", "EntityCommonStockSharesOutstanding", "100", date(2023, 12, 31), unit="shares"),
            sec_fact("new", "EntityCommonStockSharesOutstanding", "220", date(2024, 12, 31), unit="shares"),
        ]
        split = ActionInput(
            "split", "security", "forward_split", date(2024, 6, 1), Decimal("2"), Decimal("1"),
            datetime(2024, 6, 1, tzinfo=UTC), "source",
        )
        self.assertEqual(net_share_issuance(facts, [split]).value, Decimal("0.1"))

    def test_share_issuance_uses_annual_basic_weighted_average_fallback(self) -> None:
        facts = [
            sec_fact(
                "old", "WeightedAverageNumberOfSharesOutstandingBasic", "100", date(2023, 12, 31),
                start=date(2023, 1, 1), unit="shares",
            ),
            sec_fact(
                "new", "WeightedAverageNumberOfSharesOutstandingBasic", "105", date(2024, 12, 31),
                start=date(2024, 1, 1), unit="shares",
            ),
        ]
        self.assertEqual(net_share_issuance(facts, []).value, Decimal("0.05"))

    def test_accrual_quality_uses_aligned_annual_inputs(self) -> None:
        start, end = date(2024, 1, 1), date(2024, 12, 31)
        result = accrual_quality([
            sec_fact("ni", "NetIncomeLoss", "20", end, start=start),
            sec_fact("cfo", "NetCashProvidedByUsedInOperatingActivities", "30", end, start=start),
            sec_fact("ab", "Assets", "90", start),
            sec_fact("ae", "Assets", "110", end),
        ])
        self.assertEqual(result.value, Decimal("-0.1"))


if __name__ == "__main__":
    unittest.main()
