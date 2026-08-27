from datetime import date, datetime, timezone
import unittest

from quantrade_research.active_model_error_analysis import (
    BenchmarkBar,
    SegmentContext,
    analyze_predictions,
    build_market_regimes,
    market_trend_regime,
    stock_volatility_regime,
)
from quantrade_research.challenger_model_comparison import Prediction
from quantrade_research.quality import DataQualityError


class ActiveModelErrorAnalysisTests(unittest.TestCase):
    def test_regime_boundaries_are_deterministic(self) -> None:
        self.assertEqual(stock_volatility_regime(0.0), "low")
        self.assertEqual(stock_volatility_regime(1 / 3), "middle")
        self.assertEqual(stock_volatility_regime(1.0), "high")
        self.assertEqual(market_trend_regime(-0.05), "bearish")
        self.assertEqual(market_trend_regime(0.0), "range_bound")
        self.assertEqual(market_trend_regime(0.05), "bullish")
        with self.assertRaises(DataQualityError):
            stock_volatility_regime(1.1)

    def test_market_regime_uses_only_bars_available_by_decision(self) -> None:
        decision_date = date(2024, 4, 1)
        decision_at = datetime(2024, 4, 1, 20, tzinfo=timezone.utc)
        bars = tuple(
            BenchmarkBar(
                date(2024, 1, 1).fromordinal(date(2024, 1, 1).toordinal() + index),
                100 + index,
                datetime(2024, 1, 1, 18, tzinfo=timezone.utc),
            )
            for index in range(61)
        ) + (
            BenchmarkBar(decision_date, 1_000, datetime(2024, 4, 1, 21, tzinfo=timezone.utc)),
        )
        regimes, lineage_hash = build_market_regimes({decision_date: decision_at}, bars)
        self.assertEqual(regimes[decision_date], "bullish")
        self.assertEqual(len(lineage_hash), 64)

    def test_segment_analysis_reports_each_dimension_without_holdout_logic(self) -> None:
        score_date = date(2024, 1, 31)
        predictions = tuple(
            Prediction(
                1,
                score_date,
                f"security-{index}",
                index / 100,
                index / 90,
                index / 80,
                0.01,
            )
            for index in range(10)
        )
        contexts = {
            (score_date, item.security_id): SegmentContext(
                "Technology" if index < 5 else "Health Care",
                "low" if index < 5 else "high",
                datetime(2024, 1, 31, 20, tzinfo=timezone.utc),
            )
            for index, item in enumerate(predictions)
        }
        report = analyze_predictions(predictions, contexts, {score_date: "bullish"})
        self.assertEqual(report["overall"]["observation_count"], 10)
        self.assertEqual(len(report["dimensions"]["sector"]), 2)
        self.assertEqual(len(report["dimensions"]["stock_volatility"]), 2)
        self.assertEqual(report["dimensions"]["market_regime"][0]["segment"], "bullish")


if __name__ == "__main__":
    unittest.main()
