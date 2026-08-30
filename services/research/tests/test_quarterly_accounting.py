from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.quarterly_accounting import (
    endpoint_shares, latest_endpoint, standalone_quarters, true_ttm,
)
from quantrade_research.sec_fact_resolver import LEGACY_AVAILABILITY_RULE, ResolvedSecFact


UTC = timezone.utc


def fact(
    key: str, concept: str, value: str, start: date | None, end: date, fiscal_period: str | None,
    *, fiscal_year: int = 2024, taxonomy: str = "us-gaap", unit: str = "USD",
    form: str = "10-Q", available: datetime | None = None,
) -> ResolvedSecFact:
    timestamp = available or datetime(2025, 1, 1, tzinfo=UTC)
    return ResolvedSecFact(
        key, f"filing-{key}", "security", key, form, form.endswith("/A"), taxonomy, concept, unit,
        Decimal(value), start, end, fiscal_year, fiscal_period, timestamp, None, timestamp,
        LEGACY_AVAILABILITY_RULE, f"source:{key}", None, key.rjust(64, "0"),
    )


def fiscal_cycle(prefix: str, concept: str, start: date, ends: tuple[date, date, date, date], values):
    return [
        fact(f"{prefix}-{slot}", concept, str(value), start, end, slot, fiscal_year=end.year, form="10-K" if slot == "FY" else "10-Q")
        for slot, end, value in zip(("Q1", "Q2", "Q3", "FY"), ends, values, strict=True)
    ]


class QuarterlyAccountingTests(unittest.TestCase):
    def test_reconstructs_each_standalone_quarter_from_ytd_chain(self) -> None:
        facts = fiscal_cycle(
            "a", "NetIncomeLoss", date(2024, 1, 1),
            (date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31)),
            (10, 25, 45, 70),
        )
        values = standalone_quarters(facts, concept="NetIncomeLoss")
        self.assertEqual([item.value for item in values], [Decimal("10"), Decimal("15"), Decimal("20"), Decimal("25")])
        self.assertEqual([len(item.lineage) for item in values], [1, 2, 2, 2])

    def test_true_ttm_uses_four_consecutive_quarters_and_is_deterministic(self) -> None:
        facts = fiscal_cycle(
            "a", "NetIncomeLoss", date(2024, 1, 1),
            (date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31)),
            (10, 25, 45, 70),
        )
        result = true_ttm(facts, concepts=("NetIncomeLoss", "ProfitLoss"), formation_date=date(2025, 1, 31))
        replay = true_ttm(reversed(facts), concepts=("NetIncomeLoss", "ProfitLoss"), formation_date=date(2025, 1, 31))
        self.assertEqual(result.value, Decimal("70"))
        self.assertEqual(result.digest(), replay.digest())

    def test_missing_ytd_component_fails_closed(self) -> None:
        facts = fiscal_cycle(
            "a", "NetIncomeLoss", date(2024, 1, 1),
            (date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31)),
            (10, 25, 45, 70),
        )
        del facts[1]
        result = true_ttm(facts, concepts=("NetIncomeLoss",), formation_date=date(2025, 1, 31))
        self.assertFalse(result.available)
        self.assertEqual(result.exclusion, "missing_four_consecutive_eligible_standalone_quarters")

    def test_incompatible_fiscal_year_is_not_mixed(self) -> None:
        q1 = fact("q1", "NetIncomeLoss", "10", date(2024, 1, 1), date(2024, 3, 31), "Q1", fiscal_year=2024)
        h1 = fact("h1", "NetIncomeLoss", "25", date(2024, 1, 1), date(2024, 6, 30), "Q2", fiscal_year=2025)
        self.assertEqual(len(standalone_quarters((q1, h1), concept="NetIncomeLoss")), 1)

    def test_endpoint_shares_never_uses_weighted_average(self) -> None:
        weighted = fact(
            "weighted", "WeightedAverageNumberOfSharesOutstandingBasic", "100",
            date(2024, 1, 1), date(2024, 12, 31), "FY", taxonomy="us-gaap", unit="shares", form="10-K",
        )
        result = endpoint_shares((weighted,), formation_date=date(2025, 1, 31))
        self.assertFalse(result.available)
        self.assertEqual(result.exclusion, "missing_eligible_endpoint")

    def test_endpoint_shares_requires_dei_instant_fact(self) -> None:
        endpoint = fact(
            "shares", "EntityCommonStockSharesOutstanding", "125", None,
            date(2024, 12, 31), None, taxonomy="dei", unit="shares", form="10-K",
        )
        result = endpoint_shares((endpoint,), formation_date=date(2025, 1, 31))
        self.assertEqual(result.value, Decimal("125"))
        self.assertEqual(result.lineage[0].observation_hash, "shares".rjust(64, "0"))

    def test_latest_endpoint_rejects_conflicting_same_timestamp(self) -> None:
        timestamp = datetime(2025, 1, 1, tzinfo=UTC)
        facts = (
            fact("a", "Assets", "100", None, date(2024, 12, 31), "FY", form="10-K", available=timestamp),
            fact("b", "Assets", "101", None, date(2024, 12, 31), "FY", form="10-K", available=timestamp),
        )
        result = latest_endpoint(
            facts, concepts=("Assets",), taxonomy="us-gaap", unit="USD", formation_date=date(2025, 1, 31),
        )
        self.assertFalse(result.available)
        self.assertEqual(result.exclusion, "ambiguous_latest_endpoint_context")


if __name__ == "__main__":
    unittest.main()
