from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.universe_symbols import canonical_ticker


class UniverseSymbolTests(unittest.TestCase):
    def test_prefers_a_simple_common_ticker_over_preferred_listings(self) -> None:
        self.assertEqual(canonical_ticker(["KMI", "EP-PC"]), "KMI")

    def test_prefers_class_b_when_only_class_tickers_are_available(self) -> None:
        self.assertEqual(canonical_ticker(["BRK-A", "BRK-B"]), "BRK-B")

    def test_is_stable_regardless_of_input_order(self) -> None:
        self.assertEqual(canonical_ticker(["GOOGL", "GOOG"]), "GOOG")


if __name__ == "__main__":
    unittest.main()
