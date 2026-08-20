from datetime import date, datetime, timezone
import unittest

from quantrade_research.experiments import ExperimentLog, ExperimentRecord, HoldoutPeriod
from quantrade_research.quality import DataQualityError


LOCKED_AT = datetime(2026, 8, 20, 20, tzinfo=timezone.utc)
HOLDOUT = HoldoutPeriod("0.1", date(2025, 7, 1), date(2026, 6, 30), LOCKED_AT, "completed recent year")


def record(experiment_id: str, validation_end: date) -> ExperimentRecord:
    return ExperimentRecord(
        experiment_id, LOCKED_AT, "0.1", "baseline_equal_weight_v1", "a" * 64,
        date(2024, 12, 31), validation_end, f"file:///results/{experiment_id}.json",
    )


class ExperimentGovernanceTests(unittest.TestCase):
    def test_accepts_only_pre_holdout_experiments_and_keeps_log_append_only(self) -> None:
        log = ExperimentLog(HOLDOUT)
        log.append(record("first", date(2025, 6, 30)))
        self.assertEqual([item.experiment_id for item in log.records()], ["first"])
        with self.assertRaisesRegex(DataQualityError, "already recorded"):
            log.append(record("first", date(2025, 6, 30)))
        with self.assertRaisesRegex(DataQualityError, "locked final holdout"):
            log.append(record("contaminated", date(2025, 7, 1)))

    def test_rejects_invalid_holdout_and_protocol_mismatch(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "start date"):
            HoldoutPeriod("0.1", date(2026, 1, 2), date(2026, 1, 1), LOCKED_AT, "bad")
        log = ExperimentLog(HOLDOUT)
        mismatched = ExperimentRecord(
            "wrong-protocol", LOCKED_AT, "0.2", "baseline_equal_weight_v1", "a" * 64,
            date(2024, 12, 31), date(2025, 6, 30), "file:///results/wrong.json",
        )
        with self.assertRaisesRegex(DataQualityError, "protocol"):
            log.append(mismatched)


if __name__ == "__main__":
    unittest.main()
