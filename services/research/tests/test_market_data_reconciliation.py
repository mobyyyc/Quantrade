from datetime import date
from decimal import Decimal
import unittest

from quantrade_research.market_data_reconciliation import ActionRecord, BarRecord, compare_actions, compare_bars


def bar(ticker: str, session: date, basis: str = "split_adjusted", close: str = "10") -> BarRecord:
    value = Decimal(close)
    return BarRecord(ticker, session, basis, value, value, value, value, Decimal("100"))


def action(identifier: str, *, amount: str = "0.25") -> ActionRecord:
    return ActionRecord(
        identifier, "AAPL", "cash_dividend", date(2026, 8, 20), date(2026, 8, 19),
        Decimal(amount), None, None,
    )


class MarketDataReconciliationTests(unittest.TestCase):
    def test_matching_bars_have_no_ledger_or_coverage_findings(self) -> None:
        session = date(2026, 8, 20)
        result = compare_bars([bar("AAPL", session)], [bar("AAPL", session)], symbols=["AAPL"], expected_sessions=[session])
        self.assertEqual(result["matched_row_count"], 1)
        self.assertEqual(result["missing_in_ledger_count"], 0)
        self.assertEqual(result["provider_session_gap_count"], 0)
        self.assertEqual(result["ledger_session_gap_count"], 0)

    def test_bar_comparison_separates_ledger_gaps_provider_gaps_and_revisions(self) -> None:
        first = date(2026, 8, 20)
        second = date(2026, 8, 21)
        result = compare_bars(
            [bar("AAPL", first, close="11")],
            [bar("AAPL", first, close="10"), bar("AAPL", second)],
            symbols=["AAPL"], expected_sessions=[first, second], sample_limit=1,
        )
        self.assertEqual(result["value_mismatch_count"], 1)
        self.assertEqual(result["missing_at_provider_count"], 1)
        self.assertEqual(result["provider_session_gap_count"], 1)
        self.assertEqual(result["ledger_session_gap_count"], 0)
        self.assertEqual(len(result["samples"]["value_mismatches"]), 1)

    def test_action_comparison_detects_missing_and_changed_dividends(self) -> None:
        result = compare_actions(
            [action("changed", amount="0.30"), action("missing")],
            [action("changed", amount="0.25"), action("old")],
        )
        self.assertEqual(result["missing_in_ledger_count"], 1)
        self.assertEqual(result["missing_at_provider_count"], 1)
        self.assertEqual(result["value_mismatch_count"], 1)

    def test_action_ticker_alias_does_not_change_provider_identity(self) -> None:
        provider = action("same")
        ledger = ActionRecord(
            provider.provider_action_id, "GOOGL", provider.action_type, provider.process_date,
            provider.effective_date, provider.cash_amount, provider.ratio_numerator, provider.ratio_denominator,
        )
        result = compare_actions([provider], [ledger])
        self.assertEqual(result["matched_action_count"], 1)
        self.assertEqual(result["value_mismatch_count"], 0)

    def test_irrelevant_actions_are_excluded(self) -> None:
        irrelevant = ActionRecord("name", "AAPL", "name_change", date(2026, 8, 20), None, None, None, None)
        result = compare_actions([irrelevant], [irrelevant])
        self.assertEqual(result["provider_action_count"], 0)
        self.assertEqual(result["ledger_action_count"], 0)


if __name__ == "__main__":
    unittest.main()
