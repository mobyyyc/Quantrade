from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import unittest

from quantrade_research.momentum import FeaturePriceObservation
from quantrade_research.quality import DataQualityError
from quantrade_research.risk_liquidity import (
    calculate_median_dollar_volume_20d,
    calculate_trailing_volatility_60d,
)


DECISION = datetime(2026, 8, 20, 20, tzinfo=timezone.utc)
START = date(2026, 1, 1)


def split_adjusted_prices(count: int = 61) -> list[FeaturePriceObservation]:
    return [
        FeaturePriceObservation(
            "security-a", START + timedelta(days=index), Decimal(2) ** index,
            "split_adjusted", DECISION,
        )
        for index in range(count)
    ]


def unadjusted_prices(count: int = 20) -> list[FeaturePriceObservation]:
    return [
        FeaturePriceObservation(
            "security-a", START + timedelta(days=index), Decimal(index + 1), "unadjusted",
            DECISION, Decimal("100"),
        )
        for index in range(count)
    ]


class RiskLiquidityFeatureTests(unittest.TestCase):
    def test_constant_log_returns_have_zero_trailing_volatility(self) -> None:
        prices = split_adjusted_prices()
        result = calculate_trailing_volatility_60d(
            prices, security_id="security-a", formation_date=prices[-1].session_date, decision_at=DECISION
        )
        self.assertEqual(result.feature_key, "trailing_volatility_60d")
        self.assertLess(abs(result.value), Decimal("1e-20"))

    def test_volatility_rejects_incomplete_or_post_decision_price_history(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "61"):
            calculate_trailing_volatility_60d(
                split_adjusted_prices(60), security_id="security-a",
                formation_date=START + timedelta(days=59), decision_at=DECISION,
            )
        prices = split_adjusted_prices()
        prices[-1] = replace(prices[-1], available_at=DECISION + timedelta(seconds=1))
        with self.assertRaisesRegex(DataQualityError, "unavailable"):
            calculate_trailing_volatility_60d(
                prices, security_id="security-a", formation_date=prices[-1].session_date, decision_at=DECISION
            )

    def test_median_dollar_volume_uses_unadjusted_twenty_session_window(self) -> None:
        prices = unadjusted_prices()
        result = calculate_median_dollar_volume_20d(
            prices, security_id="security-a", formation_date=prices[-1].session_date, decision_at=DECISION
        )
        self.assertEqual(result.feature_key, "median_dollar_volume_20d")
        self.assertEqual(result.value, Decimal("1050"))

    def test_dollar_volume_rejects_missing_volume_and_incomplete_history(self) -> None:
        prices = unadjusted_prices()
        prices[0] = replace(prices[0], volume=None)
        with self.assertRaisesRegex(DataQualityError, "missing"):
            calculate_median_dollar_volume_20d(
                prices, security_id="security-a", formation_date=prices[-1].session_date, decision_at=DECISION
            )
        with self.assertRaisesRegex(DataQualityError, "20"):
            calculate_median_dollar_volume_20d(
                unadjusted_prices(19), security_id="security-a",
                formation_date=START + timedelta(days=18), decision_at=DECISION,
            )


if __name__ == "__main__":
    unittest.main()
