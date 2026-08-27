from datetime import date
import unittest

from quantrade_research.paper_portfolio import is_monthly_formation


class PaperPortfolioScheduleTests(unittest.TestCase):
    def test_accepts_next_session_in_new_month(self) -> None:
        self.assertTrue(is_monthly_formation(date(2026, 8, 31), date(2026, 9, 1)))

    def test_rejects_an_ordinary_daily_formation(self) -> None:
        self.assertFalse(is_monthly_formation(date(2026, 8, 26), date(2026, 8, 27)))

    def test_accepts_year_end_transition(self) -> None:
        self.assertTrue(is_monthly_formation(date(2026, 12, 31), date(2027, 1, 4)))


if __name__ == "__main__":
    unittest.main()
