import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from quantrade_research.quality import DataQualityError
from quantrade_research.regime_interaction_features import (
    BenchmarkBar,
    INTERACTION_COLUMNS,
    calculate_interactions,
    calculate_market_trend_signal,
    materialize_regime_interaction_dataset,
)


DECISION = datetime(2024, 3, 1, 20, 0, tzinfo=timezone(timedelta(hours=-5)))


def bars(*, final_close: str = "130") -> tuple[BenchmarkBar, ...]:
    start = date(2024, 1, 1)
    values = []
    for index in range(61):
        close = Decimal("100") if index == 0 else Decimal("110")
        if index == 60:
            close = Decimal(final_close)
        values.append(BenchmarkBar(start + timedelta(days=index), close, DECISION - timedelta(hours=2)))
    return tuple(values)


class RegimeInteractionFeatureTests(unittest.TestCase):
    def test_signal_is_clipped_and_rejects_a_late_revision(self) -> None:
        history = bars(final_close="150")
        history = (*history, BenchmarkBar(history[-1].session_date, Decimal("1"), DECISION + timedelta(minutes=1)))
        signal = calculate_market_trend_signal(
            score_date=history[-1].session_date, decision_at=DECISION, bars=history,
        )
        self.assertEqual(signal.raw_return, Decimal("0.5"))
        self.assertEqual(signal.normalized_signal, Decimal("1"))
        self.assertNotIn(history[-1], signal.used_bars)

    def test_signal_requires_the_same_session_close(self) -> None:
        history = bars()
        with self.assertRaisesRegex(DataQualityError, "missing_same_session_spy_close"):
            calculate_market_trend_signal(
                score_date=history[-1].session_date + timedelta(days=1),
                decision_at=DECISION,
                bars=history,
            )

    def test_interactions_follow_the_frozen_centered_formula(self) -> None:
        result = calculate_interactions(Decimal("0.9"), Decimal("0.2"), Decimal("0.5"))
        self.assertEqual(result, (Decimal("0.20"), Decimal("-0.15")))
        with self.assertRaises(DataQualityError):
            calculate_interactions(Decimal("1.1"), Decimal("0.2"), Decimal("0.5"))

    def test_materialization_is_development_only_and_provenanced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.csv"
            manifest = root / "source.json"
            output = root / "output.csv"
            score_date = bars()[-1].session_date
            fields = [
                "partition", "score_date", "security_id", "decision_at", "feature_registry_hash",
                "momentum_12_1_percentile", "relative_strength_6m_percentile",
            ]
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                for security, momentum, strength in (("a", "0.9", "0.2"), ("b", "0.1", "0.8")):
                    writer.writerow({
                        "partition": "development", "score_date": score_date.isoformat(),
                        "security_id": security, "decision_at": DECISION.isoformat(),
                        "feature_registry_hash": "a" * 64,
                        "momentum_12_1_percentile": momentum,
                        "relative_strength_6m_percentile": strength,
                    })
                writer.writerow({
                    "partition": "holdout", "score_date": "2025-07-01", "security_id": "c",
                    "decision_at": DECISION.isoformat(), "feature_registry_hash": "a" * 64,
                    "momentum_12_1_percentile": "0.5", "relative_strength_6m_percentile": "0.5",
                })
            manifest.write_text(json.dumps({
                "dataset_key": "sp500_current_survivors_20d", "dataset_version": "v1",
                "content_sha256": sha256(source.read_bytes()).hexdigest(), "limitations": ["Tier B"],
                "development_row_count": 2,
            }), encoding="utf-8")
            metadata = materialize_regime_interaction_dataset(
                source=source, source_manifest=manifest, destination=output, bars=bars(),
            )
            with output.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(column in rows[0] for column in INTERACTION_COLUMNS))
            self.assertEqual(metadata["coverage"], "1")
            self.assertFalse(metadata["holdout_used"])
            self.assertFalse(metadata["model_fitted"])
            self.assertEqual(metadata["point_in_time_violations"], 0)


if __name__ == "__main__":
    unittest.main()
