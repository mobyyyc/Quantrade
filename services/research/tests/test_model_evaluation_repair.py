from dataclasses import replace
from datetime import date
from pathlib import Path
import tempfile
import csv
import gzip
import unittest
from unittest.mock import patch

from quantrade_research.model_evaluation_repair import (
    validate_rows, reference_training, select_configuration, bootstrap, fit_reference, run,
    attach_full_universe, tune, CHALLENGER,
)
from quantrade_research.phase_9c_model_comparison import Example
from quantrade_research.phase_9c_model_comparison import run_comparison
from quantrade_research.monthly_model_comparison import Example as MonthlyExample
from quantrade_research.quality import DataQualityError


class EvaluationRepairTests(unittest.TestCase):
    def test_superseded_reference_cannot_accidentally_run(self):
        with self.assertRaisesRegex(DataQualityError, "archival"):
            run_comparison(database_url="unused", dataset=Path("unused"),
                           feature_panel=Path("unused"), destination=Path("unused"))

    def setUp(self):
        self.rows = [Example(date(2023, m, 3), f"2023-{m:02d}", "a", .1, .02,
                             1, (.1,) * 6, "hash") for m in (1, 3)]
        self.sources = {(r.formation_date, r.security_id): {
            "entry_date": f"2023-{r.formation_date.month:02d}-04",
            "outcome_date": f"2023-{r.formation_date.month:02d}-28",
        } for r in self.rows}
        self.split = {"training_formations": ["2023-01-03"],
                      "validation_formations": ["2023-03-03"], "inner_folds": []}

    def test_actual_outcome_purge_not_just_manifest_counter(self):
        validate_rows(self.rows, self.sources, {"outer_folds": [self.split]})
        self.sources[date(2023, 1, 3), "a"]["outcome_date"] = "2023-03-03"
        with self.assertRaisesRegex(DataQualityError, "overlaps"):
            validate_rows(self.rows, self.sources, {"outer_folds": [self.split]})

    def test_holdout_and_nonfinite_rejected(self):
        self.sources[date(2023, 3, 3), "a"]["outcome_date"] = "2025-07-01"
        with self.assertRaisesRegex(DataQualityError, "holdout"):
            validate_rows(self.rows, self.sources, {"outer_folds": [self.split]})
        self.setUp()
        self.rows[0] = replace(self.rows[0], target=float("nan"))
        with self.assertRaisesRegex(DataQualityError, "non-finite"):
            validate_rows(self.rows, self.sources, {"outer_folds": [self.split]})

    def test_missing_and_duplicate_fold_dates_rejected(self):
        self.split["training_formations"] += ["2023-01-03"]
        with self.assertRaises(DataQualityError):
            validate_rows(self.rows, self.sources, {"outer_folds": [self.split]})
        self.split["training_formations"] = ["2022-01-03"]
        with self.assertRaises(DataQualityError):
            validate_rows(self.rows, self.sources, {"outer_folds": [self.split]})

    def test_reference_fit_cannot_see_later_rows(self):
        monthly = [MonthlyExample(date(2022, m, 1), date(2022, m, 28), str(i),
                                 tuple((i + j) / 10 for j in range(6)), (), (),
                                 i / 100, 0, 0, .1, 0, 0)
                   for m in range(1, 10) for i in range(10)]
        split = {"training_formations": ["2022-01-01", "2022-06-01"],
                 "validation_formations": ["2022-07-01"]}
        selected = reference_training(monthly, split)
        changed = [replace(x, target=9999, base=(9999,) * 6) if x.formation_date.month > 6 else x for x in monthly]
        self.assertEqual(fit_reference(selected, (.001, .001)),
                         fit_reference(reference_training(changed, split), (.001, .001)))
        self.assertEqual(max(x.formation_date for x in selected), date(2022, 6, 1))

    def test_regularization_tie_and_bootstrap_determinism(self):
        self.assertEqual(select_configuration([
            {"configuration": .1, "mean_monthly_rank_ic": .05},
            {"configuration": 10, "mean_monthly_rank_ic": .049},
        ]), 10)
        values = [.01, -.01, .02, .01, .03, -.02]
        self.assertEqual(bootstrap(values), bootstrap(values))

    def test_immutable_output_rejected_before_any_data_or_database_access(self):
        with tempfile.TemporaryDirectory() as folder, patch(
            "quantrade_research.model_evaluation_repair._validate_inputs"
        ) as reader:
            with self.assertRaisesRegex(DataQualityError, "already exists"):
                run(dataset=Path("missing"), panel=Path("missing"), monthly_path=Path("missing"),
                    output=Path(folder), database_url="unused")
            reader.assert_not_called()

    def test_reference_peers_include_rows_without_completed_labels(self):
        day = date(2023, 1, 3)
        labelled = [Example(day, "2023-01", "a", .1, .02, 1, (.1,) * 6, "hash")]
        columns = ["formation_date", "security_id", "momentum_12_1_raw", "relative_strength_6m_raw",
                   "realized_volatility_60d_raw", "earnings_yield_ttm_raw", "return_on_assets_ttm_raw"]
        with tempfile.TemporaryDirectory() as folder:
            panel = Path(folder) / "panel.csv.gz"
            with gzip.open(panel, "wt", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(columns)
                for key, value in (("a", 1), ("b", 2), ("c", 0)):
                    writer.writerow([day, key, *([value] * 5)])
            values = {(day, key): (value, value, value) for key, value in (("a", 1), ("b", 2), ("c", 0))}
            with patch("quantrade_research.model_evaluation_repair._load_static_sectors_and_liquidity",
                       return_value=({key: "sector" for key in "abc"}, values, "lineage")) as loader:
                attached, _ = attach_full_universe(labelled, panel, "unused")
            self.assertEqual(attached[0].active_features, (.5,) * 6)
            self.assertTrue(loader.call_args.kwargs["conservative_asof"])

    def test_outer_labels_cannot_change_inner_selection(self):
        index = {date(2023, month, 3): [
            Example(date(2023, month, 3), f"2023-{month:02d}", str(i), i / 10, i / 100,
                    .1, tuple((i + j) / 10 for j in range(6)), "hash", (.1,) * 6)
            for i in range(10)] for month in (1, 3, 5)}
        outer = {"outer_fold": 1, "inner_folds": [self.split]}
        first = tune([], index, outer, CHALLENGER)
        index[date(2023, 5, 3)] = [replace(x, target=-999, family_features=(999,) * 6)
                                     for x in index[date(2023, 5, 3)]]
        self.assertEqual(first, tune([], index, outer, CHALLENGER))


if __name__ == "__main__":
    unittest.main()
