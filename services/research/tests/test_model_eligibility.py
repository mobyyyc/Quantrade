from datetime import date
import struct
import unittest

from quantrade_research.active_model import ActiveModelArtifact
from quantrade_research.model_eligibility import (
    ALL_SERIALIZED_INPUTS_V1,
    EXACT_ZERO_COEFFICIENTS_V1,
    evaluate_model_inputs,
    ignores_exact_zero_coefficients,
    required_model_columns,
)
from quantrade_research.quality import DataQualityError
from quantrade_research.phase_9d_eligibility_audit import audit_rank_rows


MODEL = ActiveModelArtifact(
    "test", "v1", "registry", ("a", "b", "c"),
    (0.5, 0.25, 0.75), (0.25, 0.5, 0.25), 0.01, (0.02, -0.0, -0.01),
)


class ModelEligibilityTests(unittest.TestCase):
    def test_named_contracts_are_exact_and_fail_closed(self) -> None:
        self.assertFalse(ignores_exact_zero_coefficients(ALL_SERIALIZED_INPUTS_V1))
        self.assertTrue(ignores_exact_zero_coefficients(EXACT_ZERO_COEFFICIENTS_V1))
        with self.assertRaisesRegex(DataQualityError, "unsupported score eligibility contract"):
            ignores_exact_zero_coefficients("zeroish")

    def test_only_exact_serialized_zero_is_ignored(self) -> None:
        self.assertEqual(
            required_model_columns(MODEL, ignore_exact_zero_coefficients=True),
            ("a", "c"),
        )
        near_zero = ActiveModelArtifact(
            "test", "v1", "registry", ("a",), (0.0,), (1.0,), 0.0, (5e-324,),
        )
        self.assertEqual(
            required_model_columns(near_zero, ignore_exact_zero_coefficients=True),
            ("a",),
        )

    def test_complete_prediction_is_byte_identical_under_both_policies(self) -> None:
        values = {"a": 0.75, "b": 0.0, "c": 0.25}
        legacy = evaluate_model_inputs(MODEL, values, ignore_exact_zero_coefficients=False)
        corrected = evaluate_model_inputs(MODEL, values, ignore_exact_zero_coefficients=True)
        self.assertEqual(
            struct.pack(">d", legacy.prediction), struct.pack(">d", corrected.prediction),
        )

    def test_missing_nonzero_input_still_excludes_the_row(self) -> None:
        result = evaluate_model_inputs(
            MODEL, {"a": None, "b": None, "c": 0.25},
            ignore_exact_zero_coefficients=True,
        )
        self.assertFalse(result.eligible)
        self.assertEqual(result.missing_required_columns, ("a",))

    def test_audit_versions_coverage_rank_and_explanation_changes(self) -> None:
        formation = date(2024, 1, 5)
        inputs = {
            (formation, "a"): {"a": 0.8, "b": 0.2, "c": 0.3},
            (formation, "b"): {"a": 0.6, "b": None, "c": 0.4},
            (formation, "c"): {"a": None, "b": 0.5, "c": 0.2},
        }
        result = audit_rank_rows(
            model=MODEL, ranked_inputs=inputs, by_formation={formation: ("a", "b", "c")},
        )
        self.assertEqual(result["previously_eligible_rows"], 1)
        self.assertEqual(result["corrected_eligible_rows"], 2)
        self.assertEqual(result["newly_eligible_rows"], 1)
        self.assertEqual(result["previous_raw_prediction_byte_mismatch_count"], 0)
        self.assertEqual(result["new_eligibility_nonzero_missing_violations"], 0)
        self.assertEqual(result["explanations"]["active_input_count"], 2)


if __name__ == "__main__":
    unittest.main()
