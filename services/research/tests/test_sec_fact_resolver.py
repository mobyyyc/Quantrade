from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.sec_fact_resolver import (
    LEGACY_AVAILABILITY_RULE, OBSERVED_AVAILABILITY_RULE,
    ResolvedSecFact, resolve_facts_as_of,
)


def fact(key: str, accession: str, available: datetime, value: str, *, observed=None, amendment=False):
    return ResolvedSecFact(
        key, "filing-" + accession, "security-1", accession, "10-Q/A" if amendment else "10-Q",
        amendment, "us-gaap", "Assets", "USD", Decimal(value), date(2026, 1, 1), date(2026, 6, 30),
        2026, "Q2", datetime(2026, 8, 1, 20, 0, tzinfo=timezone.utc), observed, available,
        OBSERVED_AVAILABILITY_RULE if observed else LEGACY_AVAILABILITY_RULE,
        "https://sec.example/" + accession, None,
    )


class SecFactResolverTests(unittest.TestCase):
    def test_later_observation_cannot_enter_an_earlier_decision(self) -> None:
        early = fact("same-key", "0001", datetime(2026, 8, 1, 20, 5, tzinfo=timezone.utc), "100")
        late = fact(
            "same-key", "0001", datetime(2026, 8, 2, 2, 0, tzinfo=timezone.utc), "110",
            observed=datetime(2026, 8, 2, 2, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            resolve_facts_as_of([early, late], decision_at=datetime(2026, 8, 1, 23, 0, tzinfo=timezone.utc))[0].value,
            Decimal("100"),
        )
        self.assertEqual(
            resolve_facts_as_of([early, late], decision_at=datetime(2026, 8, 2, 3, 0, tzinfo=timezone.utc))[0].value,
            Decimal("110"),
        )

    def test_amendment_is_preserved_as_a_separate_accession_fact(self) -> None:
        original = fact("original", "0001", datetime(2026, 8, 1, 20, 5, tzinfo=timezone.utc), "100")
        amendment = fact(
            "amendment", "0002", datetime(2026, 8, 3, 20, 5, tzinfo=timezone.utc), "105", amendment=True,
        )
        resolved = resolve_facts_as_of(
            [original, amendment], decision_at=datetime(2026, 8, 3, 21, 0, tzinfo=timezone.utc),
        )
        self.assertEqual({item.accession_number for item in resolved}, {"0001", "0002"})
        self.assertTrue(next(item for item in resolved if item.accession_number == "0002").is_amendment)

    def test_rejects_naive_decision_timestamp(self) -> None:
        with self.assertRaisesRegex(Exception, "UTC offset"):
            resolve_facts_as_of([], decision_at=datetime(2026, 8, 1, 20, 0))


if __name__ == "__main__":
    unittest.main()
