from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantrade_research.forward_evidence_report import (
    Deployment, DriftObservation, ForwardLabelEvidence, HealthObservation,
    MissedFormation, OfficialFormation, PortfolioOutcome, build_report, publish_report,
    render_summary,
)


DEPLOYMENT = Deployment("active_v1", datetime(2026, 8, 29, 18, tzinfo=timezone.utc), "private_beta")
HEALTH = (
    HealthObservation(date(2026, 9, 1), "healthy", 500, 495, Decimal("0.99"), None, None, True, True, True),
    HealthObservation(date(2026, 9, 2), "warning", 500, 496, Decimal("0.992"), Decimal("0.10"), Decimal("0.02"), True, True, True),
)
DRIFT = (
    DriftObservation(date(2026, 9, 1), "momentum_12_1", "v1", Decimal("0.04"), "healthy"),
    DriftObservation(date(2026, 9, 2), "momentum_12_1", "v1", Decimal("0.12"), "warning"),
)
LABELS = (
    ForwardLabelEvidence(5, 991, 495, 1, 495, 1, date(2026, 9, 9)),
    ForwardLabelEvidence(20, 991, 0, 0, 991, 0, None),
    ForwardLabelEvidence(60, 991, 0, 0, 991, 0, None),
)


def report(*, formations=(), outcomes=(), missed=()):
    return build_report(
        deployment=DEPLOYMENT, period_start=date(2026, 8, 29), period_end=date(2026, 9, 15),
        health=HEALTH, drift=DRIFT, forward_labels=LABELS,
        formations=formations, outcomes=outcomes, missed_formations=missed,
        code_revision="abc123",
    )


class ForwardEvidenceReportTests(unittest.TestCase):
    def test_summarizes_coverage_drift_and_rank_stability(self):
        result = report()
        self.assertEqual(result["health"]["snapshot_count"], 2)
        self.assertEqual(result["health"]["minimum_coverage_ratio"], "0.99")
        self.assertEqual(result["health"]["rank_stability"]["mean_top_20_churn_ratio"], "0.10")
        self.assertEqual(result["health"]["feature_drift"][0]["maximum_psi"], "0.12")
        self.assertTrue(result["health"]["integrity_verified_for_every_snapshot"])
        self.assertIn("momentum_12_1@v1 | 0.12 | 0.12 | warning", render_summary(result))

    def test_does_not_invent_a_basket_when_no_official_formation_exists(self):
        result = report(missed=(MissedFormation(date(2026, 8, 31), date(2026, 9, 1), "month_end_score_unavailable"),))
        basket = result["official_basket_vs_spy"]
        self.assertEqual(basket["status"], "awaiting_official_formation")
        self.assertEqual(basket["formation_count"], 0)
        self.assertTrue(all(row["average_benchmark_relative_return"] is None for row in basket["horizons"]))

    def test_reports_only_pre_existing_official_outcomes(self):
        formation = OfficialFormation(date(2026, 8, 31), date(2026, 9, 1))
        outcome = PortfolioOutcome(
            formation.score_date, 5, "completed", date(2026, 9, 8),
            Decimal("0.03"), Decimal("0.01"), Decimal("0.02"), None,
        )
        basket = report(formations=(formation,), outcomes=(outcome,))["official_basket_vs_spy"]
        self.assertEqual(basket["status"], "observed")
        row = basket["horizons"][0]
        self.assertEqual(row["outperformed_spy_count"], 1)
        self.assertEqual(row["average_benchmark_relative_return"], "0.02")
        self.assertEqual(basket["horizons"][1]["pending_outcomes"], 1)

    def test_rejects_pre_deployment_or_unreconciled_evidence(self):
        with self.assertRaisesRegex(ValueError, "before the active model deployment"):
            build_report(
                deployment=DEPLOYMENT, period_start=date(2026, 8, 28), period_end=date(2026, 9, 15),
                health=(), drift=(), forward_labels=LABELS, formations=(), outcomes=(),
                missed_formations=(), code_revision="abc123",
            )
        bad = list(LABELS)
        bad[0] = ForwardLabelEvidence(5, 991, 495, 1, 494, 1, date(2026, 9, 9))
        with self.assertRaisesRegex(ValueError, "do not reconcile"):
            build_report(
                deployment=DEPLOYMENT, period_start=date(2026, 8, 29), period_end=date(2026, 9, 15),
                health=(), drift=(), forward_labels=tuple(bad), formations=(), outcomes=(),
                missed_formations=(), code_revision="abc123",
            )

    def test_report_is_deterministic_and_published_with_verified_hashes(self):
        first = report()
        self.assertEqual(first, report())
        with TemporaryDirectory() as directory:
            output = Path(directory) / "evidence"
            publish_report(first, output)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["logical_sha256"], first["logical_sha256"])
            for name, digest in manifest["sha256"].items():
                self.assertEqual(sha256((output / name).read_bytes()).hexdigest(), digest)
            with self.assertRaises(FileExistsError):
                publish_report(first, output)


if __name__ == "__main__":
    unittest.main()
