from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.phase_9c_model_dataset import (
    LabelPriceBar, LabelWindow, _exclusion_category, _label_outcome,
    build_nested_folds, centered_label_ranks,
)
from quantrade_research.wealth_ledger import WealthAction


UTC = timezone.utc


def bar(owner: str, session: date, price: str) -> LabelPriceBar:
    return LabelPriceBar(
        f"{owner}|{session.isoformat()}", owner, session, Decimal(price),
        datetime.combine(session, datetime.min.time(), tzinfo=UTC),
    )


class Phase9CModelDatasetTests(unittest.TestCase):
    def test_label_ranks_are_centered_tie_aware_and_deterministic(self) -> None:
        ranks = centered_label_ranks({
            "c": Decimal("3"), "a": Decimal("1"), "b": Decimal("1"), "d": Decimal("4"),
        })
        self.assertEqual(ranks["a"], ranks["b"])
        self.assertLess(abs(ranks["a"] - Decimal("-2") / Decimal("3")), Decimal("1e-26"))
        self.assertLess(abs(ranks["c"] - Decimal("1") / Decimal("3")), Decimal("1e-26"))
        self.assertEqual(ranks["d"], Decimal("1"))

    def test_label_uses_explicit_cash_dividend_wealth_and_full_lineage(self) -> None:
        formation = date(2024, 1, 5)
        sessions = tuple(formation + timedelta(days=index) for index in range(1, 22))
        window = LabelWindow(formation, sessions[0], sessions[-1], sessions)
        security = {
            session: bar("stock", session, str(Decimal("10") + Decimal(index) / Decimal("20")))
            for index, session in enumerate(sessions)
        }
        benchmark = {
            session: bar("SPY", session, str(Decimal("100") + Decimal(index) / Decimal("4")))
            for index, session in enumerate(sessions)
        }
        dividend = WealthAction(
            "dividend", "cash_dividend", sessions[10], sessions[10],
            datetime.combine(sessions[10], datetime.min.time(), tzinfo=UTC),
            cash_amount=Decimal("1"), currency="USD",
        )
        outcome, reason = _label_outcome(
            security_id="stock", window=window, security_prices=security,
            benchmark_prices=benchmark, security_actions=(dividend,), benchmark_actions=(),
        )
        self.assertIsNone(reason)
        assert outcome is not None
        self.assertEqual(outcome.security_return, Decimal("0.2"))
        self.assertEqual(outcome.benchmark_return, Decimal("0.05"))
        self.assertEqual(outcome.benchmark_relative_return, Decimal("0.15"))
        self.assertEqual(len(outcome.lineage["security_bar_ids"]), 21)
        self.assertEqual(outcome.lineage["security_action_ids"], ["dividend"])

    def test_missing_intermediate_mark_withholds_label(self) -> None:
        formation = date(2024, 1, 5)
        sessions = tuple(formation + timedelta(days=index) for index in range(1, 22))
        window = LabelWindow(formation, sessions[0], sessions[-1], sessions)
        security = {session: bar("stock", session, "10") for session in sessions if session != sessions[5]}
        benchmark = {session: bar("SPY", session, "100") for session in sessions}
        outcome, reason = _label_outcome(
            security_id="stock", window=window, security_prices=security,
            benchmark_prices=benchmark, security_actions=(), benchmark_actions=(),
        )
        self.assertIsNone(outcome)
        self.assertEqual(reason, "missing_complete_security_price_path")

    def test_exclusion_details_are_aggregated_without_losing_the_reason_class(self) -> None:
        self.assertEqual(
            _exclusion_category("unexplained structural price discontinuity on 2024-01-01: 0.5"),
            "unexplained_structural_price_discontinuity",
        )
        self.assertEqual(
            _exclusion_category("unresolved complex corporate action: cash_merger"),
            "unresolved_complex_corporate_action:cash_merger",
        )

    def test_nested_folds_purge_every_overlapping_outcome(self) -> None:
        formations = []
        current = date(2022, 1, 7)
        while current <= date(2025, 5, 30):
            formations.append(current)
            current += timedelta(days=7)
        outcomes = {formation: formation + timedelta(days=28) for formation in formations}
        counts = {formation: 450 for formation in formations}
        report = build_nested_folds(outcomes, counts)
        self.assertEqual(report["label_overlap_violations"], 0)
        self.assertEqual(len(report["outer_folds"]), 4)
        for outer in report["outer_folds"]:
            self.assertEqual(len(outer["inner_folds"]), 3)
            validation_start = date.fromisoformat(outer["validation_formations"][0])
            self.assertTrue(all(
                outcomes[date.fromisoformat(item)] < validation_start
                for item in outer["training_formations"]
            ))
            for inner in outer["inner_folds"]:
                inner_start = date.fromisoformat(inner["validation_formations"][0])
                self.assertTrue(all(
                    outcomes[date.fromisoformat(item)] < inner_start
                    for item in inner["training_formations"]
                ))


if __name__ == "__main__":
    unittest.main()
