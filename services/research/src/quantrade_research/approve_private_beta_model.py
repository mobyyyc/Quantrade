"""Create an immutable approval decision for the frozen active research model."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path

from .active_model import _dotenv_values
from .approval import ModelApprovalEvidence, evaluate_model_approval
from .quality import DataQualityError


APPROVAL_SCOPE = "private_beta"
COHORT_SIZE = 500


def _document(payload: bytes, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise DataQualityError(f"invalid {label} JSON") from error
    if not isinstance(value, dict):
        raise DataQualityError(f"{label} must be a JSON object")
    return value


def serialize_approval_decision(decision: dict[str, object]) -> bytes:
    return (json.dumps(decision, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build_private_beta_approval_decision(
    *,
    model_artifact_bytes: bytes,
    experiment_bytes: bytes,
    training_manifest_bytes: bytes,
    selection_bytes: bytes,
    evaluation_bytes: bytes,
    integrity_audit_bytes: bytes,
    decided_at: datetime,
) -> dict[str, object]:
    """Validate the frozen evidence chain and apply the pre-existing approval policy."""
    artifact = _document(model_artifact_bytes, label="model artifact")
    experiment = _document(experiment_bytes, label="development experiment")
    manifest = _document(training_manifest_bytes, label="training manifest")
    selection = _document(selection_bytes, label="holdout selection")
    evaluation = _document(evaluation_bytes, label="holdout evaluation")
    integrity = _document(integrity_audit_bytes, label="integrity audit")

    model_version = str(artifact.get("model_version", ""))
    if not model_version or artifact.get("status") != "research_only":
        raise DataQualityError("approval source must be a frozen research-only model artifact")
    if artifact.get("source_experiment_sha256") != sha256(experiment_bytes).hexdigest():
        raise DataQualityError("model artifact does not match the development experiment")
    if selection.get("model_card") != model_version or selection.get("holdout_performance_evaluated") is not False:
        raise DataQualityError("holdout selection does not match the frozen model or pre-evaluation state")
    if integrity.get("evaluation_sha256") != sha256(evaluation_bytes).hexdigest():
        raise DataQualityError("integrity audit does not match the holdout evaluation")
    if evaluation.get("holdout_performance_evaluated") is not True or evaluation.get("status") != "execution_cost_evaluation_complete":
        raise DataQualityError("completed locked-holdout execution and cost evidence is required")
    if integrity.get("approval_eligible") is not True or integrity.get("failures") != []:
        raise DataQualityError("holdout integrity evidence is not eligible for policy review")
    if manifest.get("data_capability_tier") != artifact.get("data_capability_tier"):
        raise DataQualityError("training manifest and model artifact data tiers differ")
    try:
        folds = experiment["selected_candidate"]["folds"]  # type: ignore[index]
        formations = selection["formations"]
        shared_eligible = [int(item["shared_eligible_count"]) for item in formations]  # type: ignore[index]
        cost_case = evaluation["cost_case_summaries_bps"]["20"]  # type: ignore[index]
        holdout_relative_return = Decimal(str(cost_case["candidate_relative_return"]))
    except (KeyError, TypeError, ValueError) as error:
        raise DataQualityError("approval evidence has an invalid gate schema") from error
    if not isinstance(folds, list) or not isinstance(formations, list) or not shared_eligible:
        raise DataQualityError("approval evidence must include validation folds and holdout formations")

    minimum_eligible = min(shared_eligible)
    feature_coverage = Decimal(minimum_eligible) / Decimal(COHORT_SIZE)
    evidence = ModelApprovalEvidence(
        data_capability_tier=str(artifact["data_capability_tier"]),
        walk_forward_fold_count=len(folds),
        feature_coverage=feature_coverage,
        holdout_evaluated=True,
        holdout_relative_return_after_20bps=holdout_relative_return,
        point_in_time_violations=0,
        unresolved_data_quality_issues=0,
    )
    policy = evaluate_model_approval(evidence, scope=APPROVAL_SCOPE)
    if not policy.approved:
        failed = ", ".join(result.gate for result in policy.results if not result.passed)
        raise DataQualityError(f"private-beta approval gates failed: {failed}")

    evidence_payload = {
        "data_capability_tier": evidence.data_capability_tier,
        "walk_forward_fold_count": evidence.walk_forward_fold_count,
        "feature_coverage": str(evidence.feature_coverage),
        "feature_coverage_basis": {
            "cohort_size": COHORT_SIZE,
            "minimum_shared_eligible_count": minimum_eligible,
            "formation_count": len(formations),
        },
        "holdout_evaluated": evidence.holdout_evaluated,
        "holdout_relative_return_after_20bps": str(holdout_relative_return),
        "point_in_time_violations": evidence.point_in_time_violations,
        "unresolved_data_quality_issues": evidence.unresolved_data_quality_issues,
    }
    return {
        "artifact_schema_version": "model_approval_decision_v1",
        "model_version": model_version,
        "approval_scope": APPROVAL_SCOPE,
        "approved": True,
        "decided_at": decided_at.astimezone(timezone.utc).isoformat(),
        "decided_by": "local_owner",
        "evidence": evidence_payload,
        "gate_results": [
            {"gate": result.gate, "passed": result.passed, "detail": result.detail}
            for result in policy.results
        ],
        "source_sha256": {
            "model_artifact": sha256(model_artifact_bytes).hexdigest(),
            "development_experiment": sha256(experiment_bytes).hexdigest(),
            "training_manifest": sha256(training_manifest_bytes).hexdigest(),
            "holdout_selection": sha256(selection_bytes).hexdigest(),
            "holdout_evaluation": sha256(evaluation_bytes).hexdigest(),
            "integrity_audit": sha256(integrity_audit_bytes).hexdigest(),
        },
        "public_performance_claim_eligible": False,
        "limitations": [
            "Private Tier-B research only; this is not an unbiased historical-performance or public-performance approval.",
            "The fixed current-survivors cohort has survivorship bias and static current-sector classifications.",
            "The locked holdout is consumed and cannot be reused for model selection, tuning, or calibration.",
            "Approval does not guarantee that future baskets or stocks will outperform SPY.",
        ],
    }


def record_approval_and_redeploy(*, database_url: str, decision: dict[str, object], decision_uri: str, decision_sha256: str) -> None:
    """Append the decision and a corrected deployment event in one transaction."""
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM quantrade.model_approval_decisions WHERE model_version = %s AND approval_scope = %s",
                       (decision["model_version"], decision["approval_scope"]))
        if cursor.fetchone() is not None:
            raise DataQualityError(f"approval decision is already recorded: {decision['model_version']}")
        cursor.execute(
            """INSERT INTO quantrade.model_approval_decisions
                   (model_version, approval_scope, approved, evidence, gate_results,
                    decision_uri, decision_sha256, decided_at, decided_by)
               VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)""",
            (
                decision["model_version"], decision["approval_scope"], decision["approved"],
                json.dumps(decision["evidence"]), json.dumps(decision["gate_results"]),
                decision_uri, decision_sha256, decision["decided_at"], decision["decided_by"],
            ),
        )
        cursor.execute(
            """INSERT INTO quantrade.model_deployments
                   (model_version, approval_scope, approval_evidence_uri, deployed_by)
               VALUES (%s, 'private_beta', %s, %s)""",
            (decision["model_version"], decision_uri, decision["decided_by"]),
        )
        connection.commit()


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply the immutable private-beta approval policy to one frozen model")
    parser.add_argument("--model-artifact", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--training-manifest", type=Path, required=True)
    parser.add_argument("--holdout-selection", type=Path, required=True)
    parser.add_argument("--holdout-evaluation", type=Path, required=True)
    parser.add_argument("--integrity-audit", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    if arguments.decision.exists():
        raise DataQualityError(f"refusing to overwrite immutable approval decision: {arguments.decision}")
    inputs = {
        "model_artifact_bytes": arguments.model_artifact.read_bytes(),
        "experiment_bytes": arguments.experiment.read_bytes(),
        "training_manifest_bytes": arguments.training_manifest.read_bytes(),
        "selection_bytes": arguments.holdout_selection.read_bytes(),
        "evaluation_bytes": arguments.holdout_evaluation.read_bytes(),
        "integrity_audit_bytes": arguments.integrity_audit.read_bytes(),
    }
    decision = build_private_beta_approval_decision(**inputs, decided_at=datetime.now(timezone.utc))
    payload = serialize_approval_decision(decision)
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    arguments.decision.parent.mkdir(parents=True, exist_ok=True)
    arguments.decision.write_bytes(payload)
    try:
        record_approval_and_redeploy(
            database_url=settings.database_url,
            decision=decision,
            decision_uri=arguments.decision.resolve().as_uri(),
            decision_sha256=sha256(payload).hexdigest(),
        )
    except Exception:
        arguments.decision.unlink(missing_ok=True)
        raise
    print(f"approved_model={decision['model_version']}; scope=private_beta; decision_sha256={sha256(payload).hexdigest()}")


if __name__ == "__main__":
    main()
