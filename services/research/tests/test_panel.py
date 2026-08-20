from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.panel import FilingFactPanelInput, UniverseMembershipInput, build_point_in_time_panel
from quantrade_research.quality import DailyBarQualityInput, DataQualityError


DECISION = datetime(2026, 8, 20, 20, tzinfo=timezone.utc)
SESSION = date(2026, 8, 20)


def bar() -> DailyBarQualityInput:
    return DailyBarQualityInput("security-a", SESSION, "split_adjusted", Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"), Decimal("100"), DECISION)


class PointInTimePanelTests(unittest.TestCase):
    def test_selects_latest_fact_available_at_decision(self) -> None:
        facts = [
            FilingFactPanelInput("security-a", "old", "us-gaap", "Assets", Decimal("100"), date(2026, 3, 31), datetime(2026, 5, 1, tzinfo=timezone.utc)),
            FilingFactPanelInput("security-a", "future", "us-gaap", "Assets", Decimal("200"), date(2026, 6, 30), datetime(2026, 8, 21, tzinfo=timezone.utc)),
        ]
        panel = build_point_in_time_panel(
            memberships=[UniverseMembershipInput("security-a", SESSION, DECISION)], bars=[bar()], filing_facts=facts,
            session_date=SESSION, decision_at=DECISION, adjustment_basis="split_adjusted", required_facts={("us-gaap", "Assets")},
        )
        self.assertEqual(panel[0].facts[("us-gaap", "Assets")], Decimal("100"))

    def test_missing_required_fact_blocks_panel(self) -> None:
        with self.assertRaises(DataQualityError):
            build_point_in_time_panel(
                memberships=[UniverseMembershipInput("security-a", SESSION, DECISION)], bars=[bar()], filing_facts=[],
                session_date=SESSION, decision_at=DECISION, adjustment_basis="split_adjusted", required_facts={("us-gaap", "Assets")},
            )

    def test_future_universe_snapshot_blocks_panel(self) -> None:
        fact = FilingFactPanelInput("security-a", "old", "us-gaap", "Assets", Decimal("100"), date(2026, 3, 31), DECISION)
        with self.assertRaises(DataQualityError):
            build_point_in_time_panel(
                memberships=[UniverseMembershipInput("security-a", date(2026, 8, 21), DECISION)], bars=[bar()], filing_facts=[fact],
                session_date=SESSION, decision_at=DECISION, adjustment_basis="split_adjusted", required_facts={("us-gaap", "Assets")},
            )


if __name__ == "__main__":
    unittest.main()
