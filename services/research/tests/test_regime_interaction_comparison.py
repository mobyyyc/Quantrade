import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from quantrade_research.challenger_model_comparison import ComparisonExample, Prediction
from quantrade_research.quality import DataQualityError
from quantrade_research.regime_interaction_comparison import (
    CHALLENGER_FEATURE_COLUMNS,
    fit_regime_interaction_elastic_net,
    load_examples,
    range_bound_metrics,
)
from quantrade_research.regime_interaction_features import (
    DATASET_KEY,
    DATASET_VERSION,
    FEATURE_DEFINITION_SHA256,
    INTERACTION_COLUMNS,
    MarketTrendSignal,
)
from quantrade_research.regularized_training import FEATURE_COLUMNS


class RegimeInteractionComparisonTests(unittest.TestCase):
    def test_fixed_elastic_net_uses_the_interaction_columns(self) -> None:
        rows = []
        for index in range(40):
            interaction = -0.5 + index / 39
            base = (0.5,) * len(FEATURE_COLUMNS)
            challenger = (*base, interaction, 0.0)
            rows.append(ComparisonExample(
                date(2024, 1, 31), f"security-{index:02d}", base, challenger,
                interaction * 0.2, interaction * 0.2, 0.0,
            ))
        model = fit_regime_interaction_elastic_net(rows)
        self.assertEqual(len(model.coefficients), len(CHALLENGER_FEATURE_COLUMNS))
        self.assertGreater(model.predict(rows[-1].challenger_features), model.predict(rows[0].challenger_features))

    def test_range_bound_metric_uses_only_frozen_range_bound_dates(self) -> None:
        range_date = date(2024, 1, 31)
        bullish_date = date(2024, 2, 29)
        predictions = (
            Prediction(1, range_date, "a", 0.0, 0.0, 0.0, 0.0),
            Prediction(1, range_date, "b", 1.0, 1.0, 1.0, 0.0),
            Prediction(1, bullish_date, "a", 1.0, 0.0, 0.0, 0.0),
            Prediction(1, bullish_date, "b", 0.0, 1.0, 1.0, 0.0),
        )
        signals = {
            range_date: MarketTrendSignal(Decimal("0.01"), Decimal("0.1"), ()),
            bullish_date: MarketTrendSignal(Decimal("0.10"), Decimal("0.3"), ()),
        }
        metrics = range_bound_metrics(predictions, signals)
        self.assertEqual(metrics["score_date_count"], 1)
        self.assertEqual(metrics["observation_count"], 2)
        self.assertEqual(metrics["mean_daily_spearman_ic"], Decimal("1.0"))

    def test_loader_rejects_a_holdout_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "dataset.csv"
            manifest = root / "dataset.json"
            fields = [
                "partition", "score_date", "security_id", "decision_at",
                "benchmark_relative_return", "security_return", "benchmark_return",
                *CHALLENGER_FEATURE_COLUMNS,
            ]
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                row = {
                    "partition": "holdout", "score_date": "2025-07-01", "security_id": "a",
                    "decision_at": datetime(2025, 7, 1, 20, tzinfo=timezone(timedelta(hours=-4))).isoformat(),
                    "benchmark_relative_return": "0", "security_return": "0", "benchmark_return": "0",
                }
                row.update({column: "0.5" for column in FEATURE_COLUMNS})
                row.update({column: "0" for column in INTERACTION_COLUMNS})
                writer.writerow(row)
            manifest.write_text(json.dumps({
                "dataset_key": DATASET_KEY,
                "dataset_version": DATASET_VERSION,
                "development_only": True,
                "holdout_used": False,
                "model_fitted": False,
                "interaction_definition_sha256": FEATURE_DEFINITION_SHA256,
                "interaction_columns": list(INTERACTION_COLUMNS),
                "point_in_time_violations": 0,
                "materialized_rows": 1,
                "content_sha256": sha256(dataset.read_bytes()).hexdigest(),
            }), encoding="utf-8")
            with self.assertRaisesRegex(DataQualityError, "non-development"):
                load_examples(dataset, manifest)


if __name__ == "__main__":
    unittest.main()
