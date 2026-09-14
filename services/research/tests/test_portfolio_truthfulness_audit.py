from datetime import date, datetime, timezone
from decimal import Decimal
import unittest
from unittest.mock import MagicMock, patch

from quantrade_research.portfolio_truthfulness_audit import audit_portfolio_truthfulness


class PortfolioTruthfulnessAuditTests(unittest.TestCase):
    def run_audit(self, official_rows, outcome_rows, *, legacy_count=0, missed_count=0, conflicts=()):
        settings = MagicMock(database_url="unused")
        with patch("psycopg.connect") as connect:
            cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.side_effect = [(legacy_count,), (missed_count,)]
            cursor.fetchall.side_effect = [official_rows, outcome_rows, list(conflicts)]
            report = audit_portfolio_truthfulness(settings=settings)
        return report

    def test_accepts_a_reconciled_official_portfolio_and_reports_excluded_preview(self) -> None:
        formation = date(2026, 7, 31)
        execution = date(2026, 8, 3)
        outcome = date(2026, 8, 28)
        official_rows = [(
            "run-1", formation, execution, Decimal("100000"), Decimal("0"), "model-v1",
            1, execution, 20, 20, Decimal("100000"), 0, 1, 20,
        )]
        outcome_rows = [(
            formation, 20, "completed", Decimal("0.08"), Decimal("0.03"), Decimal("0.05"),
            "ledger-v1", "a" * 64, "b" * 64, 0, datetime(2026, 8, 28, tzinfo=timezone.utc),
            outcome, outcome,
        )]
        report = self.run_audit(official_rows, outcome_rows, legacy_count=1)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["critical_finding_count"], 0)
        self.assertEqual(report["findings"][0]["code"], "legacy_preview_excluded")

    def test_rejects_invalid_formation_holdings_and_outcome_arithmetic(self) -> None:
        formation = date(2026, 8, 25)
        execution = date(2026, 8, 26)
        official_rows = [(
            "run-1", formation, execution, Decimal("100000"), Decimal("0"), None,
            0, date(2026, 8, 27), 19, 19, Decimal("95000"), 1, 2, 18,
        )]
        outcome_rows = [(
            formation, 20, "completed", Decimal("0.08"), Decimal("0.03"), Decimal("0.06"),
            None, None, None, None, None, date(2026, 9, 22), date(2026, 9, 21),
        )]
        report = self.run_audit(official_rows, outcome_rows)
        self.assertEqual(report["status"], "failed")
        codes = {item["code"] for item in report["findings"]}
        self.assertEqual(codes, {
            "invalid_formation_session", "invalid_next_open", "not_month_end_formation", "ambiguous_formation_model",
            "invalid_holdings", "formation_nav_mismatch", "invalid_outcome_window",
            "invalid_completed_outcome",
        })

    def test_rejects_a_missed_and_official_conflict(self) -> None:
        report = self.run_audit([], [], conflicts=((date(2026, 8, 31),),), missed_count=1)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["findings"][0]["code"], "gap_conflicts_with_official_portfolio")


if __name__ == "__main__":
    unittest.main()
