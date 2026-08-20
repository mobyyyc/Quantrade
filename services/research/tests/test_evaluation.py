from datetime import date
from decimal import Decimal
import unittest

from quantrade_research.evaluation import (
    LiquiditySnapshot, NavObservation, calculate_performance_metrics,
    rebalance_cost_report, validate_rebalance_liquidity,
)
from quantrade_research.quality import DataQualityError
from quantrade_research.rebalance import (
    NextOpenPrice, PortfolioPosition, PortfolioState, RebalanceTarget,
    build_next_open_rebalance_ledger,
)


FORMATION = date(2026, 8, 20)
EXECUTION = date(2026, 8, 21)


def targets() -> tuple[RebalanceTarget, ...]:
    return (RebalanceTarget("a", Decimal("0.5")), RebalanceTarget("b", Decimal("0.5")))


def ledger():
    return build_next_open_rebalance_ledger(
        PortfolioState(Decimal("100"), (PortfolioPosition("old", Decimal("10")),)),
        targets(),
        (NextOpenPrice("old", EXECUTION, Decimal("10")), NextOpenPrice("a", EXECUTION, Decimal("20")), NextOpenPrice("b", EXECUTION, Decimal("25"))),
        formation_date=FORMATION, execution_date=EXECUTION,
    )


class EvaluationTests(unittest.TestCase):
    def test_enforces_liquidity_floor_for_every_target(self) -> None:
        validate_rebalance_liquidity(
            targets(), (LiquiditySnapshot("a", FORMATION, Decimal("10000000")), LiquiditySnapshot("b", FORMATION, Decimal("12000000"))),
            formation_date=FORMATION,
        )
        with self.assertRaisesRegex(DataQualityError, "floor"):
            validate_rebalance_liquidity(
                targets(), (LiquiditySnapshot("a", FORMATION, Decimal("9999999")), LiquiditySnapshot("b", FORMATION, Decimal("12000000"))),
                formation_date=FORMATION,
            )

    def test_reports_baseline_cost_and_required_sensitivities(self) -> None:
        report = rebalance_cost_report(ledger())
        self.assertEqual(report.gross_trade_notional, Decimal("300"))
        self.assertEqual(report.one_way_turnover, Decimal("1"))
        self.assertEqual(report.baseline.total_cost, Decimal("0.15"))
        self.assertEqual([item.one_way_cost_bps for item in report.sensitivities], [Decimal("1"), Decimal("10"), Decimal("20")])

    def test_calculates_portfolio_and_benchmark_metrics(self) -> None:
        metrics = calculate_performance_metrics((
            NavObservation(date(2026, 8, 20), Decimal("100"), Decimal("100")),
            NavObservation(date(2026, 8, 21), Decimal("110"), Decimal("105")),
            NavObservation(date(2026, 8, 22), Decimal("99"), Decimal("100")),
        ))
        self.assertEqual(metrics.portfolio_cumulative_return, Decimal("-0.01"))
        self.assertEqual(metrics.benchmark_cumulative_return, Decimal("0"))
        self.assertEqual(metrics.benchmark_relative_return, Decimal("-0.01"))
        self.assertEqual(metrics.maximum_drawdown, Decimal("-0.1"))

    def test_rejects_invalid_metric_series(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "at least two"):
            calculate_performance_metrics((NavObservation(FORMATION, Decimal("100"), Decimal("100")),))


if __name__ == "__main__":
    unittest.main()
