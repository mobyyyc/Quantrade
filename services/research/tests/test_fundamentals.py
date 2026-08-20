from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import unittest

from quantrade_research.fundamentals import (
    FundamentalFactObservation,
    calculate_earnings_yield_ttm,
    calculate_return_on_assets_ttm,
)
from quantrade_research.momentum import FeaturePriceObservation
from quantrade_research.quality import DataQualityError


DECISION = datetime(2026, 8, 20, 20, tzinfo=timezone.utc)
FORMATION = date(2026, 8, 20)
PERIOD_START = date(2024, 12, 30)
PERIOD_END = date(2025, 12, 30)


def fact(
    taxonomy: str, concept: str, value: str, period_end: date, *, period_start: date | None = None,
    unit: str = "USD", available_at: datetime = DECISION,
) -> FundamentalFactObservation:
    return FundamentalFactObservation("security-a", "filing-a", taxonomy, concept, unit, Decimal(value), period_start, period_end, available_at)


def inputs() -> list[FundamentalFactObservation]:
    return [
        fact("us-gaap", "NetIncomeLoss", "120", PERIOD_END, period_start=PERIOD_START),
        fact("dei", "EntityCommonStockSharesOutstanding", "10", PERIOD_END, unit="shares"),
        fact("us-gaap", "Assets", "1000", PERIOD_START),
        fact("us-gaap", "Assets", "1400", PERIOD_END),
    ]


def price() -> FeaturePriceObservation:
    return FeaturePriceObservation("security-a", FORMATION, Decimal("20"), "split_adjusted", DECISION)


class FundamentalFeatureTests(unittest.TestCase):
    def test_calculates_earnings_yield_and_return_on_assets_from_eligible_facts(self) -> None:
        facts = inputs()
        earnings_yield = calculate_earnings_yield_ttm(
            facts, [price()], security_id="security-a", formation_date=FORMATION, decision_at=DECISION
        )
        roa = calculate_return_on_assets_ttm(
            facts, security_id="security-a", formation_date=FORMATION, decision_at=DECISION
        )
        self.assertEqual(earnings_yield.value, Decimal("120") / Decimal("200"))
        self.assertEqual(earnings_yield.feature_key, "earnings_yield_ttm")
        self.assertEqual(roa.value, Decimal("120") / Decimal("1200"))
        self.assertEqual(roa.feature_key, "return_on_assets_ttm")

    def test_rejects_future_facts_and_missing_annual_or_asset_endpoints(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "unavailable"):
            calculate_earnings_yield_ttm(
                [
                    fact("us-gaap", "NetIncomeLoss", "120", PERIOD_END, period_start=PERIOD_START, available_at=DECISION + timedelta(seconds=1)),
                    *inputs()[1:],
                ],
                [price()], security_id="security-a", formation_date=FORMATION, decision_at=DECISION,
            )
        quarterly = [
            fact("us-gaap", "NetIncomeLoss", "30", PERIOD_END, period_start=PERIOD_END - timedelta(days=90)),
            *inputs()[1:],
        ]
        with self.assertRaisesRegex(DataQualityError, "annual"):
            calculate_return_on_assets_ttm(
                quarterly, security_id="security-a", formation_date=FORMATION, decision_at=DECISION
            )
        with self.assertRaisesRegex(DataQualityError, "annual-period start"):
            calculate_return_on_assets_ttm(
                inputs()[0:2] + [inputs()[-1]],
                security_id="security-a", formation_date=FORMATION, decision_at=DECISION,
            )


if __name__ == "__main__":
    unittest.main()
