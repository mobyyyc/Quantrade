from datetime import date
import unittest

from quantrade_research.forward_readiness_snapshot import ForwardReadinessMetric
from quantrade_research.quality import DataQualityError


class ForwardReadinessSnapshotTests(unittest.TestCase):
    def test_accepts_a_supported_nonnegative_metric(self) -> None:
        metric = ForwardReadinessMetric(20, 100, 2, 3, 10, date(2026, 8, 20))
        self.assertEqual(metric.horizon_sessions, 20)

    def test_rejects_unsupported_or_negative_metrics(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "unsupported"):
            ForwardReadinessMetric(10, 1, 0, 0, 1, None)
        with self.assertRaisesRegex(DataQualityError, "cannot be negative"):
            ForwardReadinessMetric(5, -1, 0, 0, 0, None)
