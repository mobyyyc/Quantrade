from datetime import datetime, timezone
import json
import unittest

from quantrade_research.approve_private_beta_model import build_private_beta_approval_decision, serialize_approval_decision
from quantrade_research.quality import DataQualityError


def payloads() -> dict[str, bytes]:
    experiment = {
        "selected_candidate": {"folds": [{}, {}, {}]},
    }
    experiment_bytes = json.dumps(experiment, sort_keys=True).encode()
    artifact = {
        "model_version": "candidate_v1", "status": "research_only", "data_capability_tier": "B",
        "source_experiment_sha256": __import__("hashlib").sha256(experiment_bytes).hexdigest(),
    }
    selection = {
        "model_card": "candidate_v1", "holdout_performance_evaluated": False,
        "formations": [{"shared_eligible_count": 464}, {"shared_eligible_count": 470}],
    }
    evaluation = {
        "status": "execution_cost_evaluation_complete", "holdout_performance_evaluated": True,
        "cost_case_summaries_bps": {"20": {"candidate_relative_return": "0.04"}},
    }
    evaluation_bytes = json.dumps(evaluation, sort_keys=True).encode()
    integrity = {
        "approval_eligible": True, "failures": [],
        "evaluation_sha256": __import__("hashlib").sha256(evaluation_bytes).hexdigest(),
    }
    return {
        "model_artifact_bytes": json.dumps(artifact, sort_keys=True).encode(),
        "experiment_bytes": experiment_bytes,
        "training_manifest_bytes": json.dumps({"data_capability_tier": "B", "content_sha256": "a" * 64}).encode(),
        "selection_bytes": json.dumps(selection, sort_keys=True).encode(),
        "evaluation_bytes": evaluation_bytes,
        "integrity_audit_bytes": json.dumps(integrity, sort_keys=True).encode(),
    }


def clean_payloads() -> dict[str, bytes]:
    manifest = {
        "dataset_key": "tier_b_clean_monthly_model_development",
        "dataset_version": "v1", "content_sha256": "d" * 64,
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
    artifact = {
        "artifact_schema_version": "research_inference_v3",
        "model_version": "clean_v3", "status": "development_frozen",
        "data_capability_tier": "B", "family": "elastic_net",
        "l1_penalty": 0.001, "l2_penalty": 0.001,
        "source_dataset": {
            "content_sha256": manifest["content_sha256"],
            "manifest_sha256": __import__("hashlib").sha256(manifest_bytes).hexdigest(),
        },
    }
    artifact_bytes = json.dumps(artifact, sort_keys=True).encode()
    experiment = {
        "status": "development_validation_complete", "model_version": "clean_v3",
        "development_only": True, "holdout_used": False,
        "source_model_artifact_sha256": __import__("hashlib").sha256(artifact_bytes).hexdigest(),
        "source_dataset_sha256": manifest["content_sha256"],
        "source_dataset_manifest_sha256": __import__("hashlib").sha256(manifest_bytes).hexdigest(),
        "frozen_specification": {"family": "elastic_net", "l1": 0.001, "l2": 0.001},
        "folds": [{}, {}, {}, {}],
    }
    experiment_bytes = json.dumps(experiment, sort_keys=True).encode()
    selection = {
        "model_card": "clean_v3", "holdout_performance_evaluated": False,
        "source_model_artifact_sha256": __import__("hashlib").sha256(artifact_bytes).hexdigest(),
        "formations": [{"shared_eligible_count": 464}, {"shared_eligible_count": 470}],
    }
    evaluation = {
        "status": "execution_cost_evaluation_complete", "holdout_performance_evaluated": True,
        "cost_case_summaries_bps": {"20": {"candidate_relative_return": "0.04"}},
    }
    evaluation_bytes = json.dumps(evaluation, sort_keys=True).encode()
    integrity = {
        "approval_eligible": True, "failures": [],
        "evaluation_sha256": __import__("hashlib").sha256(evaluation_bytes).hexdigest(),
    }
    return {
        "model_artifact_bytes": artifact_bytes,
        "experiment_bytes": experiment_bytes,
        "training_manifest_bytes": manifest_bytes,
        "selection_bytes": json.dumps(selection, sort_keys=True).encode(),
        "evaluation_bytes": evaluation_bytes,
        "integrity_audit_bytes": json.dumps(integrity, sort_keys=True).encode(),
    }
class ApprovePrivateBetaModelTests(unittest.TestCase):
    def test_builds_clean_v3_decision_from_matching_frozen_evidence(self) -> None:
        decision = build_private_beta_approval_decision(
            **clean_payloads(), decided_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
        )

        self.assertTrue(decision["approved"])
        self.assertEqual(decision["evidence"]["walk_forward_fold_count"], 4)
        self.assertFalse(decision["public_performance_claim_eligible"])
        self.assertTrue(any("reused diagnostic" in item for item in decision["limitations"]))

    def test_clean_v3_rejects_selection_for_different_artifact_bytes(self) -> None:
        values = clean_payloads()
        selection = json.loads(values["selection_bytes"])
        selection["source_model_artifact_sha256"] = "0" * 64
        values["selection_bytes"] = json.dumps(selection, sort_keys=True).encode()

        with self.assertRaisesRegex(DataQualityError, "selection does not match"):
            build_private_beta_approval_decision(
                **values, decided_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
            )

    def test_builds_approved_decision_from_matching_frozen_evidence(self) -> None:
        decision = build_private_beta_approval_decision(
            **payloads(), decided_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        )
        self.assertTrue(decision["approved"])
        self.assertEqual(decision["approval_scope"], "private_beta")
        self.assertEqual(decision["evidence"]["feature_coverage"], "0.928")
        self.assertFalse(decision["public_performance_claim_eligible"])
        self.assertTrue(serialize_approval_decision(decision).endswith(b"\n"))

    def test_rejects_integrity_audit_for_different_evaluation(self) -> None:
        values = payloads()
        integrity = json.loads(values["integrity_audit_bytes"])
        integrity["evaluation_sha256"] = "0" * 64
        values["integrity_audit_bytes"] = json.dumps(integrity).encode()
        with self.assertRaisesRegex(DataQualityError, "does not match"):
            build_private_beta_approval_decision(
                **values, decided_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
            )

    def test_rejects_failed_cost_gate(self) -> None:
        values = payloads()
        evaluation = json.loads(values["evaluation_bytes"])
        evaluation["cost_case_summaries_bps"]["20"]["candidate_relative_return"] = "-0.01"
        values["evaluation_bytes"] = json.dumps(evaluation, sort_keys=True).encode()
        integrity = json.loads(values["integrity_audit_bytes"])
        integrity["evaluation_sha256"] = __import__("hashlib").sha256(values["evaluation_bytes"]).hexdigest()
        values["integrity_audit_bytes"] = json.dumps(integrity, sort_keys=True).encode()
        with self.assertRaisesRegex(DataQualityError, "cost_robustness"):
            build_private_beta_approval_decision(
                **values, decided_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
