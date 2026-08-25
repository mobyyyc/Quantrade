from decimal import Decimal
import unittest

from quantrade_research.forward_outcomes import calculate_forward_returns
from quantrade_research.quality import DataQualityError


class ForwardScoreOutcomeTests(unittest.TestCase):
    def test_calculates_security_benchmark_and_relative_price_returns(self) -> None:
        security, benchmark, relative = calculate_forward_returns(
            security_entry_price=Decimal("100"), security_exit_price=Decimal("112"),
            benchmark_entry_price=Decimal("200"), benchmark_exit_price=Decimal("210"),
        )
        self.assertEqual(security, Decimal("0.12"))
        self.assertEqual(benchmark, Decimal("0.05"))
        self.assertEqual(relative, Decimal("0.07"))

    def test_rejects_non_positive_marks(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "positive"):
            calculate_forward_returns(
                security_entry_price=Decimal("0"), security_exit_price=Decimal("100"),
                benchmark_entry_price=Decimal("100"), benchmark_exit_price=Decimal("100"),
            )


if __name__ == "__main__":
    unittest.main()
