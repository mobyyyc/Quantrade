from datetime import date
from datetime import datetime
from decimal import Decimal
import unittest

from quantrade_research.historical_replay import historical_decision_at, pending_session_dates, replayable_session_dates
from quantrade_research.feature_diagnostics import FeatureOutcome
from quantrade_research.features import FeatureRegistry, baseline_feature_registry
from quantrade_research.ranking import SectorClassification, build_sector_aware_percentile_ranks


class HistoricalReplayTests(unittest.TestCase):
    def test_uses_the_fixed_toronto_eight_pm_cutoff(self) -> None:
        decision = historical_decision_at(date(2024, 7, 2))
        self.assertEqual((decision.hour, decision.minute), (20, 0))
        self.assertEqual(decision.tzinfo.key, "America/Toronto")

    def test_sessions_are_sorted_deduplicated_and_bounded(self) -> None:
        sessions = replayable_session_dates(
            [date(2021, 1, 5), date(2021, 1, 4), date(2021, 1, 5), date(2020, 12, 31)],
            start_date=date(2021, 1, 4), end_date=date(2021, 1, 5),
        )
        self.assertEqual(sessions, (date(2021, 1, 4), date(2021, 1, 5)))

    def test_batch_selection_advances_past_completed_sessions(self) -> None:
        sessions = (date(2021, 1, 4), date(2021, 1, 5), date(2021, 1, 6))
        self.assertEqual(
            pending_session_dates(sessions, {date(2021, 1, 4)}, limit=1),
            (date(2021, 1, 5),),
        )

    def test_static_sector_grouping_is_explicitly_opt_in(self) -> None:
        formation = date(2021, 1, 4)
        decision = historical_decision_at(formation)
        definition = baseline_feature_registry().get("momentum_12_1", "v1")
        registry = FeatureRegistry((definition,))
        outcomes = [
            FeatureOutcome(security, formation, definition.key, definition.version, definition.definition_hash, Decimal(value))
            for security, value in (("a", "0.1"), ("b", "0.2"))
        ]
        classifications = [
            SectorClassification(security, "technology", date(2026, 8, 21), datetime(2026, 8, 21, tzinfo=decision.tzinfo))
            for security in ("a", "b")
        ]
        ranks = build_sector_aware_percentile_ranks(
            outcomes, classifications, formation_date=formation, decision_at=decision,
            universe_security_ids=("a", "b"), registry=registry,
            allow_static_tier_b_grouping=True,
        )
        self.assertEqual(len(ranks), 2)


if __name__ == "__main__":
    unittest.main()
