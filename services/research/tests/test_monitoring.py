from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.monitoring import ScoreRunSummary, evaluate_monitoring


class MonitoringTests(unittest.TestCase):
    def test_stale_data_and_failed_manifest_are_critical(self) -> None:
        alerts = evaluate_monitoring(expected_price_date=date(2026, 8, 20), expected_score_date=date(2026, 8, 20), latest_price_date=date(2026, 8, 19), latest_score=None, failed_runs=("ingest-1",))
        self.assertEqual({alert.code for alert in alerts}, {"stale_market_data", "stale_scores", "failed_run"})

    def test_score_anomalies_are_warnings(self) -> None:
        alerts = evaluate_monitoring(expected_price_date=date(2026, 8, 20), expected_score_date=date(2026, 8, 20), latest_price_date=date(2026, 8, 20), latest_score=ScoreRunSummary(date(2026, 8, 20), 50, Decimal("80")), previous_score=ScoreRunSummary(date(2026, 8, 19), 100, Decimal("50")))
        self.assertEqual({alert.code for alert in alerts}, {"eligible_count_drop", "mean_score_shift"})
