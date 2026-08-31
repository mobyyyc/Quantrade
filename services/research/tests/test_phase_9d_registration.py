from hashlib import sha256
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
REGISTRATION = ROOT / "research" / "registrations" / "phase_9d_anchored_stability_v1.json"
PROTOCOL = ROOT / "PHASE_9D_STABILITY_PROTOCOL.md"


class Phase9DRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(REGISTRATION.read_text(encoding="utf-8"))

    def test_registration_and_protocol_are_authenticated(self) -> None:
        payload = dict(self.document)
        recorded = payload.pop("registration_sha256")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(sha256(canonical).hexdigest(), recorded)
        protocol = PROTOCOL.read_text(encoding="utf-8").replace("\r\n", "\n").encode()
        self.assertEqual(
            sha256(protocol).hexdigest(),
            self.document["protocol_document_canonical_sha256"],
        )

    def test_numeric_bootstrap_constants_are_registered(self) -> None:
        self.assertEqual(
            self.document["bootstrap"],
            {
                "block_length_calendar_months": 3,
                "resamples": 10000,
                "seed": 20260830,
                "type": "paired_circular_moving_block",
            },
        )

    def test_candidate_budget_and_anchor_eligibility_are_exact(self) -> None:
        candidate = self.document["candidate"]
        self.assertEqual(candidate["configuration_count"], 3)
        self.assertEqual(candidate["penalties"], [1, 10, 100])
        self.assertEqual(
            candidate["correction_families"],
            ["investment_issuance", "profitability_quality"],
        )
        anchor = self.document["anchor"]
        nonzero = set(anchor["mathematically_nonzero_inputs"])
        zero = set(anchor["mathematically_zero_inputs"])
        self.assertFalse(nonzero & zero)
        self.assertEqual(nonzero | zero, set(anchor["feature_columns"]))
        by_feature = dict(zip(
            anchor["feature_columns"], anchor["serialized_coefficients"], strict=True,
        ))
        self.assertTrue(all(by_feature[key] != 0 for key in nonzero))
        self.assertTrue(all(by_feature[key] == 0 for key in zero))

    def test_holdout_and_allowed_decisions_fail_closed(self) -> None:
        self.assertTrue(
            self.document["consumed_holdout"]["permanently_unavailable_for_selection"]
        )
        self.assertEqual(
            self.document["allowed_decisions"],
            ["freeze_for_forward_shadow", "no-freeze"],
        )
        gates = self.document["frozen_gates"]
        self.assertGreaterEqual(gates["minimum_mean_monthly_rank_ic_delta"], 0.004)
        self.assertLessEqual(gates["maximum_absolute_one_way_turnover"], 0.36)
        self.assertGreaterEqual(gates["minimum_consecutive_rank_stability"], 0.90)


if __name__ == "__main__":
    unittest.main()
