import unittest

from quantrade_research.phase_9c_data_feasibility import classify_capabilities


def evidence():
    return {
        "cohort_size": 500,
        "market": {
            "equity_basis": {
                "unadjusted": {"security_count": 500},
                "split_adjusted": {"security_count": 500},
                "total_return_adjusted": {"security_count": 100},
            },
            "benchmark_basis": {"split_adjusted": {"row_count": 1000}},
        },
        "corporate_actions": {"cash_dividend": 100, "forward_split": 2, "spin_off": 1},
        "sec": {
            "candidate_complete_flow_sets": {"NetIncomeLoss": {"security_count": 450}},
            "immutable_observation_count": 10,
        },
        "shares": {"endpoint_security_count": 465, "weighted_average_basic_security_count": 492},
        "historical_sic": {"normalized_security_count": 0},
        "development_start": "2021-01-01",
        "weekly_market_features": {
            "first_formation": "2021-01-08",
            "first_90pct_252_session_formation": "2021-01-08",
            "minimum_252_session_coverage_after_eligibility": 0.95,
        },
    }


class Phase9CDataFeasibilityTests(unittest.TestCase):
    def test_classifies_measured_but_unimplemented_paths_as_restricted(self) -> None:
        report = classify_capabilities(evidence())
        self.assertEqual(report["corporate_action_wealth_label"]["status"], "restricted")
        self.assertEqual(report["point_in_time_quarterly_ttm"]["status"], "restricted")
        self.assertEqual(report["endpoint_shares"]["status"], "restricted")
        self.assertEqual(report["historical_sic_ff12"]["status"], "deferred")
        self.assertEqual(report["weekly_market_features"]["status"], "pass")

    def test_blocks_label_without_ordinary_actions_or_price_coverage(self) -> None:
        raw = evidence()
        raw["corporate_actions"] = {}
        raw["market"]["equity_basis"]["unadjusted"]["security_count"] = 0
        report = classify_capabilities(raw)
        self.assertEqual(report["corporate_action_wealth_label"]["status"], "blocked")

    def test_does_not_treat_weighted_average_shares_as_endpoint_coverage(self) -> None:
        raw = evidence()
        raw["shares"]["endpoint_security_count"] = 0
        report = classify_capabilities(raw)
        self.assertEqual(report["endpoint_shares"]["status"], "blocked")

    def test_requires_ninety_percent_minimum_weekly_coverage(self) -> None:
        raw = evidence()
        raw["weekly_market_features"]["minimum_252_session_coverage_after_eligibility"] = 0.899
        report = classify_capabilities(raw)
        self.assertEqual(report["weekly_market_features"]["status"], "blocked")

    def test_restricts_weekly_features_when_long_history_starts_later(self) -> None:
        raw = evidence()
        raw["weekly_market_features"]["first_90pct_252_session_formation"] = "2022-01-07"
        report = classify_capabilities(raw)
        self.assertEqual(report["weekly_market_features"]["status"], "restricted")


if __name__ == "__main__":
    unittest.main()
