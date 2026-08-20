from datetime import date
from decimal import Decimal
import unittest

from quantrade_research.baseline import BASELINE_MODEL_VERSION, CompositeBaselineScore
from quantrade_research.quality import DataQualityError
from quantrade_research.rebalance import (
    NextOpenPrice,
    PortfolioPosition,
    PortfolioState,
    RebalanceTarget,
    build_next_open_rebalance_ledger,
    select_equal_weight_targets,
)


FORMATION = date(2026, 8, 20)
EXECUTION = date(2026, 8, 21)


def score(security_id: str, value: str, *, eligible: bool = True) -> CompositeBaselineScore:
    return CompositeBaselineScore(
        security_id, FORMATION, BASELINE_MODEL_VERSION, "a" * 64, eligible,
        Decimal(value) if eligible else None, Decimal(value) * Decimal("100") if eligible else None,
        None if eligible else "required_feature_rank_unavailable",
    )


class NextOpenRebalanceTests(unittest.TestCase):
    def test_selects_top_eligible_scores_with_fixed_equal_weights(self) -> None:
        targets = select_equal_weight_targets(
            [score("a", "0.8"), score("b", "0.6"), score("c", "0.9", eligible=False)],
            formation_date=FORMATION,
            portfolio_size=2,
        )
        self.assertEqual([target.security_id for target in targets], ["a", "b"])
        self.assertEqual([target.target_weight for target in targets], [Decimal("0.5"), Decimal("0.5")])

    def test_sells_prior_positions_then_buys_targets_at_next_open(self) -> None:
        ledger = build_next_open_rebalance_ledger(
            PortfolioState(Decimal("100"), (PortfolioPosition("old", Decimal("10")),)),
            (RebalanceTarget("a", Decimal("0.5")), RebalanceTarget("b", Decimal("0.5"))),
            (
                NextOpenPrice("old", EXECUTION, Decimal("10")),
                NextOpenPrice("a", EXECUTION, Decimal("20")),
                NextOpenPrice("b", EXECUTION, Decimal("25")),
            ),
            formation_date=FORMATION,
            execution_date=EXECUTION,
        )
        self.assertEqual(ledger.starting_nav, Decimal("200"))
        self.assertEqual(ledger.ending_cash, Decimal("0"))
        self.assertEqual([(trade.security_id, trade.side, trade.quantity) for trade in ledger.trades], [
            ("old", "sell", Decimal("10")), ("a", "buy", Decimal("5")), ("b", "buy", Decimal("4")),
        ])

    def test_rejects_same_close_execution_and_missing_open(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "strictly after"):
            build_next_open_rebalance_ledger(
                PortfolioState(Decimal("100"), ()), (RebalanceTarget("a", Decimal("1")),),
                (NextOpenPrice("a", FORMATION, Decimal("10")),),
                formation_date=FORMATION, execution_date=FORMATION,
            )
        with self.assertRaisesRegex(DataQualityError, "missing next-open"):
            build_next_open_rebalance_ledger(
                PortfolioState(Decimal("100"), ()), (RebalanceTarget("a", Decimal("1")),), (),
                formation_date=FORMATION, execution_date=EXECUTION,
            )


if __name__ == "__main__":
    unittest.main()
