from datetime import date, datetime, timezone
from decimal import Decimal
import unittest

from quantrade_research.quality import DataQualityError
from quantrade_research.wealth_ledger import (
    WealthAction,
    WealthPriceMark,
    calculate_relative_wealth_return,
    calculate_wealth_return,
)


UTC = timezone.utc
ENTRY = date(2024, 1, 2)
EXIT = date(2024, 2, 1)
AVAILABLE = datetime(2024, 2, 1, 23, tzinfo=UTC)


def action(action_id: str, action_type: str, event: date | None, **values) -> WealthAction:
    return WealthAction(
        action_id, action_type, event, event or EXIT, AVAILABLE,
        cash_amount=values.get("cash_amount"),
        ratio_numerator=values.get("ratio_numerator"),
        ratio_denominator=values.get("ratio_denominator"),
    )


def calculate(actions=(), *, entry=Decimal("100"), exit_value=Decimal("110")):
    return calculate_wealth_return(
        entry_date=ENTRY, exit_date=EXIT, entry_price=entry, exit_price=exit_value,
        entry_available_at=AVAILABLE, exit_available_at=AVAILABLE, actions=actions,
    )


class WealthLedgerTests(unittest.TestCase):
    def test_calculates_price_only_wealth(self) -> None:
        result = calculate()
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.wealth_return, Decimal("0.1"))
        self.assertEqual(result.ending_quantity, Decimal("1"))
        self.assertEqual(result.cash_distributions, Decimal("0"))

    def test_adds_cash_dividend_without_reinvestment(self) -> None:
        result = calculate((action("d1", "cash_dividend", date(2024, 1, 15), cash_amount=Decimal("2")),))
        self.assertEqual(result.wealth_return, Decimal("0.12"))
        self.assertEqual(result.cash_distributions, Decimal("2"))

    def test_applies_split_before_same_day_dividend(self) -> None:
        result = calculate((
            action("d1", "cash_dividend", date(2024, 1, 15), cash_amount=Decimal("1")),
            action("s1", "forward_split", date(2024, 1, 15), ratio_numerator=Decimal("2"), ratio_denominator=Decimal("1")),
        ), exit_value=Decimal("55"))
        self.assertEqual(result.ending_quantity, Decimal("2"))
        self.assertEqual(result.cash_distributions, Decimal("2"))
        self.assertEqual(result.wealth_return, Decimal("0.12"))
        self.assertEqual(result.action_ids, ("s1", "d1"))

    def test_entry_date_action_is_already_reflected_in_entry_open(self) -> None:
        result = calculate((
            action("s1", "forward_split", ENTRY, ratio_numerator=Decimal("2"), ratio_denominator=Decimal("1")),
        ))
        self.assertEqual(result.action_ids, ())
        self.assertEqual(result.ending_quantity, Decimal("1"))

    def test_exit_date_dividend_is_included(self) -> None:
        result = calculate((action("d1", "cash_dividend", EXIT, cash_amount=Decimal("2")),))
        self.assertEqual(result.cash_distributions, Decimal("2"))

    def test_withholds_complex_or_undated_actions(self) -> None:
        complex_result = calculate((action("x1", "spin_off", date(2024, 1, 10)),))
        self.assertEqual(complex_result.status, "withheld")
        self.assertIn("spin_off", complex_result.unavailable_reason)
        undated_result = calculate((action("x2", "cash_dividend", None, cash_amount=Decimal("1")),))
        self.assertEqual(undated_result.status, "withheld")
        self.assertIn("no effective date", undated_result.unavailable_reason)

    def test_withholds_incomplete_split_or_invalid_dividend(self) -> None:
        split = calculate((action("s1", "forward_split", date(2024, 1, 10)),))
        self.assertEqual(split.status, "withheld")
        dividend = calculate((action("d1", "cash_dividend", date(2024, 1, 10), cash_amount=Decimal("-1")),))
        self.assertEqual(dividend.status, "withheld")

    def test_rejects_bad_window_marks_and_duplicate_actions(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "follow"):
            calculate_wealth_return(
                entry_date=EXIT, exit_date=ENTRY, entry_price=Decimal("1"), exit_price=Decimal("1"),
                entry_available_at=AVAILABLE, exit_available_at=AVAILABLE, actions=(),
            )
        with self.assertRaisesRegex(DataQualityError, "unique"):
            calculate((
                action("d1", "cash_dividend", date(2024, 1, 10), cash_amount=Decimal("1")),
                action("d1", "cash_dividend", date(2024, 1, 20), cash_amount=Decimal("1")),
            ))

    def test_relative_result_withholds_if_either_leg_is_withheld(self) -> None:
        security = calculate()
        benchmark = calculate((action("x", "spin_off", date(2024, 1, 10)),))
        relative = calculate_relative_wealth_return(security, benchmark)
        self.assertEqual(relative.status, "withheld")
        self.assertIsNone(relative.benchmark_relative_return)

    def test_digest_is_deterministic(self) -> None:
        first = calculate((action("d1", "cash_dividend", date(2024, 1, 15), cash_amount=Decimal("2")),))
        second = calculate((action("d1", "cash_dividend", date(2024, 1, 15), cash_amount=Decimal("2")),))
        self.assertEqual(first.digest, second.digest)

    def test_withholds_unexplained_structural_price_jump(self) -> None:
        result = calculate_wealth_return(
            entry_date=ENTRY, exit_date=EXIT, entry_price=Decimal("100"), exit_price=Decimal("50"),
            entry_available_at=AVAILABLE, exit_available_at=AVAILABLE, actions=(),
            intermediate_prices=(
                WealthPriceMark(ENTRY, Decimal("100"), AVAILABLE),
                WealthPriceMark(date(2024, 1, 15), Decimal("50"), AVAILABLE),
                WealthPriceMark(EXIT, Decimal("50"), AVAILABLE),
            ),
        )
        self.assertEqual(result.status, "withheld")
        self.assertIn("structural price discontinuity", result.unavailable_reason)

    def test_known_split_reconciles_structural_price_jump(self) -> None:
        split = action(
            "s1", "forward_split", date(2024, 1, 15),
            ratio_numerator=Decimal("2"), ratio_denominator=Decimal("1"),
        )
        result = calculate_wealth_return(
            entry_date=ENTRY, exit_date=EXIT, entry_price=Decimal("100"), exit_price=Decimal("55"),
            entry_available_at=AVAILABLE, exit_available_at=AVAILABLE, actions=(split,),
            intermediate_prices=(
                WealthPriceMark(ENTRY, Decimal("100"), AVAILABLE),
                WealthPriceMark(date(2024, 1, 15), Decimal("50"), AVAILABLE),
                WealthPriceMark(EXIT, Decimal("55"), AVAILABLE),
            ),
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.wealth_return, Decimal("0.1"))


if __name__ == "__main__":
    unittest.main()
