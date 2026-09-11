from datetime import date, datetime, timezone
from decimal import Decimal
import unittest

from quantrade_research.feature_diagnostics import FeatureOutcome
from quantrade_research.features import FeatureValue, baseline_feature_registry
from quantrade_research.quality import DataQualityError
from quantrade_research.model_eligibility import (
    ALL_SERIALIZED_INPUTS_V1,
    EXACT_ZERO_COEFFICIENTS_V1,
)
from quantrade_research.score_run import (
    LEGACY_HISTORICAL_SCORE_PROTOCOL,
    SCORE_PROTOCOL_BY_ELIGIBILITY_CONTRACT,
    _load_facts,
    _outcome,
    score_protocol_for_eligibility,
)
from quantrade_research.sec_form_scope import RESEARCH_RELEVANT_FORMS


class RecordingCursor:
    def __init__(self):
        self.query = ""
        self.parameters = ()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, query, parameters):
        self.query = query
        self.parameters = parameters

    def fetchall(self):
        return []


class RecordingConnection:
    def __init__(self):
        self.recording_cursor = RecordingCursor()

    def cursor(self):
        return self.recording_cursor


class ScoreRunOutcomeTests(unittest.TestCase):
    def test_live_and_rollback_contracts_have_distinct_snapshot_versions(self) -> None:
        self.assertEqual(LEGACY_HISTORICAL_SCORE_PROTOCOL, "0.1")
        self.assertNotEqual(
            SCORE_PROTOCOL_BY_ELIGIBILITY_CONTRACT[EXACT_ZERO_COEFFICIENTS_V1],
            SCORE_PROTOCOL_BY_ELIGIBILITY_CONTRACT[ALL_SERIALIZED_INPUTS_V1],
        )
        self.assertEqual(
            score_protocol_for_eligibility(
                ALL_SERIALIZED_INPUTS_V1, historical_replay=True,
            ),
            LEGACY_HISTORICAL_SCORE_PROTOCOL,
        )
        with self.assertRaisesRegex(DataQualityError, "historical replay"):
            score_protocol_for_eligibility(
                EXACT_ZERO_COEFFICIENTS_V1, historical_replay=True,
            )

    def test_daily_score_facts_are_restricted_to_research_forms(self) -> None:
        connection = RecordingConnection()

        result = _load_facts(
            connection, ("00000000-0000-0000-0000-000000000001",),
            date(2026, 8, 28),
            datetime(2026, 8, 28, 20, tzinfo=timezone.utc),
        )

        self.assertEqual(result, {})
        self.assertIn("filing.form = ANY(%s)", connection.recording_cursor.query)
        self.assertEqual(
            set(connection.recording_cursor.parameters[3]),
            set(RESEARCH_RELEVANT_FORMS),
        )

    def test_calculated_value_is_a_available_feature_outcome(self) -> None:
        registry = baseline_feature_registry()
        formation_date = date(2026, 8, 21)
        definition = registry.get("momentum_12_1", "v1")

        outcome = _outcome(
            "security-1", formation_date, registry, "momentum_12_1",
            lambda: FeatureValue("security-1", formation_date, definition.key, definition.version,
                                 definition.definition_hash, Decimal("0.12")),
        )

        self.assertEqual(outcome.value, Decimal("0.12"))
        self.assertIsNone(outcome.unavailable_reason)

    def test_data_failure_is_an_explicit_unavailable_feature_outcome(self) -> None:
        outcome = _outcome(
            "security-1", date(2026, 8, 21), baseline_feature_registry(), "momentum_12_1",
            lambda: (_ for _ in ()).throw(DataQualityError("missing completed sessions")),
        )

        self.assertIsNone(outcome.value)
        self.assertEqual(outcome.unavailable_reason, "data_unavailable:missing completed sessions")
