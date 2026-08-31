from datetime import date
import unittest

from quantrade_research.phase_9c_portfolio_attribution import (
    PortfolioPeriod,
    select_portfolio,
    summarize_periods,
)
from quantrade_research.phase_9c_feature_panel import _formation_dates


def period(month: int, *, relative: float, turnover: float) -> PortfolioPeriod:
    formation = date(2024, month, 28)
    return PortfolioPeriod(
        "model", "exact_top20", formation, formation, formation,
        tuple(f"security-{index:02d}" for index in range(20)), "a" * 64,
        int((1 - turnover) * 20), int(turnover * 20), int(turnover * 20), turnover,
        relative + 0.01, 0.01, relative, tuple(f"hash-{index}" for index in range(20)), None,
    )


class Phase9CPortfolioAttributionTests(unittest.TestCase):
    def test_month_end_rule_uses_the_final_actual_session_not_last_weekly_session(self) -> None:
        sessions = (
            date(2024, 1, 26), date(2024, 1, 29), date(2024, 1, 30), date(2024, 1, 31),
            date(2024, 2, 1), date(2024, 2, 2),
        )
        self.assertEqual(
            _formation_dates(sessions, "month_end"),
            (date(2024, 1, 31), date(2024, 2, 2)),
        )
        self.assertIn(date(2024, 1, 26), _formation_dates(sessions, "weekly"))

    def test_exact_rule_always_takes_current_top_twenty(self) -> None:
        ranked = tuple(f"security-{index:02d}" for index in range(40))
        prior = tuple(f"security-{index:02d}" for index in range(10, 30))
        self.assertEqual(
            select_portfolio(ranked, rule_key="exact_top20", prior=prior),
            ranked[:20],
        )

    def test_buffered_rule_retains_prior_names_inside_top_thirty_then_fills(self) -> None:
        ranked = tuple(f"security-{index:02d}" for index in range(40))
        prior = tuple(f"security-{index:02d}" for index in range(15, 35))
        selected = select_portfolio(
            ranked, rule_key="top20_entry_top30_retention", prior=prior,
        )
        self.assertEqual(len(selected), 20)
        self.assertEqual(len(set(selected)), 20)
        self.assertTrue(set(ranked[15:30]) <= set(selected))
        self.assertFalse(set(ranked[30:35]) & set(selected))
        self.assertEqual(set(selected) - set(ranked[15:30]), set(ranked[:5]))

    def test_summary_applies_cost_only_to_one_way_turnover(self) -> None:
        rows = (period(1, relative=0.02, turnover=1.0), period(2, relative=0.01, turnover=0.25))
        summary = summarize_periods(rows, {item.formation_date for item in rows})
        self.assertAlmostEqual(summary["mean_monthly_gross_relative_return"], 0.015)
        self.assertAlmostEqual(summary["mean_recurring_one_way_turnover"], 0.25)
        expected_25_bps = ((0.02 - 0.0025) + (0.01 - 0.25 * 0.0025)) / 2
        self.assertAlmostEqual(
            summary["mean_monthly_net_relative_return_by_one_way_cost_bps"]["25"],
            expected_25_bps,
        )


if __name__ == "__main__":
    unittest.main()
