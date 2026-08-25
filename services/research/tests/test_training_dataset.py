from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantrade_research.quality import DataQualityError
from quantrade_research.training_dataset import (
    TrainingDatasetRow,
    inspect_training_dataset,
    write_training_dataset_export,
)


def row(*, snapshot_id: str = "snapshot-1", feature_key: str = "momentum_12_1") -> TrainingDatasetRow:
    return TrainingDatasetRow(
        snapshot_id, "security-1", "ACME", "Acme Inc.", date(2026, 8, 20),
        datetime(2026, 8, 20, 20, tzinfo=timezone.utc), datetime(2026, 8, 20, 20, tzinfo=timezone.utc),
        "baseline_equal_weight_v1", "registry-hash", "0.1", "technology", Decimal("71"), 12,
        feature_key, "v1", "a" * 64, Decimal("0.8"), Decimal("0.1666666666666667"), Decimal("0.1333333333333334"),
        5, date(2026, 8, 21), date(2026, 8, 27), Decimal("0.06"), Decimal("0.02"), Decimal("0.04"),
        datetime(2026, 8, 27, 20, tzinfo=timezone.utc),
    )


class TrainingDatasetTests(unittest.TestCase):
    def test_inspects_complete_long_format_feature_examples(self) -> None:
        report = inspect_training_dataset((row(feature_key="momentum_12_1"), row(feature_key="return_on_assets_ttm")))
        self.assertEqual(report.training_example_count, 1)
        self.assertEqual(report.feature_row_count, 2)
        self.assertEqual(report.feature_identities, ("momentum_12_1@v1", "return_on_assets_ttm@v1"))

    def test_rejects_mismatched_or_duplicate_feature_schema(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "duplicate"):
            inspect_training_dataset((row(), row()))
        with self.assertRaisesRegex(DataQualityError, "complete feature schema"):
            inspect_training_dataset((row(snapshot_id="one"), row(snapshot_id="two", feature_key="return_on_assets_ttm")))

    def test_writes_csv_and_inspection_sidecar(self) -> None:
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "dataset.csv"
            report = write_training_dataset_export(rows=(row(),), destination=destination, horizon_sessions=5)
            self.assertEqual(report.training_example_count, 1)
            self.assertIn("benchmark_relative_return", destination.read_text(encoding="utf-8"))
            self.assertIn('"training_example_count": 1', destination.with_suffix(".json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
