from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import unittest
from zoneinfo import ZoneInfo

from quantrade_research.baseline import BASELINE_MODEL_VERSION, CompositeBaselineScore
from quantrade_research.quality import DataQualityError
from quantrade_research.scoring import InMemoryScoreSnapshotRepository, generate_end_of_day_scores


TORONTO = ZoneInfo("America/Toronto")
SCORE_DATE = date(2026, 8, 20)
DECISION = datetime(2026, 8, 20, 20, tzinfo=TORONTO)


def scores() -> tuple[CompositeBaselineScore, ...]:
    return (
        CompositeBaselineScore("a", SCORE_DATE, BASELINE_MODEL_VERSION, "a" * 64, True, Decimal("0.8"), Decimal("80")),
        CompositeBaselineScore("b", SCORE_DATE, BASELINE_MODEL_VERSION, "a" * 64, True, Decimal("0.5"), Decimal("50")),
        CompositeBaselineScore("c", SCORE_DATE, BASELINE_MODEL_VERSION, "a" * 64, False, None, None, "required_feature_rank_unavailable=x"),
    )


class EndOfDayScoreTests(unittest.TestCase):
    def test_generates_ranked_snapshots_idempotently(self) -> None:
        repository = InMemoryScoreSnapshotRepository()
        first = generate_end_of_day_scores(
            scores(), repository, score_date=SCORE_DATE, decision_at=DECISION, published_at=DECISION,
            data_cutoff_at=DECISION, data_capability_tier="B",
        )
        second = generate_end_of_day_scores(
            scores(), repository, score_date=SCORE_DATE, decision_at=DECISION, published_at=DECISION,
            data_cutoff_at=DECISION, data_capability_tier="B",
        )
        self.assertEqual(first, second)
        by_security = {snapshot.security_id: snapshot for snapshot in first}
        self.assertEqual(by_security["a"].rank, 1)
        self.assertEqual(by_security["b"].rank, 2)
        self.assertEqual(by_security["c"].signal, "unavailable")

    def test_rejects_conflicting_repeats_and_wrong_schedule(self) -> None:
        repository = InMemoryScoreSnapshotRepository()
        generate_end_of_day_scores(
            scores(), repository, score_date=SCORE_DATE, decision_at=DECISION, published_at=DECISION,
            data_cutoff_at=DECISION, data_capability_tier="B",
        )
        changed = list(scores())
        changed[0] = replace(changed[0], display_score=Decimal("79"), normalized_score=Decimal("0.79"))
        with self.assertRaisesRegex(DataQualityError, "conflicting"):
            generate_end_of_day_scores(
                changed, repository, score_date=SCORE_DATE, decision_at=DECISION, published_at=DECISION,
                data_cutoff_at=DECISION, data_capability_tier="B",
            )

    def test_allows_a_private_manual_run_after_market_close(self) -> None:
        snapshots = generate_end_of_day_scores(
            scores(), InMemoryScoreSnapshotRepository(), score_date=SCORE_DATE,
            decision_at=datetime(2026, 8, 20, 20, 6, tzinfo=TORONTO),
            published_at=datetime(2026, 8, 20, 20, 6, tzinfo=TORONTO),
            data_cutoff_at=datetime(2026, 8, 20, 20, 6, tzinfo=TORONTO),
            data_capability_tier="B", manual=True,
        )
        self.assertEqual(len(snapshots), 3)
        with self.assertRaisesRegex(DataQualityError, "8:00"):
            generate_end_of_day_scores(
                scores(), InMemoryScoreSnapshotRepository(), score_date=SCORE_DATE,
                decision_at=datetime(2026, 8, 20, 19, tzinfo=TORONTO), published_at=DECISION,
                data_cutoff_at=DECISION, data_capability_tier="B",
            )


if __name__ == "__main__":
    unittest.main()
