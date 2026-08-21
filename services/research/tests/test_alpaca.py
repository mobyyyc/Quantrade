from datetime import date
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.alpaca import AlpacaError, parse_corporate_actions, parse_daily_bars


class AlpacaAdapterTests(unittest.TestCase):
    def test_parses_daily_bar_page_and_token(self) -> None:
        payload = b'{"bars":{"AAPL":[{"t":"2026-08-20T00:00:00Z","o":225.1,"h":228,"l":224,"c":227.5,"v":12345}]},"next_page_token":"next"}'
        bars, token = parse_daily_bars(payload)
        self.assertEqual(token, "next")
        self.assertEqual(bars[0].ticker, "AAPL")
        self.assertEqual(bars[0].session_date, date(2026, 8, 20))
        self.assertEqual(str(bars[0].close_price), "227.5")

    def test_normalizes_alpaca_share_class_symbol(self) -> None:
        payload = b'{"bars":{"BRK.B":[{"t":"2026-08-20T00:00:00Z","o":450,"h":455,"l":449,"c":454,"v":12345}]}}'
        bars, token = parse_daily_bars(payload)
        self.assertIsNone(token)
        self.assertEqual(bars[0].ticker, "BRK-B")

    def test_parses_dividend_and_split_actions(self) -> None:
        payload = b'{"cash_dividends":[{"id":"div-1","symbol":"AAPL","process_date":"2026-08-20","ex_date":"2026-08-19","cash":"0.25"}],"forward_splits":[{"id":"split-1","symbol":"AAPL","process_date":"2026-08-20","ex_date":"2026-08-19","ratio":{"numerator":4,"denominator":1}}],"next_page_token":null}'
        actions, token = parse_corporate_actions(payload)
        self.assertIsNone(token)
        self.assertEqual(actions[0].action_type, "cash_dividend")
        self.assertEqual(str(actions[0].cash_amount), "0.25")
        self.assertEqual(actions[1].action_type, "forward_split")
        self.assertEqual(str(actions[1].ratio_numerator), "4")

    def test_rejects_bar_without_price(self) -> None:
        with self.assertRaises(AlpacaError):
            parse_daily_bars(b'{"bars":{"AAPL":[{"t":"2026-08-20T00:00:00Z"}]}}')


if __name__ == "__main__":
    unittest.main()
