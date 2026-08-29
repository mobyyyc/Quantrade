import csv
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from quantrade_research.clean_monthly_baseline_panel import FEATURES, PANEL_KEY, PANEL_VERSION
from quantrade_research.clean_monthly_holdout_selection import freeze_clean_holdout_selection
from quantrade_research.quality import DataQualityError


class CleanMonthlyPipelineTests(unittest.TestCase):
    def _inputs(self, root: Path, *, exposed: bool = False):
        panel = root / "panel.csv"
        panel_manifest = root / "panel.json"
        model_artifact = root / "model.json"
        output = root / "selection.json"
        fields = [
            "partition", "formation_date", "decision_at", "security_id", "ticker",
            "sector_code", "baseline_rank", *FEATURES, "row_sha256",
        ]
        formations = (
            date(2025, month, 28) for month in range(7, 13)
        )
        formation_dates = [*formations, *(date(2026, month, 28) for month in range(1, 7))]
        with panel.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for formation in formation_dates:
                for index in range(20):
                    row = {
                        "partition": "holdout", "formation_date": formation.isoformat(),
                        "decision_at": formation.isoformat() + "T20:00:00+00:00",
                        "security_id": f"security-{index:02d}", "ticker": f"T{index:02d}",
                        "sector_code": "sector", "baseline_rank": str(index + 1),
                        "row_sha256": "a" * 64,
                    }
                    row.update({feature: str(index / 20) for feature in FEATURES})
                    writer.writerow(row)
        panel_hash = sha256(panel.read_bytes()).hexdigest()
        panel_manifest.write_text(json.dumps({
            "panel_key": PANEL_KEY, "panel_version": PANEL_VERSION,
            "content_sha256": panel_hash,
        }), encoding="utf-8")
        model_artifact.write_text(json.dumps({
            "model_version": "clean-test-model",
            "source_dataset": {"source_panel_sha256": panel_hash},
            "holdout_used": exposed, "holdout_evaluated": False,
            "feature_columns": [f"{feature}_percentile" for feature in FEATURES],
            "feature_means": [0.5] * len(FEATURES),
            "feature_scales": [1.0] * len(FEATURES),
            "coefficients": [1.0] + [0.0] * (len(FEATURES) - 1),
            "target_mean": 0.0,
        }), encoding="utf-8")
        return panel, panel_manifest, model_artifact, output

    def test_freezes_twelve_months_without_return_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            panel, manifest, model, output = self._inputs(Path(temporary))

            result = freeze_clean_holdout_selection(
                panel=panel, panel_manifest=manifest, model_artifact=model, output=output,
            )

            self.assertEqual(len(result["formations"]), 12)
            self.assertFalse(result["holdout_performance_evaluated"])
            self.assertEqual(len(result["formations"][0]["elastic_net"]), 20)
            payload = output.read_text(encoding="utf-8").lower()
            self.assertNotIn("benchmark_return", payload)
            self.assertNotIn("security_return", payload)

    def test_rejects_a_model_that_has_used_holdout_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            panel, manifest, model, output = self._inputs(Path(temporary), exposed=True)

            with self.assertRaisesRegex(DataQualityError, "not holdout-naive"):
                freeze_clean_holdout_selection(
                    panel=panel, panel_manifest=manifest, model_artifact=model, output=output,
                )


if __name__ == "__main__":
    unittest.main()
