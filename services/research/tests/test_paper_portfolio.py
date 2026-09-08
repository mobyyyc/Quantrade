from datetime import date
import unittest
from unittest.mock import MagicMock, patch

from quantrade_research.paper_portfolio import (
    is_execution_window_open, is_monthly_formation, record_missed_paper_portfolio_formations,
)


class PaperPortfolioScheduleTests(unittest.TestCase):
    def test_accepts_next_session_in_new_month(self) -> None:
        self.assertTrue(is_monthly_formation(date(2026, 8, 31), date(2026, 9, 1)))

    def test_rejects_an_ordinary_daily_formation(self) -> None:
        self.assertFalse(is_monthly_formation(date(2026, 8, 26), date(2026, 8, 27)))

    def test_accepts_year_end_transition(self) -> None:
        self.assertTrue(is_monthly_formation(date(2026, 12, 31), date(2027, 1, 4)))

    def test_execution_window_cannot_be_backfilled(self) -> None:
        self.assertTrue(is_execution_window_open(date(2026, 9, 1), date(2026, 9, 1)))
        self.assertFalse(is_execution_window_open(date(2026, 9, 1), date(2026, 9, 2)))

    def test_missed_formations_are_recorded_only_after_the_execution_window(self) -> None:
        settings = MagicMock(database_url="unused")
        with patch("psycopg.connect") as connect:
            cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchall.return_value = [(date(2026, 9, 30),)]
            recorded = record_missed_paper_portfolio_formations(
                settings=settings, as_of_date=date(2026, 10, 2),
            )
        self.assertEqual(recorded, (date(2026, 9, 30),))
        statement, parameters = cursor.execute.call_args.args
        self.assertIn("sessions.execution_date < %s", statement)
        self.assertIn("NOT EXISTS", statement)
        self.assertIn("ON CONFLICT (formation_date) DO NOTHING", statement)
        self.assertEqual(parameters[0], "live_after_validation_v1")


if __name__ == "__main__":
    unittest.main()
