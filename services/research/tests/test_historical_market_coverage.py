from datetime import date
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.historical_market_coverage import BasisCoverage, HistoricalMarketCoverageReport, coverage_warnings


class HistoricalMarketCoverageTests(unittest.TestCase):
    def test_warns_when_provider_starts_after_requested_range_or_a_listing_is_excluded(self) -> None:
        stock = (BasisCoverage("unadjusted", 10, 5, 2, date(2020, 1, 2), date(2020, 1, 8), 2, 1),)
        benchmark = (BasisCoverage("unadjusted", 5, 5, 1, date(2020, 1, 2), date(2020, 1, 8), 1, 0),)
        warnings = coverage_warnings(
            requested_start=date(2016, 1, 1), stock_coverage=stock,
            benchmark_coverage=benchmark, excluded_listings=("EXAMPLE",),
        )
        self.assertTrue(any("begins after" in warning for warning in warnings))
        self.assertTrue(any("incomplete" in warning for warning in warnings))
        self.assertTrue(any("excluded" in warning for warning in warnings))

    def test_report_json_serializes_dates_and_tuple_values(self) -> None:
        report = HistoricalMarketCoverageReport(
            generated_at=date(2026, 8, 25), cohort_code="cohort", requested_start=date(2016, 1, 1),
            requested_end=date(2026, 6, 30), cohort_company_count=500,
            stock_coverage=(BasisCoverage("unadjusted", 1, 1, 1, date(2020, 1, 2), date(2020, 1, 2), 1, 0),),
            benchmark_coverage=(), excluded_cohort_listings=("EXAMPLE",),
            incorrect_stock_availability_count=0, incorrect_benchmark_availability_count=0,
            warnings=("Tier B",),
        )
        self.assertIn('"requested_start": "2016-01-01"', report.to_json())
        self.assertIn('"EXAMPLE"', report.to_json())


if __name__ == "__main__":
    unittest.main()
