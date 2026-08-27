from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import unittest

from quantrade_research.candidate_features import (
    calculate_amihud_illiquidity_20d,
    calculate_downside_volatility_60d,
    calculate_return_on_assets_change_yoy,
    calculate_short_term_reversal_20d,
)
from quantrade_research.features import (
    NEXT_GENERATION_CANDIDATE_SET_VERSION,
    baseline_feature_registry,
    next_generation_candidate_registry,
)
from quantrade_research.fundamentals import FundamentalFactObservation
from quantrade_research.momentum import FeaturePriceObservation
from quantrade_research.quality import DataQualityError


DECISION = datetime(2026, 8, 20, 20, tzinfo=timezone.utc)
START = date(2025, 1, 1)


def prices(count: int = 61) -> list[FeaturePriceObservation]:
    observations: list[FeaturePriceObservation] = []
    for index in range(count):
        session = START + timedelta(days=index)
        adjusted_close = Decimal("100") + Decimal(index if index % 2 else -index) / Decimal("10")
        observations.extend((
            FeaturePriceObservation("security-a", session, adjusted_close, "split_adjusted", DECISION, Decimal("1000")),
            FeaturePriceObservation("security-a", session, Decimal("100"), "unadjusted", DECISION, Decimal("1000")),
        ))
    return observations


def fact(
    concept: str,
    value: str,
    period_end: date,
    *,
    period_start: date | None = None,
    available_at: datetime = DECISION,
) -> FundamentalFactObservation:
    return FundamentalFactObservation(
        "security-a", f"filing-{concept}-{period_end}", "us-gaap", concept, "USD",
        Decimal(value), period_start, period_end, available_at,
    )


class CandidateFeatureTests(unittest.TestCase):
    def test_candidate_registry_is_versioned_and_does_not_change_active_registry(self) -> None:
        active = baseline_feature_registry()
        candidates = next_generation_candidate_registry()
        self.assertEqual(NEXT_GENERATION_CANDIDATE_SET_VERSION, "next_gen_free_v1")
        self.assertEqual(len(active.definitions()), 6)
        self.assertEqual(len(candidates.definitions()), 4)
        self.assertFalse(
            {(item.key, item.version) for item in active.definitions()}
            & {(item.key, item.version) for item in candidates.definitions()}
        )

    def test_price_candidates_use_declared_complete_windows(self) -> None:
        observations = prices()
        formation = START + timedelta(days=60)
        reversal = calculate_short_term_reversal_20d(
            observations, security_id="security-a", formation_date=formation, decision_at=DECISION,
        )
        downside = calculate_downside_volatility_60d(
            observations, security_id="security-a", formation_date=formation, decision_at=DECISION,
        )
        illiquidity = calculate_amihud_illiquidity_20d(
            observations, security_id="security-a", formation_date=formation, decision_at=DECISION,
        )
        adjusted = [item for item in observations if item.adjustment_basis == "split_adjusted"]
        self.assertEqual(reversal.value, adjusted[-1].close_price / adjusted[-21].close_price - Decimal("1"))
        self.assertGreater(downside.value, Decimal("0"))
        self.assertGreater(illiquidity.value, Decimal("0"))
        self.assertEqual({reversal.feature_key, downside.feature_key, illiquidity.feature_key}, {
            "short_term_reversal_20d", "downside_volatility_60d", "amihud_illiquidity_20d",
        })

    def test_price_candidates_reject_late_mismatched_and_zero_volume_inputs(self) -> None:
        observations = prices()
        formation = START + timedelta(days=60)
        late = list(observations)
        late[-2] = replace(late[-2], available_at=DECISION + timedelta(seconds=1))
        with self.assertRaisesRegex(DataQualityError, "unavailable"):
            calculate_short_term_reversal_20d(
                late, security_id="security-a", formation_date=formation, decision_at=DECISION,
            )
        mismatched = [
            item for item in observations
            if not (
                item.adjustment_basis == "unadjusted"
                and item.session_date == formation - timedelta(days=1)
            )
        ]
        with self.assertRaisesRegex(DataQualityError, "matching"):
            calculate_amihud_illiquidity_20d(
                mismatched, security_id="security-a", formation_date=formation, decision_at=DECISION,
            )
        zero_volume = [
            replace(item, volume=Decimal("0"))
            if item.adjustment_basis == "unadjusted" and item.session_date == formation else item
            for item in observations
        ]
        with self.assertRaisesRegex(DataQualityError, "positive dollar volume"):
            calculate_amihud_illiquidity_20d(
                zero_volume, security_id="security-a", formation_date=formation, decision_at=DECISION,
            )

    def test_roa_change_uses_two_latest_public_annual_periods(self) -> None:
        first_start, first_end = date(2023, 12, 31), date(2024, 12, 30)
        second_start, second_end = first_end, date(2025, 12, 30)
        observations = [
            fact("NetIncomeLoss", "100", first_end, period_start=first_start),
            fact("Assets", "900", first_start),
            fact("Assets", "1100", first_end),
            fact("NetIncomeLoss", "180", second_end, period_start=second_start),
            fact("Assets", "1300", second_end),
        ]
        result = calculate_return_on_assets_change_yoy(
            observations,
            security_id="security-a",
            formation_date=date(2026, 8, 20),
            decision_at=DECISION,
        )
        expected = Decimal("180") / Decimal("1200") - Decimal("100") / Decimal("1000")
        self.assertEqual(result.value, expected)
        self.assertEqual(result.feature_key, "return_on_assets_change_yoy")

    def test_roa_change_rejects_incomplete_or_late_history(self) -> None:
        period_start, period_end = date(2024, 12, 30), date(2025, 12, 30)
        incomplete = [
            fact("NetIncomeLoss", "100", period_end, period_start=period_start),
            fact("Assets", "900", period_start),
            fact("Assets", "1100", period_end),
        ]
        with self.assertRaisesRegex(DataQualityError, "two eligible annual periods"):
            calculate_return_on_assets_change_yoy(
                incomplete, security_id="security-a", formation_date=date(2026, 8, 20), decision_at=DECISION,
            )
        late = incomplete + [
            fact(
                "NetIncomeLoss", "120", date(2026, 6, 30), period_start=date(2025, 7, 1),
                available_at=DECISION + timedelta(seconds=1),
            )
        ]
        with self.assertRaisesRegex(DataQualityError, "unavailable"):
            calculate_return_on_assets_change_yoy(
                late, security_id="security-a", formation_date=date(2026, 8, 20), decision_at=DECISION,
            )


if __name__ == "__main__":
    unittest.main()
