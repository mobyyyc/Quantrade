from datetime import date, timedelta
from decimal import Decimal
import unittest

from quantrade_research.holdout_price_adapter import build_execution_period_input


IDS = tuple(f"id-{index:02d}" for index in range(20))


class FakePriceSource:
    def __init__(self, *, missing_exit: bool = False) -> None:
        self.missing_exit = missing_exit

    def require_corporate_action_coverage(self, start_date: date, end_date: date) -> None:
        return None

    def next_benchmark_session(self, formation_date: date) -> date:
        return formation_date + timedelta(days=1)

    def security_opens(self, security_ids: tuple[str, ...], session_date: date) -> dict[str, Decimal]:
        values = {security_id: Decimal("100") for security_id in security_ids}
        if self.missing_exit and session_date == date(2025, 9, 1):
            values.pop("id-00")
        return values

    def benchmark_open(self, session_date: date) -> Decimal:
        return Decimal("500")

    def corporate_action_security_ids(self, security_ids: tuple[str, ...], start_date: date, end_date: date) -> frozenset[str]:
        return frozenset()


def manifest() -> dict[str, object]:
    positions = [{"security_id": security_id} for security_id in IDS]
    return {
        "formations": [
            {"formation_date": "2025-07-31", "baseline": positions, "elastic_net": positions},
            {"formation_date": "2025-08-31", "baseline": positions, "elastic_net": positions},
        ]
    }


class HoldoutPriceAdapterTests(unittest.TestCase):
    def test_prepares_first_spy_open_to_next_frozen_execution_period(self) -> None:
        document = build_execution_period_input(manifest(), FakePriceSource())
        self.assertEqual(len(document["periods"]), 1)
        period = document["periods"][0]
        self.assertEqual(period["execution_date"], "2025-08-01")
        self.assertEqual(period["exit_date"], "2025-09-01")
        self.assertEqual(len(period["entry_prices"]), 20)
        self.assertEqual(document["withheld_formations"][-1]["formation_date"], "2025-08-31")

    def test_withholds_period_when_fixed_exit_open_is_missing(self) -> None:
        document = build_execution_period_input(manifest(), FakePriceSource(missing_exit=True))
        self.assertEqual(document["periods"], [])
        self.assertTrue(any("missing next-open" in item["reason"] for item in document["withheld_formations"]))


if __name__ == "__main__":
    unittest.main()
