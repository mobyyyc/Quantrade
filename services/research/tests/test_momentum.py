from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import unittest

from quantrade_research.momentum import (
    FeaturePriceObservation,
    calculate_momentum_12_1,
    calculate_relative_strength_6m,
)
from quantrade_research.quality import DataQualityError


DECISION = datetime(2026, 8, 20, 20, tzinfo=timezone.utc)
START = date(2025, 1, 1)


def prices(security_id: str, starting_close: int, count: int = 300) -> list[FeaturePriceObservation]:
    return [
        FeaturePriceObservation(
            security_id=security_id,
            session_date=START + timedelta(days=index),
            close_price=Decimal(starting_close + index),
            adjustment_basis="split_adjusted",
            available_at=DECISION,
        )
        for index in range(count)
    ]


class MomentumFeatureTests(unittest.TestCase):
    def test_momentum_12_1_uses_the_declared_sessions_and_registry_hash(self) -> None:
        history = prices("security-a", 1)
        result = calculate_momentum_12_1(
            history,
            security_id="security-a",
            formation_date=history[-1].session_date,
            decision_at=DECISION,
        )
        self.assertEqual(result.feature_key, "momentum_12_1")
        self.assertEqual(result.feature_version, "v1")
        self.assertEqual(result.value, Decimal(279) / Decimal(48) - Decimal(1))
        self.assertEqual(len(result.definition_hash), 64)

    def test_momentum_rejects_future_and_incomplete_history(self) -> None:
        history = prices("security-a", 1)
        history[-22] = replace(
            history[-22], available_at=DECISION + timedelta(seconds=1)
        )
        with self.assertRaisesRegex(DataQualityError, "unavailable"):
            calculate_momentum_12_1(
                history,
                security_id="security-a",
                formation_date=history[-1].session_date,
                decision_at=DECISION,
            )
        with self.assertRaisesRegex(DataQualityError, "253"):
            calculate_momentum_12_1(
                prices("security-a", 1, 252),
                security_id="security-a",
                formation_date=START + timedelta(days=251),
                decision_at=DECISION,
            )

    def test_relative_strength_requires_matching_complete_windows(self) -> None:
        security = prices("security-a", 100)
        benchmark = prices("spy", 50)
        result = calculate_relative_strength_6m(
            security,
            benchmark,
            security_id="security-a",
            benchmark_security_id="spy",
            formation_date=security[-1].session_date,
            decision_at=DECISION,
        )
        expected = (Decimal(399) / Decimal(273) - Decimal(1)) - (
            Decimal(349) / Decimal(223) - Decimal(1)
        )
        self.assertEqual(result.value, expected)
        self.assertEqual(result.feature_key, "relative_strength_6m")

        mismatched_benchmark = benchmark[:250] + benchmark[251:] + [
            FeaturePriceObservation("spy", START - timedelta(days=1), Decimal("49"), "split_adjusted", DECISION)
        ]
        with self.assertRaisesRegex(DataQualityError, "matching"):
            calculate_relative_strength_6m(
                security,
                mismatched_benchmark,
                security_id="security-a",
                benchmark_security_id="spy",
                formation_date=security[-1].session_date,
                decision_at=DECISION,
            )


if __name__ == "__main__":
    unittest.main()
