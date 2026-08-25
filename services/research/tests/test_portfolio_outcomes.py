from decimal import Decimal
import unittest

from quantrade_research.portfolio_outcomes import (
    PaperPortfolioPosition,
    calculate_paper_portfolio_return,
)
from quantrade_research.quality import DataQualityError


class PaperPortfolioOutcomeTests(unittest.TestCase):
    def test_calculates_mark_to_market_return_with_cash(self) -> None:
        value = calculate_paper_portfolio_return(
            starting_nav=Decimal("100"),
            ending_cash=Decimal("10"),
            positions=(PaperPortfolioPosition("a", Decimal("2")), PaperPortfolioPosition("b", Decimal("1"))),
            closing_prices={"a": Decimal("30"), "b": Decimal("50")},
        )
        self.assertEqual(value, Decimal("0.2"))

    def test_rejects_missing_or_non_positive_marks(self) -> None:
        positions = (PaperPortfolioPosition("a", Decimal("1")),)
        with self.assertRaisesRegex(DataQualityError, "missing closing"):
            calculate_paper_portfolio_return(
                starting_nav=Decimal("100"), ending_cash=Decimal("0"), positions=positions, closing_prices={},
            )
        with self.assertRaisesRegex(DataQualityError, "positive"):
            calculate_paper_portfolio_return(
                starting_nav=Decimal("100"), ending_cash=Decimal("0"), positions=positions,
                closing_prices={"a": Decimal("0")},
            )


if __name__ == "__main__":
    unittest.main()
