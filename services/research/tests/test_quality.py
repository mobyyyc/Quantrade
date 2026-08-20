from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.quality import (
    DailyBarQualityInput,
    DataQualityError,
    FilingFactQualityInput,
    assert_available_as_of,
    evaluate_daily_bar_quality,
    evaluate_filing_fact_quality,
)


DECISION = datetime(2026, 8, 20, 20, tzinfo=timezone.utc)


class QualityGateTests(unittest.TestCase):
    def test_complete_bar_set_is_publishable(self) -> None:
        report = evaluate_daily_bar_quality(
            [DailyBarQualityInput("security-a", date(2026, 8, 20), "unadjusted", Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"), Decimal("100"), DECISION)],
            {"security-a"}, date(2026, 8, 20), "unadjusted", DECISION,
        )
        self.assertTrue(report.publishable)

    def test_missing_and_future_bars_block_publication(self) -> None:
        report = evaluate_daily_bar_quality(
            [DailyBarQualityInput("security-a", date(2026, 8, 20), "unadjusted", Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"), Decimal("100"), datetime(2026, 8, 20, 20, 1, tzinfo=timezone.utc))],
            {"security-a", "security-b"}, date(2026, 8, 20), "unadjusted", DECISION,
        )
        self.assertFalse(report.publishable)
        self.assertEqual({issue.code for issue in report.issues}, {"future_available_at", "missing_daily_bar"})
        with self.assertRaises(DataQualityError):
            report.require_publishable()

    def test_invalid_ohlc_and_duplicate_filing_fact_are_rejected(self) -> None:
        bars = [DailyBarQualityInput("security-a", date(2026, 8, 20), "unadjusted", Decimal("10"), Decimal("9"), Decimal("8"), Decimal("11"), Decimal("1"), DECISION)]
        self.assertFalse(evaluate_daily_bar_quality(bars, {"security-a"}, date(2026, 8, 20), "unadjusted", DECISION).publishable)
        fact = FilingFactQualityInput("security-a", "us-gaap", "Assets", date(2026, 6, 30), DECISION)
        report = evaluate_filing_fact_quality([fact, fact], DECISION)
        self.assertIn("duplicate_filing_fact", [issue.code for issue in report.issues])

    def test_as_of_gate_never_silently_filters_future_records(self) -> None:
        future = FilingFactQualityInput("security-a", "us-gaap", "Assets", date(2026, 6, 30), datetime(2026, 8, 20, 20, 1, tzinfo=timezone.utc))
        with self.assertRaises(DataQualityError):
            assert_available_as_of([future], DECISION, "filing facts")


if __name__ == "__main__":
    unittest.main()
